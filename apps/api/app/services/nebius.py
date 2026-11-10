"""OpenAI-compatible JSON-schema requests, with bounded timeouts and retries. No provider fallback."""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

import httpx

from app.agents.context import Output
from app.observability.tracing import (
    capture_synthetic_content,
    current_run_id,
    observation,
    sanitize_content,
)

logger = logging.getLogger("jeeves.models")
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"


class ModelUnavailable(RuntimeError):
    """The configured model could not produce validated output."""


def response_schema(output_type: type[Output], payload: dict) -> dict:
    schema = output_type.model_json_schema()
    if isinstance(payload.get("evidence"), list):
        # A reviewer cites the passages it actually saw, never page labels,
        # invented chunk IDs, prior-turn citations, or a comma-joined list.
        ids = sorted(
            {
                item["chunk_id"]
                for item in payload["evidence"]
                if isinstance(item, dict) and isinstance(item.get("chunk_id"), str)
            }
        )
        for definition in (schema, *schema.get("$defs", {}).values()):
            refs = definition.get("properties", {}).get("citation_ids")
            if refs is not None:
                if ids:
                    refs["items"] = {"type": "string", "enum": ids}
                else:
                    refs["maxItems"] = 0
    return schema


@dataclass(frozen=True)
class JsonSchemaModel:
    client: httpx.AsyncClient
    model: str
    max_tokens: int = 3000
    timeout_seconds: float = 45
    token_limit_field: str = "max_tokens"
    role: Literal["generator", "reviewer"] | None = None
    reasoning_effort: Literal["low"] | None = None

    async def generate(
        self, *, prompt: str, payload: dict[str, Any], output_type: type[Output]
    ) -> Output:
        # Content capture is separately enabled only for synthetic demo inputs.
        with observation(
            "model-call",
            as_type="span",
            model=self.model,
            metadata={
                "schema": output_type.__name__,
                **({"model_role": self.role} if self.role else {}),
            },
        ) as span:
            if capture_synthetic_content():
                span.update(input=sanitize_content({"prompt": prompt, "payload": payload}))
            else:
                span.update(input={"capture": "metadata_only", "schema": output_type.__name__})
            result = await self._generate(prompt=prompt, payload=payload, output_type=output_type)
            if capture_synthetic_content():
                span.update(output=sanitize_content(result.model_dump(mode="json")))
            return result

    async def _generate(
        self, *, prompt: str, payload: dict[str, Any], output_type: type[Output]
    ) -> Output:
        started = perf_counter()
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            self.token_limit_field: self.max_tokens,
            **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_type.__name__,
                    "schema": response_schema(output_type, payload),
                },
            },
        }
        if output_type.__name__ == "PacketDraft" and self.model.startswith(
            "deepseek-ai/DeepSeek-V4"
        ):
            # The separately reviewed packet is a structured drafting task. Reserve its budget for JSON.
            body["reasoning_effort"] = "none"
        for attempt in range(2):
            with observation(
                "model-generation",
                as_type="generation",
                model=self.model,
                input={"capture": "metadata_only", "schema": output_type.__name__},
                metadata={
                    "attempt": attempt + 1,
                    "model_role": self.role or "generator",
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                },
            ) as span:
                try:
                    response = await self.client.post(
                        "chat/completions", json=body, timeout=self.timeout_seconds
                    )
                    if attempt == 0 and (
                        response.status_code == 429 or response.status_code >= 500
                    ):
                        span.update(
                            level="WARNING",
                            status_message="Provider retry",
                            output={"http_status": response.status_code},
                        )
                        await asyncio.sleep(0.25)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    raw_usage = data.get("usage") or {}
                    if not isinstance(raw_usage, dict):
                        raw_usage = {}
                    usage = {
                        key: raw_usage[key]
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                        if isinstance(raw_usage.get(key), int)
                        and not isinstance(raw_usage[key], bool)
                        and raw_usage[key] >= 0
                    }
                    if usage:
                        span.update(usage_details=usage)
                    choice = data["choices"][0]
                    if (
                        choice["message"].get("refusal")
                        or choice.get("finish_reason") == "content_filter"
                    ):
                        raise ModelUnavailable("Model response was unavailable or invalid")
                    if choice.get("finish_reason") != "stop":
                        if (
                            choice.get("finish_reason") == "length"
                            and body.get("reasoning_effort") == "low"
                            and self.model.startswith("deepseek-ai/DeepSeek-V4")
                        ):
                            # Retry with the same token cap, reserving it for the actual JSON.
                            # The independent incident and policy checks still run on the result.
                            body["reasoning_effort"] = "none"
                        raise ValueError("Incomplete model response")
                    result = output_type.model_validate_json(choice["message"]["content"])
                    span.update(
                        output={"validated": True},
                        metadata={
                            "schema": output_type.__name__,
                            "attempts": attempt + 1,
                            **({"model_role": self.role} if self.role else {}),
                        },
                    )
                    logger.info(
                        json.dumps(
                            {
                                "event": "model_completed",
                                "run_id": current_run_id.get(),
                                "model": self.model,
                                "schema": output_type.__name__,
                                "elapsed_ms": round((perf_counter() - started) * 1000),
                                "usage": usage,
                            }
                        )
                    )
                    return result
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    span.update(level="ERROR", status_message="Provider transport failure")
                    if attempt == 0:
                        continue
                    raise ModelUnavailable("Model request timed out or could not connect") from exc
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    span.update(
                        level="WARNING",
                        status_message="Structured validation failed",
                        output={"validated": False},
                    )
                    if attempt == 0:
                        body["messages"].append(
                            {
                                "role": "user",
                                "content": "Return a complete JSON object matching the requested schema and its field constraints. Do not add commentary.",
                            }
                        )
                        continue
                    raise ModelUnavailable("Model response was unavailable or invalid") from exc
                except httpx.HTTPStatusError as exc:
                    # Never include provider bodies, prompts, or authorization headers in public errors.
                    raise ModelUnavailable("Model response was unavailable or invalid") from exc
        raise ModelUnavailable("Model request failed")


class NebiusModel(JsonSchemaModel):
    """Nebius uses the default token limit field."""


def nebius_pair(
    client: httpx.AsyncClient, generator_id: str, reviewer_id: str
) -> tuple[NebiusModel, NebiusModel]:
    generator_id, reviewer_id = generator_id.strip(), reviewer_id.strip()
    if not generator_id or not reviewer_id or generator_id == reviewer_id:
        raise ValueError("Nebius requires two distinct generator and reviewer model IDs.")
    # Nebius counts reasoning and visible JSON against the same completion limit.
    # A complete PacketDraft with policy citations needs more room than a route.
    return (
        NebiusModel(
            client,
            generator_id,
            role="generator",
            max_tokens=8192,
            timeout_seconds=90,
            reasoning_effort="low" if generator_id.startswith("deepseek-ai/DeepSeek-V4") else None,
        ),
        NebiusModel(client, reviewer_id, role="reviewer", max_tokens=4096, timeout_seconds=75),
    )

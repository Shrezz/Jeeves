"""Nebius JSON-schema requests, with bounded timeouts and retries. No provider fallback."""

import asyncio
import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from app.agents.context import Output
from app.observability.tracing import (
    capture_synthetic_content,
    current_run_id,
    observation,
    sanitize_content,
)

logger = logging.getLogger("jeeves.models")


class ModelUnavailable(RuntimeError):
    """The configured model could not produce validated output."""


@dataclass(frozen=True)
class NebiusModel:
    client: httpx.AsyncClient
    model: str
    max_tokens: int = 3000
    timeout_seconds: float = 45

    async def generate(
        self, *, prompt: str, payload: dict[str, Any], output_type: type[Output]
    ) -> Output:
        # Content capture is separately enabled only for synthetic demo inputs.
        with observation(
            "model-generation",
            as_type="generation",
            model=self.model,
            metadata={"schema": output_type.__name__},
        ) as span:
            if capture_synthetic_content():
                span.update(input=sanitize_content({"prompt": prompt, "payload": payload}))
            result = await self._generate(
                prompt=prompt, payload=payload, output_type=output_type, span=span
            )
            if capture_synthetic_content():
                span.update(output=sanitize_content(result.model_dump(mode="json")))
            return result

    async def _generate(
        self, *, prompt: str, payload: dict[str, Any], output_type: type[Output], span: Any
    ) -> Output:
        started = perf_counter()
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            "max_tokens": self.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_type.__name__,
                    "schema": output_type.model_json_schema(),
                },
            },
        }
        for attempt in range(2):
            try:
                response = await self.client.post(
                    "chat/completions", json=body, timeout=self.timeout_seconds
                )
                if attempt == 0 and (response.status_code == 429 or response.status_code >= 500):
                    await asyncio.sleep(0.25)
                    continue
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                    raise ValueError("Incomplete or refused model response")
                result = output_type.model_validate_json(choice["message"]["content"])
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
                span.update(
                    output={"validated": True},
                    metadata={"schema": output_type.__name__, "attempts": attempt + 1},
                )
                logger.info(
                    json.dumps(
                        {
                            "event": "model_completed",
                            "run_id": current_run_id.get(),
                            "model": self.model,
                            "schema": output_type.__name__,
                            "elapsed_ms": round((perf_counter() - started) * 1000),
                            "usage": data.get("usage", {}),
                        }
                    )
                )
                return result
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 0:
                    continue
                raise ModelUnavailable("Model request timed out or could not connect") from exc
            except (httpx.HTTPStatusError, ValueError, KeyError, IndexError, TypeError) as exc:
                # Never include provider bodies, prompts, or authorization headers in public errors.
                raise ModelUnavailable("Model response was unavailable or invalid") from exc
        raise ModelUnavailable("Model request failed")

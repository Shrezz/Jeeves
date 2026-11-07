"""One private JSON request from the authenticated web API; no HTTP listener or tools."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.agents.context import Output
from app.observability.tracing import observation
from app.services.chat_guidance import guidance
from app.services.nebius import NebiusModel


@dataclass
class OllamaModel:
    client: httpx.AsyncClient
    model: str

    async def generate(self, *, prompt: str, payload: dict, output_type: type[Output]) -> Output:
        with observation(
            "model-generation",
            as_type="generation",
            model=self.model,
            metadata={"provider": "ollama", "schema": output_type.__name__},
        ) as span:
            result = await self._generate(
                prompt=prompt, payload=payload, output_type=output_type, span=span
            )
            span.update(output={"validated": True})
            return result

    async def _generate(
        self, *, prompt: str, payload: dict, output_type: type[Output], span
    ) -> Output:
        schema = output_type.model_json_schema()
        # Pydantic accepts Decimal as a number OR arbitrary string. Constrain the
        # provider's grammar so it can't emit formatted currency like "$1,000".
        for definition in (schema, *schema.get("$defs", {}).values()):
            for name, field in definition.get("properties", {}).items():
                if name in {"repair_cost", "covered_amount", "deductible"} and "anyOf" in field:
                    field["anyOf"] = [t for t in field["anyOf"] if t.get("type") != "string"]
        if output_type.__name__ == "PacketDraft":
            # Local grammar generators often omit optional-but-important fields that
            # have schema defaults. Require an explicit value; nullable fields may stay null.
            for definition in (schema, *schema.get("$defs", {}).values()):
                if "properties" in definition:
                    definition["required"] = list(definition["properties"])
            coverage = schema["$defs"]["CoverageDraft"]
            if payload.get("available_chunk_ids"):
                coverage["properties"]["citation_ids"]["items"] = {
                    "type": "string",
                    "enum": payload["available_chunk_ids"],
                }
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        complete_usage = True
        for attempt in range(2):
            response = await self.client.post(
                "api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "format": schema,
                    "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 1500},
                    "messages": messages,
                },
            )
            response.raise_for_status()
            data = response.json()
            for field, key in (
                ("prompt_eval_count", "prompt_tokens"),
                ("eval_count", "completion_tokens"),
            ):
                value = data.get(field)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    usage[key] += value
                else:
                    complete_usage = False
            if not data.get("done") or data.get("done_reason") == "length":
                raise ValueError("Incomplete model response")
            try:
                result = output_type.model_validate_json(data["message"]["content"])
                if complete_usage:
                    span.update(usage_details={**usage, "total_tokens": sum(usage.values())})
                return result
            except ValidationError as exc:
                if attempt:
                    raise
                problems = [
                    {"field": e["loc"], "error": e["msg"]} for e in exc.errors(include_input=False)
                ]
                messages += [
                    {"role": "assistant", "content": data["message"]["content"]},
                    {
                        "role": "user",
                        "content": "Correct the structured response: " + json.dumps(problems),
                    },
                ]
        raise ValueError("Invalid model response")


@asynccontextmanager
async def chat_models():
    mode = os.environ.get("CLAIM_CHAT_PROVIDER", "ollama")
    if mode == "ollama":
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:11434/", trust_env=False, timeout=90
        ) as client:
            model = OllamaModel(client, os.environ.get("OLLAMA_MODEL", "gemma4:12b"))
            yield model, model
    elif mode == "nebius":
        async with httpx.AsyncClient(
            base_url="https://api.tokenfactory.nebius.com/v1/",
            headers={"Authorization": "Bearer " + os.environ["NEBIUS_API_KEY"]},
        ) as client:
            yield (
                NebiusModel(client, os.environ["NEBIUS_GENERATOR_MODEL"]),
                NebiusModel(client, os.environ["NEBIUS_REVIEWER_MODEL"]),
            )
    else:
        raise ValueError("Unsupported chat provider")


async def main() -> None:
    request = json.load(sys.stdin)
    async with chat_models() as (generator, reviewer):
        result = await guidance(request["context"], request["passages"], generator, reviewer)
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())

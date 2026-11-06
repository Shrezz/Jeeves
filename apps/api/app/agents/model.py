"""Adapt an injected LangChain chat model without coupling nodes to a provider."""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.observability.tracing import capture_synthetic_content, observation, sanitize_content

from .context import Output


@dataclass(frozen=True)
class ChatModelAdapter:
    model: BaseChatModel

    async def generate(
        self,
        *,
        prompt: str,
        payload: dict[str, Any],
        output_type: type[Output],
    ) -> Output:
        model_name = getattr(self.model, "model_name", None) or type(self.model).__name__
        with observation(
            "model-generation",
            as_type="generation",
            model=model_name,
            metadata={"schema": output_type.__name__},
        ) as span:
            if capture_synthetic_content():
                span.update(input=sanitize_content({"prompt": prompt, "payload": payload}))
            runnable = self.model.with_structured_output(output_type)
            result = await runnable.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=json.dumps(payload))]
            )
            parsed = output_type.model_validate(result)
            span.update(
                output=sanitize_content(parsed.model_dump(mode="json"))
                if capture_synthetic_content()
                else {"validated": True}
            )
            return parsed

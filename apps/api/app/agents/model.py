"""Adapt an injected LangChain chat model without coupling nodes to a provider."""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

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
        runnable = self.model.with_structured_output(output_type)
        result = await runnable.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload)),
            ]
        )
        return output_type.model_validate(result)

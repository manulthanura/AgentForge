"""Hugging Face adapter for the LLMProvider port.

Built on LangChain's ``langchain-huggingface`` integration
(``HuggingFaceEndpoint`` + ``ChatHuggingFace``) — covers both serverless
Inference Providers (by ``repo_id``) and dedicated Inference Endpoints (by
URL).

The chat model is built lazily on first use rather than in ``__init__``:
``ChatHuggingFace`` resolves a tokenizer for chat-template formatting, which
can touch the network — construction must not happen just from
instantiating the provider (tests inject a stub via ``_chat_model`` before
first use, same as every other adapter's ``_client``).
"""

from __future__ import annotations

from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

from ..config.settings import Settings
from .langchain_support import (
    raise_as_llm_error,
    response_text,
    to_langchain_messages,
    token_usage,
)
from .port import LLMProvider, LLMResponse, Message


class HuggingFaceProvider(LLMProvider):
    name = "huggingface"
    default_model = "meta-llama/Llama-3.1-8B-Instruct"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self._settings = settings
        self._chat_model: ChatHuggingFace | None = None

    def _get_chat_model(self) -> ChatHuggingFace:
        if self._chat_model is None:
            endpoint_kwargs: dict = {
                "huggingfacehub_api_token": self._settings.huggingface_api_token,
                "task": self._settings.huggingface_task,
                "max_new_tokens": 4096,
            }
            if self._settings.huggingface_endpoint_url:
                endpoint_kwargs["endpoint_url"] = self._settings.huggingface_endpoint_url
            else:
                endpoint_kwargs["repo_id"] = self.model
            llm = HuggingFaceEndpoint(**endpoint_kwargs)
            self._chat_model = ChatHuggingFace(llm=llm)
        return self._chat_model

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        # json_mode stays prompt-level: there's no uniform native JSON mode
        # across the many open-model architectures this adapter can point at.
        lc_messages = to_langchain_messages(messages, system)
        try:
            response = self._get_chat_model().bind(max_tokens=max_tokens).invoke(
                lc_messages
            )
        except Exception as exc:
            raise_as_llm_error("Hugging Face", exc)

        input_tokens, output_tokens = token_usage(response)
        return LLMResponse(
            text=response_text(response),
            model=response.response_metadata.get("model", self.model),
            stop_reason=response.response_metadata.get("finish_reason"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response,
        )

"""LLM clients. Backends: hf (free HF Inference API) | ollama | openai_compatible.

The rag service uses these. Swap with one config flag: LLM_BACKEND=hf|ollama|openai_compatible
"""
import json
from typing import Any

import httpx

from .config import get_settings


class LLMClient:
    """Minimal chat-generation client (no LangChain dependency for the call itself)."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = httpx.Client(timeout=120)

    def chat(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> str:
        backend = self._settings.llm_backend
        if backend == "ollama":
            return self._ollama(messages)
        if backend == "openai_compatible":
            return self._openai_compatible(messages)
        return self._hf(messages, tools)

    # ---- HF Inference API (free tier, serverless) -------------------------
    def _hf(self, messages: list[dict[str, str]], tools: list[dict] | None) -> str:
        s = self._settings
        headers = {"Authorization": f"Bearer {s.hf_token}"} if s.hf_token else {}
        url = f"{s.hf_api_url}/models/{s.hf_inference_model}"
        payload: dict[str, Any] = {
            "messages": messages,
            "max_new_tokens": s.llm_max_tokens,
            "temperature": s.llm_temperature,
        }
        if tools:
            payload["tools"] = tools
        resp = self._client.post(url, json=payload, headers=headers)
        if resp.status_code == 503:
            # model cold-start / loading
            raise RuntimeError(resp.json().get("error", "HF model is still loading"))
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            data = data[0]
        choices = data.get("choices")
        if choices:
            if choices[0].get("message", {}).get("tool_calls"):
                raw = json.dumps(choices[0]["message"]["tool_calls"])
                return self._dispatch_tools(messages, tool_calls=json.loads(raw))
            return choices[0]["message"].get("content", "")
        return data.get("generated_text", "")

    # ---- Ollama -------------------------------------------------------------
    def _ollama(self, messages: list[dict[str, str]]) -> str:
        s = get_settings()
        payload = {
            "model": s.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": s.llm_temperature, "num_predict": s.llm_max_tokens},
        }
        resp = self._client.post(f"{s.ollama_host}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    # ---- OpenAI-compatible (portable to other providers) --------------------
    def _openai_compatible(self, messages: list[dict[str, str]]) -> str:
        s = get_settings()
        headers = {"Content-Type": "application/json"}
        if s.openai_compatible_api_key:
            headers["Authorization"] = f"Bearer {s.openai_compatible_api_key}"
        payload = {
            "model": s.openai_compatible_model,
            "messages": messages,
            "temperature": s.llm_temperature,
            "max_tokens": s.llm_max_tokens,
        }
        resp = self._client.post(
            f"{s.openai_compatible_base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _dispatch_tools(self, messages, tool_calls) -> str:
        """If the model requested tool use, return a JSON string the caller can handle.

        In the rag service the caller integrates tools into the chain. Here we
        simply serialize so a tool-using loop can pick it up.
        """
        return json.dumps(tool_calls)


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
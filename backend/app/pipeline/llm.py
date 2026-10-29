"""Step 2: LLM with Sarvam-105B (chat completions, streaming, native tool calling).

Docs: https://docs.sarvam.ai/api-reference/chat/chat-completions-v1
      https://docs.pipecat.ai/server/services/llm/sarvam

- sarvam-30b is deprecated and not accepted by the chat API any more.
- sarvam-105b-conversations (default) is tuned for voice agents and has no
  reasoning setting, which keeps time-to-first-token low.
- sarvam-105b: reasoning "off" sends reasoning_effort=null (the docs say null
  disables it; omitting it would use the server default). "low" sends "low".
- Tokens are streamed; Pipecat forwards them to TTS as they arrive.
"""

from pipecat.services.sarvam.llm import SarvamLLMService


class FormLLMService(SarvamLLMService):
    """SarvamLLMService that can explicitly switch reasoning off for sarvam-105b."""

    def __init__(self, *, reasoning_off: bool, **kwargs):
        super().__init__(**kwargs)
        self._reasoning_off = reasoning_off

    def build_chat_completion_params(self, params_from_context):
        params = super().build_chat_completion_params(params_from_context)
        if self._reasoning_off and self._settings.model == "sarvam-105b":
            params["reasoning_effort"] = None  # sent as JSON null = reasoning disabled
        return params


def make_llm(settings: dict, api_key: str) -> FormLLMService:
    model = settings["llm_model"]
    use_low = model == "sarvam-105b" and settings.get("reasoning") == "low"
    return FormLLMService(
        api_key=api_key,
        reasoning_off=(model == "sarvam-105b" and not use_low),
        settings=FormLLMService.Settings(
            model=model,
            temperature=0.2,
            max_tokens=int(settings["llm_max_tokens"]),
            reasoning_effort="low" if use_low else None,
        ),
    )

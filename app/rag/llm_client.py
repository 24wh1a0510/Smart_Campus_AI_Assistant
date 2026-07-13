"""Chat completion client for GPT-4o Mini via OpenRouter, using the
OpenAI-compatible SDK pointed at OpenRouter's base URL."""
from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI

from app.config.settings import settings


class ChatClient:
    def __init__(self):
        # Re-read settings on every instantiation so a key change in .env
        # takes effect after a full app restart without needing code changes.
        from dotenv import load_dotenv
        load_dotenv(override=True)
        from app.config.settings import Settings
        _s = Settings()
        self._client = OpenAI(
            api_key=_s.openrouter_api_key,
            base_url=_s.openrouter_base_url,
        )
        self._model = _s.openrouter_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=30))
    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        call_type: str = "chat",
        session_id: str = "",
        ab_variant: str = "",
    ) -> dict:
        import time as _time
        _t0 = _time.perf_counter()
        status = "ok"
        error_msg = ""
        result: dict = {"text": "", "prompt_tokens": 0, "completion_tokens": 0}

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = resp.choices[0]
            usage = getattr(resp, "usage", None)
            result = {
                "text": choice.message.content or "",
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            }
        except Exception as e:
            status = "error"
            error_msg = str(e)[:300]
            # Re-raise so tenacity can retry, but tag rate-limit errors clearly
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                status = "rate_limited"
            raise
        finally:
            latency_ms = (_time.perf_counter() - _t0) * 1000
            try:
                from app.observability.llm_logger import log_llm_call
                log_llm_call(
                    model=self._model,
                    prompt_tokens=result.get("prompt_tokens", 0),
                    completion_tokens=result.get("completion_tokens", 0),
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_msg,
                    call_type=call_type,
                    session_id=session_id,
                    ab_variant=ab_variant,
                )
            except Exception:
                pass  # logging must never break the pipeline

        return result

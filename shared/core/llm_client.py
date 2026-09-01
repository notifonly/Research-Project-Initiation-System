from __future__ import annotations

import json
from typing import Any, Optional

from shared.core.config import settings
from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase, TokenBudget

logger = get_logger()

_llm = None


def get_llm():
    global _llm
    if _llm is None:
        try:
            import litellm

            litellm.drop_params = True
            _llm = litellm
        except ImportError:
            _llm = None
    return _llm


async def llm_complete(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    budget: Optional[TokenBudget] = None,
    phase: BudgetPhase = BudgetPhase.EXTRACTION,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[type] = None,
) -> str:
    """Call LLM via litellm. Returns raw text. Consumes token budget."""
    llm = get_llm()
    model = model or settings.llm_model
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.llm_temperature,
        "max_tokens": max_tokens or settings.llm_max_tokens,
    }
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    if settings.llm_base_url:
        kwargs["api_base"] = settings.llm_base_url
    if response_format is not None:
        kwargs["response_format"] = {"type": "json_object"}

    if llm is None:
        logger.warning("litellm not available, returning stub LLM response")
        return _stub_response(prompt, response_format)

    cache_key_parts = (
        model,
        system or "",
        prompt,
        str(temperature if temperature is not None else settings.llm_temperature),
        str(max_tokens or settings.llm_max_tokens),
    )

    if settings.llm_cache_enabled:
        try:
            from shared.core.cache import ResponseCache
            cache = await ResponseCache.get_instance()
            cached = await cache.get("llm", *cache_key_parts)
            if cached is not None:
                logger.debug("LLM cache hit")
                return cached
        except Exception:
            pass

    try:
        if budget:
            budget.set_phase(phase)
        resp = await llm.acompletion(**kwargs)
        text = resp.choices[0].message.content or ""
        if budget:
            usage = resp.usage
            if usage:
                budget.consume(usage.total_tokens, phase)

        if settings.llm_cache_enabled and text:
            try:
                from shared.core.cache import ResponseCache
                cache = await ResponseCache.get_instance()
                await cache.set("llm", text, settings.llm_cache_ttl_seconds, *cache_key_parts)
            except Exception:
                pass

        return text
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        if budget:
            budget.consume(100, phase)
        return _stub_response(prompt, response_format, str(e))


async def llm_structured(
    prompt: str,
    output_schema: type,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    budget: Optional[TokenBudget] = None,
    phase: BudgetPhase = BudgetPhase.EXTRACTION,
) -> Any:
    """Call LLM and parse JSON output. Returns dict or list depending on schema."""
    schema_hint = ""
    is_list = output_schema is list
    if is_list:
        schema_hint = "a JSON array"
    else:
        try:
            schema_dict = output_schema.model_json_schema()
            schema_hint = json.dumps(schema_dict, ensure_ascii=False)
        except Exception:
            schema_hint = output_schema.__name__

    full_prompt = f"{prompt}\n\nRespond with valid JSON matching this schema:\n{schema_hint}\n\nReturn ONLY JSON, no prose."
    raw = await llm_complete(
        full_prompt,
        system=system or "You are a bioinformatics research assistant. Output valid JSON only.",
        model=model,
        budget=budget,
        phase=phase,
        response_format=None if is_list else output_schema,
    )
    return _parse_json(raw)


def _parse_json(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    arr_start = raw.find("[")
    arr_end = raw.rfind("]")
    if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
        try:
            return json.loads(raw[arr_start : arr_end + 1])
        except json.JSONDecodeError:
            pass
    if arr_start != -1 and (arr_end == -1 or arr_end < arr_start):
        truncated = raw[arr_start:].rstrip()
        if truncated.endswith(","):
            truncated = truncated[:-1]
        try:
            return json.loads(truncated + "]")
        except json.JSONDecodeError:
            pass
    obj_start = raw.find("{")
    obj_end = raw.rfind("}")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        try:
            return json.loads(raw[obj_start : obj_end + 1])
        except json.JSONDecodeError:
            pass
    return {"_parse_error": True, "_raw": raw[:500]}


def _stub_response(prompt: str, response_format: Any, error: str = "") -> str:
    if response_format is not None:
        return json.dumps({"_stub": True, "_error": error or "litellm_unavailable", "_prompt_preview": prompt[:200]})
    return f"[STUB LLM RESPONSE] {error or 'litellm not available'}. Prompt: {prompt[:200]}"

import json
import re
from typing import TypeVar, Type
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.logger import logger

T = TypeVar("T", bound=BaseModel)

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMParsingError(Exception):
    """Raised when a model response cannot be coerced into the expected schema."""


def fix_json_syntax(text: str) -> str:
    """Repair common LLM JSON syntax errors like trailing commas, unquoted keys, single quotes."""
    if not text:
        return text

    # Remove trailing commas in objects and arrays: e.g. {"a": 1,} -> {"a": 1}
    repaired = re.sub(r',\s*([}\]])', r'\1', text)

    # Convert unquoted keys: e.g. {intent: "SELECT"} -> {"intent": "SELECT"}
    repaired = re.sub(r'(?<=[{\s,])([a-zA-Z0-9_]+)\s*:', r'"\1":', repaired)

    # Convert single quotes to double quotes if no double quotes in keys
    if "'" in repaired and '"' not in repaired:
        repaired = repaired.replace("'", '"')

    return repaired


def clean_llm_json(raw: str) -> str:
    """Strip code fences, stray control characters, and extract JSON object/array."""
    if not raw:
        return ""
    cleaned = _FENCE_PATTERN.sub("", raw).strip()
    cleaned = cleaned.replace("\x00", "")
    
    start_brace = cleaned.find("{")
    start_bracket = cleaned.find("[")
    
    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        end_brace = cleaned.rfind("}")
        if end_brace > start_brace:
            return cleaned[start_brace:end_brace + 1]
    elif start_bracket != -1:
        end_bracket = cleaned.rfind("]")
        if end_bracket > start_bracket:
            return cleaned[start_bracket:end_bracket + 1]
            
    return cleaned


async def call_llm_structured(
    prompt: str,
    schema: Type[T],
    llm_call_fn,
    fallback: T,
    model_name: str | None = None,
) -> T:
    """
    Calls the model, validates the response against `schema`, and retries
    with exponential backoff on malformed output. Returns `fallback` if all attempts fail.
    """
    @retry(
        reraise=False,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=3),
        retry=retry_if_exception_type(LLMParsingError),
    )
    async def _execute_with_retry():
        raw_response = await llm_call_fn(prompt, model_name=model_name)
        cleaned = clean_llm_json(raw_response)
        
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            repaired = fix_json_syntax(cleaned)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as exc:
                logger.warning(f"LLM JSON decode failed after repair: {exc}")
                raise LLMParsingError(str(exc)) from exc

        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            logger.warning(f"LLM Pydantic validation failed: {exc}")
            raise LLMParsingError(str(exc)) from exc

    try:
        result = await _execute_with_retry()
        return result if result is not None else fallback
    except Exception as exc:
        logger.error(f"Structured LLM call failed after retries: {exc}. Returning fallback.")
        return fallback
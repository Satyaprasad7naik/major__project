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


def clean_llm_json(raw: str) -> str:
    """Strip code fences and stray control characters the model may emit."""
    cleaned = _FENCE_PATTERN.sub("", raw).strip()
    cleaned = cleaned.replace("\x00", "")
    return cleaned


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type(LLMParsingError),
)
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
    try:
        raw_response = await llm_call_fn(prompt, model_name=model_name)
        cleaned = clean_llm_json(raw_response)
        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(f"LLM structured output failed validation, will retry: {exc}")
        raise LLMParsingError(str(exc)) from exc
    except Exception as exc:
        logger.error(f"Non-retriable LLM failure, returning fallback: {exc}")
        return fallback
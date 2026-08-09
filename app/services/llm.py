import time
import asyncio
from app.core.config import settings
from app.core.logger import logger

# Provider-agnostic imports
try:
    import openai
except ImportError:
    openai = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None


class LLMService:
    def __init__(self):
        # Priority: Qubrid > OpenAI > Gemini
        if getattr(settings, "QUBRID_API_KEY", None):
            if openai is None:
                raise ImportError("openai package is required for Qubrid API usage.")
            self.client = openai.AsyncOpenAI(
                api_key=settings.QUBRID_API_KEY,
                base_url=settings.QUBRID_BASE_URL,
                timeout=20.0
            )
            self.provider = "qubrid"
            self.model_name = getattr(settings, "QUBRID_MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
            logger.info(f"LLM Service initialized with Qubrid provider, model: {self.model_name}")
        elif getattr(settings, "OPENAI_API_KEY", None):
            if openai is None:
                raise ImportError("openai package is required for OPENAI_API_KEY usage.")
            self.client = openai.AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                timeout=20.0
            )
            self.provider = "openai"
            self.model_name = getattr(settings, "OPENAI_MODEL_NAME", "gpt-4o-mini")
            logger.info(f"LLM Service initialized with OpenAI provider, model: {self.model_name}")
        elif getattr(settings, "GEMINI_API_KEY", None):
            if genai is None:
                raise ImportError("google-generativeai package is required for GEMINI_API_KEY usage.")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.provider = "gemini"
            self.model_name = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                safety_settings=safety_settings
            )
            logger.info(f"LLM Service initialized with Gemini provider, model: {self.model_name}")
        else:
            print("Warning: No LLM API key found in settings.")
            self.provider = None
            self.model = None

    async def _call_openai_compatible(self, prompt: str, model_override: str = None) -> str:
        """Call OpenAI-compatible ChatCompletion (works for OpenAI, Ollama, Qubrid, etc.)."""
        response = await self.client.chat.completions.create(
            model=model_override or self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            stream=False,
        )
        return response.choices[0].message.content

    async def generate_response(self, prompt: str, model_name: str = None) -> str:
        if not self.provider:
            logger.error("LLM Service not configured (no API key found).")
            return "LLM Service not configured."

        selected_model = model_name or self.model_name
        logger.info(f"LLM [{self.provider}] using model [{selected_model}] generating response...")
        
        # Retry logic for rate-limit (429/503) – up to 5 attempts
        attempts = 0
        while attempts < 5:
            try:
                if self.provider in ("openai", "qubrid"):
                    res = await self._call_openai_compatible(prompt, model_override=selected_model)
                else:  # gemini
                    model_to_use = self.model
                    if model_name:
                        model_to_use = genai.GenerativeModel(
                            model_name=model_name,
                            safety_settings=[
                                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                            ]
                        )
                    
                    response = model_to_use.generate_content(prompt)
                    
                    if not response.candidates or response.candidates[0].finish_reason != 1:
                        if response.candidates and response.candidates[0].finish_reason == 3:
                            logger.warning(f"LLM response blocked by safety filters for model {selected_model}.")
                            return "Error: Response blocked by safety filters."
                        
                    res = response.text
                
                logger.info(f"LLM response received from [{selected_model}]. Snippet: {res[:50]}...")
                return res
            except Exception as e:
                err_msg = str(e).lower()
                if "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg or "503" in err_msg or "resourceexhausted" in err_msg or "limit reached" in err_msg:
                    attempts += 1
                    wait = 2 ** attempts
                    logger.warning(f"LLM rate limit / resource exhaustion encountered, retrying in {wait}s (attempt {attempts})")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"LLM Error: {str(e)}")
                return f"Error generating response: {str(e)}"
        logger.error("LLM service rate limit exceeded after multiple retries.")
        return "Error: LLM service rate limit exceeded after multiple retries."

llm_service = LLMService()

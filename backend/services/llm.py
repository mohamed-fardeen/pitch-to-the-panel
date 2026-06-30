import json
import logging
import os
from collections.abc import AsyncGenerator

import httpx
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from google import genai as google_genai
from google.genai import types
from openai import AsyncOpenAI

try:
    from backend.observability import trace_llm_call
except ImportError:
    # When run from backend/ as cwd (e.g. uvicorn main:app), the bare
    # path `observability` works. Fall back to it.
    from observability import trace_llm_call  # type: ignore[no-redef]

load_dotenv()
logger = logging.getLogger(__name__)

class LLMProvider:
    def __init__(self):
        # Pooled HTTP client for Ollama (and any other HTTP-based provider)
        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        self.anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) if os.getenv("ANTHROPIC_API_KEY") else None

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            self.gemini_client = google_genai.Client(api_key=gemini_api_key)
            self.gemini_model = "gemini-1.5-pro"
        else:
            self.gemini_client = None
            self.gemini_model = None

        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
        self.groq_client = AsyncOpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1") if os.getenv("GROQ_API_KEY") else None

    @staticmethod
    def _model_for_provider(provider: str) -> str:
        """Best-effort model name for a provider. Used for tracing."""
        if provider == "anthropic":
            return "claude-3-5-sonnet-latest"
        if provider == "openai":
            return "gpt-4o"
        if provider == "gemini":
            return "gemini-1.5-pro"
        if provider == "groq":
            return "llama-3.1-8b-instant"
        return "llama3.2"  # ollama default

    async def generate_response(self, system_prompt: str, user_prompt: str, provider: str = "ollama", stream: bool = False, max_tokens: int = 1024) -> str | AsyncGenerator[str, None]:
        if not provider:
            provider = "ollama"

        # Fallback chain: requested -> local ollama -> groq -> gemini -> fail
        provider_chain = [provider]
        if provider == "groq":
            provider_chain.extend(["ollama", "gemini"])
        elif provider == "gemini":
            provider_chain.extend(["ollama", "groq"])
        elif provider == "anthropic":
            provider_chain.extend(["ollama", "groq", "gemini"])
        else: # default ollama
            provider_chain.extend(["groq", "gemini"])

        # Trace this LLM call. The context manager is a no-op when
        # Langfuse is not configured, so this is zero-cost in dev.
        with trace_llm_call(
            name="llm.generate_response",
            provider=provider,
            model=self._model_for_provider(provider),
            metadata={
                "stream": stream,
                "max_tokens": max_tokens,
                "fallback_chain": provider_chain,
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
            },
            input_data={
                "system_prompt": system_prompt[:500] + ("..." if len(system_prompt) > 500 else ""),
                "user_prompt": user_prompt[:500] + ("..." if len(user_prompt) > 500 else ""),
            },
        ) as trace:
            for fallback_provider in provider_chain:
                try:
                    result = await self._generate_response_internal(
                        system_prompt, user_prompt, fallback_provider, stream, max_tokens
                    )
                    # If streaming, we can't easily update the trace
                    # with the final output (it's an async generator).
                    # For non-stream, we capture the full text.
                    if not stream and isinstance(result, str):
                        trace.update(
                            output=result[:2000] + ("..." if len(result) > 2000 else ""),
                            metadata={
                                "fallback_used": fallback_provider,
                                "output_chars": len(result),
                            },
                        )
                    else:
                        trace.update(
                            metadata={"fallback_used": fallback_provider, "streamed": True},
                        )
                    return result
                except Exception as e:
                    logger.warning(
                        "LLM provider %r failed: %s", fallback_provider, e,
                    )
                    # continue to next fallback

            # All providers failed
            trace.update(status="error", error="all providers failed")
            if stream:
                async def fallback_stream():
                    yield "I'm sorry, my systems are currently unavailable. Please check your API keys or local server."
                return fallback_stream()
            return "I'm sorry, my systems are currently unavailable. Please check your API keys or local server."

    async def _generate_response_internal(self, system_prompt: str, user_prompt: str, provider: str = "ollama", stream: bool = False, max_tokens: int = 1024) -> str | AsyncGenerator[str, None]:
        if provider == "anthropic":
            if not self.anthropic_client:
                raise ValueError("Anthropic API key not configured")

            if stream:
                return self._stream_anthropic(system_prompt, user_prompt, max_tokens)
            response = await self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            return response.content[0].text

        if provider == "gemini":
            if not self.gemini_client:
                raise ValueError("Gemini API key not configured")

            if stream:
                return self._stream_gemini(system_prompt, user_prompt, max_tokens)
            response = await self.gemini_client.aio.models.generate_content(
                model=self.gemini_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens
                )
            )
            return response.text

        if provider == "openai":
            if not self.openai_client:
                raise ValueError("OpenAI API key not configured")

            if stream:
                return self._stream_openai(system_prompt, user_prompt, max_tokens)
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens
            )
            return response.choices[0].message.content

        if provider == "groq":
            if not self.groq_client:
                raise ValueError("Groq API key not configured")

            if stream:
                return self._stream_groq(system_prompt, user_prompt, max_tokens)
            response = await self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens
            )
            return response.choices[0].message.content

        if provider == "ollama":
            if stream:
                return self._stream_ollama(system_prompt, user_prompt)
            return await self._sync_ollama(system_prompt, user_prompt)
        raise ValueError(f"Unknown provider: {provider}")

    async def _stream_anthropic(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        stream = await self.anthropic_client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            stream=True
        )
        async for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                text = event.delta.text
                if text:
                    yield text

    async def _stream_gemini(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        stream = await self.gemini_client.aio.models.generate_content(
            model=self.gemini_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens
            ),
            stream=True
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text

    async def _stream_openai(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        stream = await self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            stream=True,
            max_tokens=max_tokens
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    async def _stream_groq(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
        stream = await self.groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            stream=True,
            max_tokens=max_tokens
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    async def _sync_ollama(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": "llama3.2",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False
        }
        try:
            response = await self._http_client.post("http://localhost:11434/api/chat", json=payload, timeout=60.0)
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "")
            raise Exception(f"Ollama API returned non-200 status: {response.status_code}")
        except Exception as e:
            print(f"[OLLAMA SYNC] Error: {str(e)}")
            raise e

    async def _stream_ollama(self, system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
        payload = {
            "model": "llama3.2",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": True
        }
        try:
            async with self._http_client.stream("POST", "http://localhost:11434/api/chat", json=payload, timeout=60.0) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"[OLLAMA STREAM] Error: {str(e)}")
            raise e

    async def close(self) -> None:
        """Close the pooled HTTP client. Call on app shutdown."""
        await self._http_client.aclose()


llm_provider = LLMProvider()

import os
import json
import asyncio
import httpx
from typing import AsyncGenerator
from google import genai as google_genai
from google.genai import types
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

class LLMProvider:
    def __init__(self):
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

    async def generate_response(self, system_prompt: str, user_prompt: str, provider: str = "anthropic", stream: bool = False, max_tokens: int = 1024) -> str | AsyncGenerator[str, None]:
        # Define fallback chain
        provider_chain = [provider]
        if provider == "groq":
            provider_chain.append("anthropic")
        elif provider == "anthropic":
            provider_chain.append("groq")
        
        # Always attempt at least two
        if len(provider_chain) < 2 and provider != "gemini":
            provider_chain.append("gemini")

        last_error = None
        for attempt_provider in provider_chain:
            try:
                return await self._generate_response_internal(system_prompt, user_prompt, attempt_provider, stream, max_tokens)
            except Exception as e:
                last_error = e
                print(f"[LLM FALLBACK] {attempt_provider} failed: {type(e).__name__}: {str(e)[:100]}")
                continue

        # Both providers failed
        print(f"[LLM FALLBACK] All providers failed. Last error: {last_error}")
        if stream:
            async def empty_gen(): yield ""; return
            return empty_gen()
        
        raise last_error or Exception("All LLM providers failed")

    async def _generate_response_internal(self, system_prompt: str, user_prompt: str, provider: str = "anthropic", stream: bool = False, max_tokens: int = 1024) -> str | AsyncGenerator[str, None]:
        if provider == "anthropic":
            if not self.anthropic_client:
                raise ValueError("Anthropic API key not configured")
            
            if stream:
                return self._stream_anthropic(system_prompt, user_prompt, max_tokens)
            else:
                response = await self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                return response.content[0].text

        elif provider == "gemini":
            if not self.gemini_client:
                raise ValueError("Gemini API key not configured")
            
            if stream:
                return self._stream_gemini(system_prompt, user_prompt, max_tokens)
            else:
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.gemini_model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=max_tokens
                    )
                )
                return response.text

        elif provider == "openai":
            if not self.openai_client:
                raise ValueError("OpenAI API key not configured")
            
            if stream:
                return self._stream_openai(system_prompt, user_prompt, max_tokens)
            else:
                response = await self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content

        elif provider == "groq":
            if not self.groq_client:
                raise ValueError("Groq API key not configured")
            
            if stream:
                return self._stream_groq(system_prompt, user_prompt, max_tokens)
            else:
                response = await self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content

        elif provider == "ollama":
            if stream:
                return self._stream_ollama(system_prompt, user_prompt)
            else:
                return await self._sync_ollama(system_prompt, user_prompt)
        else:
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
                yield event.delta.text

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
            yield chunk.text

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
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

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
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    async def _sync_ollama(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": "llama3.2",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post("http://localhost:11434/api/chat", json=payload, timeout=60.0)
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
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("POST", "http://localhost:11434/api/chat", json=payload, timeout=60.0) as response:
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

llm_provider = LLMProvider()

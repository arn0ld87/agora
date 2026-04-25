"""
LLM Client Wrapper
Unified OpenAI format API calls
Supports Ollama num_ctx parameter to prevent prompt truncation
"""

import json
import os
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config
from .retry import llm_call_with_retry


class LLMClient:
    """LLM Client"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 300.0
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

        # Ollama context window size — prevents prompt truncation.
        # Read from env OLLAMA_NUM_CTX, default 8192 (Ollama default is only 2048).
        self._num_ctx = int(os.environ.get('OLLAMA_NUM_CTX', '8192'))
        # Ollama thinking toggle (Gemma 4, Qwen3, DeepSeek-R1, GPT-OSS).
        # Default false to keep latency low on long prompts.
        self._think = os.environ.get('OLLAMA_THINKING', 'false').lower() in ('1', 'true', 'yes')

        # Transient-failure retry knobs (Ollama Cloud sometimes 5xx-flaps).
        self._max_retries = int(os.environ.get('LLM_MAX_RETRIES', '3'))
        self._retry_initial_delay = float(os.environ.get('LLM_RETRY_INITIAL_DELAY', '1.0'))
        self._retry_max_delay = float(os.environ.get('LLM_RETRY_MAX_DELAY', '30.0'))

    def _is_ollama(self) -> bool:
        """Check if we're talking to an Ollama server."""
        return '11434' in (self.base_url or '')

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Send chat request

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count
            response_format: Response format (e.g., JSON mode)

        Returns:
            Model response text
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        # For Ollama: pass num_ctx via extra_body to prevent prompt truncation,
        # plus think flag to control reasoning output on capable models.
        if self._is_ollama():
            extra_body: Dict[str, Any] = {}
            if self._num_ctx:
                extra_body["options"] = {"num_ctx": self._num_ctx}
            extra_body["think"] = self._think
            kwargs["extra_body"] = extra_body

        response = llm_call_with_retry(
            self.client.chat.completions.create,
            max_retries=self._max_retries,
            initial_delay=self._retry_initial_delay,
            max_delay=self._retry_max_delay,
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        # Some models (like MiniMax M2.5, DeepSeek-R1) include <think>thinking content in response, need to remove
        content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
        return content

    def describe_image(
        self,
        image_b64: str,
        prompt: str,
        model: Optional[str] = None,
        mime: str = "image/png",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """
        Send a single image + prompt to a vision-capable model and return a
        plain-text description.

        Uses the OpenAI-compatible multimodal message shape:
            {"role": "user", "content": [
                {"type": "text", "text": ...},
                {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<b64>"}}
            ]}

        Works against Ollama Cloud vision models (e.g. gemini-3-flash-preview:cloud).
        """
        vision_model = model or os.environ.get('VISION_MODEL_NAME') or self.model
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            ],
        }]
        kwargs: Dict[str, Any] = {
            "model": vision_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self._is_ollama():
            extra_body: Dict[str, Any] = {"options": {"num_ctx": max(self._num_ctx, 8192)}}
            extra_body["think"] = False  # never want reasoning noise in vision output
            kwargs["extra_body"] = extra_body

        response = llm_call_with_retry(
            self.client.chat.completions.create,
            max_retries=self._max_retries,
            initial_delay=self._retry_initial_delay,
            max_delay=self._retry_max_delay,
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count

        Returns:
            Parsed JSON object
        """
        disable_json_mode = os.environ.get('LLM_DISABLE_JSON_MODE', '').lower() in ('1', 'true', 'yes')
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=None if disable_json_mode else {"type": "json_object"}
        )
        # Clean markdown code block markers
        cleaned_response = response.strip()
        # Robustly remove ```json ... ``` or just ``` ... ```
        cleaned_response = re.sub(r'^```(?:json)?\s*', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\s*```$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format from LLM: {cleaned_response}")

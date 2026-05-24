from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMClient:
    base_url: str
    model: str
    api_key_env: str
    max_retries: int = 2
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required for real API calls. "
                "Install dependencies with: pip install -r requirements.txt"
            ) from exc

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {self.api_key_env} is not set. "
                "Set it before running the experiment."
            )
        self.client: Any = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        enable_thinking: bool = False,
    ) -> str:
        last_error: Exception | None = None
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request_kwargs["extra_body"] = {"enable_thinking": bool(enable_thinking)}

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(**request_kwargs)
                content = response.choices[0].message.content
                return content or ""
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(2**attempt)
        raise RuntimeError(f"LLM request failed after retries: {last_error}")


def extract_score(text: str) -> int | None:
    patterns = [
        r"【\s*评分\s*[:：]\s*(\d{1,2})\s*】",
        r"评分\s*[:：]\s*(\d{1,2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            score = int(match.group(1))
            if 1 <= score <= 10:
                return score
    return None

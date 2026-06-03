from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import requests


@dataclass(slots=True)
class DeepSeekConfig:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int = 30


class DeepSeekClient:
    def __init__(
        self,
        config: DeepSeekConfig,
        http_post: Callable[..., object] = requests.post,
    ) -> None:
        self._config = config
        self._http_post = http_post

    def summarize_paper(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
    ) -> str:
        response = self._http_post(
            f"{self._config.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._config.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是科研论文助手。请使用简体中文输出 2-3 句总结，"
                            "只概括研究对象、方法或结果，不要编号，不要杜撰。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"标题：{title}\n"
                            f"摘要：{abstract}\n"
                            f"命中关键词：{', '.join(matched_keywords) or 'N/A'}"
                        ),
                    },
                ],
                "temperature": 0.2,
            },
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        if not content:
            raise ValueError("DeepSeek returned empty summary")
        return content

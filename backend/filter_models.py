"""OpenRouter 모델 카탈로그 검색 — 후보 모델의 정확한 ID·가격 확인용."""

import json
import sys

from pathlib import Path

CACHE = Path(__file__).parent / "_or_models_cache.json"
with CACHE.open(encoding="utf-8") as f:
    d = json.load(f)
ms = d.get("data", [])
print(f"total: {len(ms)}")

keywords = sys.argv[1:] or [
    "hermes",
    "mistral-large",
    "qwen3",
    "grok",
    "command-r",
    "exaone",
    "deepseek-v4",
    "deepseek/deepseek-v3.2",
    "claude-sonnet-4",
    "claude-opus-4",
]

for m in ms:
    mid = m.get("id", "").lower()
    if any(k.lower() in mid for k in keywords):
        p = m.get("pricing", {})
        ctx = m.get("context_length", "?")
        prompt_p = p.get("prompt", "?")
        comp_p = p.get("completion", "?")
        print(f"{m.get('id',''):65s} in={prompt_p:14s} out={comp_p:14s} ctx={ctx}")

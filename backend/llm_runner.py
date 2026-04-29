"""
LLM Runner — OpenAI / OpenRouter / Ollama 통합 호출

model_id 형식:
- "openai/<model>"           예: "openai/gpt-4o-mini"
- "openrouter/<vendor>/<m>"  예: "openrouter/anthropic/claude-sonnet-4.6"
- "ollama/<model>"           예: "ollama/qwen2.5:7b"

모든 라우팅 결과는 표준 LLMResponse(텍스트 + 메타) 반환.
JSON 응답은 parse_json_response()로 강건하게 파싱.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(".env.local", override=True)
    load_dotenv(".env", override=False)
except ImportError:
    pass


@dataclass
class LLMResponse:
    text: str
    model_id: str
    elapsed_sec: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _call_openai_sdk(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    *,
    temperature: float,
    json_mode: bool,
    timeout: int,
) -> Dict[str, Any]:
    """OpenAI SDK 사용 (OpenAI 직접 + OpenRouter 호환)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    return {
        "text": text,
        "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "raw": resp.model_dump(),
    }


def _call_ollama(
    model: str,
    system: str,
    user: str,
    *,
    temperature: float,
    json_mode: bool,
    timeout: int,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": temperature},
        "stream": False,
    }
    if json_mode:
        body["format"] = "json"

    r = requests.post(f"{host.rstrip('/')}/api/chat", json=body, timeout=timeout)
    r.raise_for_status()
    raw = r.json()
    return {
        "text": raw["message"]["content"],
        "input_tokens": raw.get("prompt_eval_count"),
        "output_tokens": raw.get("eval_count"),
        "raw": raw,
    }


def call_llm(
    model_id: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.7,
    json_mode: bool = True,
    timeout: int = 120,
) -> LLMResponse:
    """model_id 앞 prefix로 provider 라우팅."""
    t0 = time.monotonic()

    if model_id.startswith("openai/"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY 없음 (.env.local 확인)")
        result = _call_openai_sdk(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            model=model_id[len("openai/"):],
            system=system,
            user=user,
            temperature=temperature,
            json_mode=json_mode,
            timeout=timeout,
        )

    elif model_id.startswith("openrouter/"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY 없음 (.env.local 확인)")
        result = _call_openai_sdk(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model_id[len("openrouter/"):],
            system=system,
            user=user,
            temperature=temperature,
            json_mode=json_mode,
            timeout=timeout,
        )

    elif model_id.startswith("ollama/"):
        result = _call_ollama(
            model=model_id[len("ollama/"):],
            system=system,
            user=user,
            temperature=temperature,
            json_mode=json_mode,
            timeout=timeout,
        )

    else:
        raise ValueError(f"알 수 없는 model_id prefix: {model_id}")

    return LLMResponse(
        text=result["text"],
        model_id=model_id,
        elapsed_sec=time.monotonic() - t0,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        raw=result["raw"],
    )


def parse_json_response(text: str) -> Dict[str, Any]:
    """JSON 모드라도 가끔 ```json 펜스나 서두가 붙어오므로 강건 파싱."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        text = text[first : last + 1]
    return json.loads(text)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("사용법: python -m backend.llm_runner <model_id> [질문]")
        print('예: python -m backend.llm_runner openai/gpt-4o-mini "한국 박물관 한 곳 추천 (JSON: {name, why})"')
        sys.exit(1)

    model_id = sys.argv[1]
    user_prompt = (
        sys.argv[2]
        if len(sys.argv) > 2
        else 'JSON으로 답: {"name": "박물관 이름", "why": "이유"}'
    )

    print(f"== {model_id} ==")
    resp = call_llm(
        model_id=model_id,
        system="당신은 도움 되는 어시스턴트입니다. JSON으로만 답하세요.",
        user=user_prompt,
        temperature=0.3,
        json_mode=True,
    )
    print(f"elapsed: {resp.elapsed_sec:.2f}s")
    print(f"tokens: in={resp.input_tokens} out={resp.output_tokens}")
    print(f"text: {resp.text}")
    try:
        parsed = parse_json_response(resp.text)
        print(f"parsed: {parsed}")
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 실패: {e}")

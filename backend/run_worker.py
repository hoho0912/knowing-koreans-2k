"""
측정 워커 — gateway.py가 systemd-run으로 띄우는 백그라운드 프로세스.

spec.json 한 개를 입력받아 페르소나 샘플링 → LLM 호출 루프 → 보고서 컴파일을
수행하며 status.json을 주기적으로 atomic write로 갱신. 브라우저가 닫혀도
이 프로세스는 systemd 관리하에 계속 돌아간다.

흐름:
  1. spec.json 로드
  2. status.json 초기화 (phase=starting)
  3. validate_spec() — drift 시 phase=error로 즉시 abort
  4. 페르소나 풀 로드 (1M행)
  5. 샘플링 → personas.csv
  6. persona × model 루프
     - 호출마다 result.csv append
     - 5건마다 status.json 갱신 (n_done, avg, eta)
     - SIGTERM 받으면 phase=cancelled로 종료
  7. 보고서 LLM 호출 → report.md
  8. weasyprint로 report.pdf
  9. pypdfium2로 report.png (1페이지)
  10. zipfile로 sources.zip (spec + personas + result + report)
  11. phase=done

CLI: python -m backend.run_worker /path/to/run_dir
"""

from __future__ import annotations

import io
import json
import os
import re
import signal
import sys
import textwrap
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm_runner import call_llm, parse_json_response  # noqa: E402
from backend.persona_sampler import load_all_personas, sample_personas  # noqa: E402
from backend.prompt_builder import (  # noqa: E402
    CLUSTER_ANALYSIS_SYSTEM,
    CLUSTER_ANALYSIS_USER_TEMPLATE,
    CROSS_CLUSTER_DIFF_SYSTEM,
    CROSS_CLUSTER_DIFF_USER_TEMPLATE,
    INSIGHT_SINGLE_SYSTEM,
    INSIGHT_SINGLE_USER_TEMPLATE,
    RAW_RETRIEVAL_SYSTEM,
    RAW_RETRIEVAL_USER_TEMPLATE,
    SYNTHESIS_SYSTEM,
    SYNTHESIS_USER_TEMPLATE,
    SYSTEM_TEMPLATE,
    render_template,
    validate_insight_prompt_schema,
)
from backend.run_validate import validate_spec  # noqa: E402

KST = timezone(timedelta(hours=9))
PERSONA_DIR = PROJECT_ROOT / "data" / "personas"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# 페르소나 province(단축) ↔ GeoJSON name(풀) 매핑.
# Nemotron 데이터에 "전북"·"전라남"·"경상남" 같은 단축·풀 형태가 섞여 있어
# 양쪽을 모두 GeoJSON 풀 이름에 흡수.
PROVINCE_TO_GEO: Dict[str, str] = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원도",
    "충청북": "충청북도",
    "충청남": "충청남도",
    "전북":   "전라북도",
    "전라북": "전라북도",
    "전남":   "전라남도",
    "전라남": "전라남도",
    "경상북": "경상북도",
    "경상남": "경상남도",
    "제주":   "제주특별자치도",
}

AGE_BUCKET_ORDER: List[str] = ["~19", "20대", "30대", "40대", "50대", "60+"]

# ─────────────────────────────────────────────────────────
# 보고서 생성 — gateway.py와 동일한 톤·구조 (큐레이터 비평가)
# ─────────────────────────────────────────────────────────

MODEL_LABELS: Dict[str, str] = {
    "openrouter/qwen/qwen3-max":               "Qwen3 Max (Alibaba)",
    "openrouter/nousresearch/hermes-4-405b":   "Hermes 4 405B (NousResearch)",
    "openrouter/anthropic/claude-haiku-4.5":   "Claude Haiku 4.5 (Anthropic)",
    "openrouter/nousresearch/hermes-4-70b":    "Hermes 4 70B (NousResearch)",
    "openrouter/qwen/qwen3.6-max-preview":     "Qwen3.6 Max Preview (Alibaba)",
    "openrouter/qwen/qwen3.6-plus":            "Qwen3.6 Plus (Alibaba)",
    "openrouter/mistralai/mistral-large-2512": "Mistral Large (Mistral, 프랑스)",
    "openrouter/anthropic/claude-sonnet-4.6":  "Claude Sonnet 4.6 (Anthropic)",
    "openrouter/openai/gpt-4o-mini":           "GPT-4o mini (OpenAI)",
    "openrouter/google/gemini-2.5-flash":      "Gemini 2.5 Flash (Google)",
    "openrouter/deepseek/deepseek-v4-flash":   "DeepSeek v4 Flash (DeepSeek)",
    "openrouter/x-ai/grok-4-fast":             "Grok 4 Fast (xAI)",
    "openrouter/cohere/command-a":             "Cohere Command A (Cohere)",
    "openrouter/anthropic/claude-opus-4.7":    "Claude Opus 4.7 (Anthropic)",
    "openrouter/cognitivecomputations/dolphin-mistral-24b-venice-edition:free":
                                                "Dolphin Mistral 24B (Cognitive Computations, uncensored)",
}


def model_label(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id)


DYNAMIC_USER_TEMPLATE = textwrap.dedent("""\
[배경]
{context}

[질문]
{questions}

응답은 JSON 한 개로만 답해주세요. 다른 설명·인사·서두 없이 JSON만.

아래 [응답 형식 정의]는 각 키가 요구하는 응답 타입·범위를 알려주는 안내입니다.
응답 형식 정의 자체를 그대로 복사해 답하지 마세요.
각 키에 schema가 요구하는 **실제 응답값**(정수·옵션 문자열·자유 서술 등)만
값으로 담아 [응답 예시] 형태로 답하세요.

[응답 형식 정의]
{schema}

[응답 예시 — 정확히 이 모양으로 답하세요]
{example}
""")


# schema 정의에서 사용되는 키들 — dict-wrap 응답 패턴 인식에 사용.
# 응답값이 dict이고 본 키 중 2개 이상 보유하면 hermes-4-405b 류의 nested
# wrap 패턴으로 인식하고 description leaf 를 응답값으로 unwrap.
_SCHEMA_DEF_KEYS = frozenset({
    "type", "scale", "options", "enum", "description",
    "min_length", "max_length",
})


def _unwrap_dict_response(v: Any) -> Any:
    """dict-wrap 응답 패턴이면 description leaf 추출, 단순 값이면 그대로 반환.

    배경: hermes-4-405b 가 모든 응답을 nested dict 로 감싸서 회신하는 패턴.
    예) {"type": "integer", "scale": "1~5 Likert ...", "description": 2}
        ↑ 이 객체에서 진짜 응답값은 description 필드의 2.

    인식 규칙: v 가 dict 이고 _SCHEMA_DEF_KEYS 중 2개 이상 보유하면
    nested wrap 으로 인식 → description leaf 반환. description 이 없으면
    원본 dict 그대로 반환 (검증 단에서 schema-echo 로 fail 처리).

    knowing-koreans 2026-05-06 외부 리뷰 #2 데이터 테스트로 발견된 패턴.
    """
    if not isinstance(v, dict):
        return v
    overlap = _SCHEMA_DEF_KEYS & set(v.keys())
    if len(overlap) < 2:
        return v
    if "description" not in v:
        return v
    return v["description"]


def _try_int_in_schema_range(v: Any, t: str, scale: str) -> Optional[int]:
    """정수 변환 + likert/integer scale 범위 검증. 통과 시 int, 실패 시 None.

    frontend-obs/src/data/scenario.json.py:to_int_in_range / _detect_schema 와
    동일 분류로 동작 — type=likert_5/likert/integer는 [1,5], likert_7는 [1,7],
    또는 scale 텍스트의 '1~5', '1-7' 등을 정규식으로 추출.
    """
    try:
        if isinstance(v, str):
            m = re.search(r"-?\d+", v)
            if not m:
                return None
            n = int(m.group(0))
        elif isinstance(v, bool):
            return None
        elif isinstance(v, (int, float)):
            if isinstance(v, float) and v != v:  # NaN
                return None
            n = int(v)
        else:
            return None
    except (ValueError, TypeError):
        return None

    if t == "likert_7":
        lo, hi = 1, 7
    elif t in ("likert_5", "likert"):
        lo, hi = 1, 5
    else:
        m = re.search(r"(\d+)\s*[-~∼]\s*(\d+)", str(scale))
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
        else:
            keys = sorted({int(k) for k in re.findall(r"(\d+)\s*=", str(scale))})
            if len(keys) >= 2:
                lo, hi = keys[0], keys[-1]
            else:
                lo, hi = 1, 5  # default

    return n if lo <= n <= hi else None


def validate_response_against_schema(
    parsed: Dict[str, Any],
    schema_block: str,
) -> Optional[str]:
    """parse_json_response 결과가 schema_block 정의대로 응답됐는지 검증.

    None 반환 = PASS. str 반환 = error reason (worker가 ok=False로 기록).

    검증 분류 (frontend-obs loader 와 동일):
      - 응답값이 dict: schema echo 사고 (모델이 schema 정의 자체를 회신) → fail
      - numeric (integer / likert / likert_5 / likert_7 또는 scale 안 'likert'):
        정수 변환 + 범위 검증
      - categorical (single_choice / multi_choice 또는 options 보유):
        options 안에 포함되는지 검증
      - freetext (free_text / freetext / text / string + min_length 또는
        '자유'/'서술' 표지): min_length 검증 + description echo 검출

    schema_block 파싱 실패·미정의 시 검증 skip(PASS) — 호환성 유지.
    외부 리뷰 #2 (knowing-koreans 2026-05-06) 도입.
    """
    if not schema_block or not schema_block.strip():
        return None
    try:
        schema = json.loads(schema_block)
    except json.JSONDecodeError:
        return None
    if not isinstance(schema, dict):
        return None

    fails: List[str] = []
    for key, q_def in schema.items():
        if not isinstance(q_def, dict):
            continue  # validate_spec이 별도 차단 (외부 리뷰 #5)
        if key not in parsed:
            continue  # 응답 누락은 별도 영역 (parse 단계의 키 결손)

        # B안 — dict-wrap 응답이면 description leaf 추출 후 검증
        v = _unwrap_dict_response(parsed[key])
        t = (q_def.get("type") or "").lower().strip()

        if isinstance(v, dict):
            fails.append(f"{key}=dict(schema-echo)")
            continue

        # description echo 검출 — unwrap된 값이 schema_block의 description과 같으면
        # 모델이 답을 안 하고 schema 정의를 그대로 회신한 사고
        expected_desc = (q_def.get("description") or "").strip()
        if expected_desc and isinstance(v, str) and v.strip() == expected_desc:
            fails.append(f"{key}=description-echo")
            continue

        scale = q_def.get("scale", "")
        is_numeric = (
            t in ("integer", "likert", "likert_5", "likert_7")
            or "likert" in str(scale).lower()
        )
        if is_numeric:
            if _try_int_in_schema_range(v, t, scale) is None:
                preview = repr(v)[:30]
                fails.append(f"{key}={preview}(non-numeric/out-of-range)")
            continue

        options = q_def.get("options") or q_def.get("enum")
        if t in ("single_choice", "multi_choice") or (
            isinstance(options, list) and len(options) > 0
        ):
            if isinstance(options, list) and options:
                opts_str = [str(o) for o in options]
                if t == "multi_choice" and isinstance(v, list):
                    bad = [str(x) for x in v if str(x) not in opts_str]
                    if bad:
                        fails.append(f"{key} bad-options:{bad[:3]}")
                else:
                    if str(v).strip() not in opts_str:
                        preview = repr(v)[:30]
                        fails.append(f"{key}={preview}(not-in-options)")
            continue

        if t in ("free_text", "freetext", "text", "string"):
            min_len = q_def.get("min_length")
            if min_len:
                v_str = str(v) if v is not None else ""
                if len(v_str) < int(min_len):
                    fails.append(f"{key}=len{len(v_str)}<min{min_len}")
                    continue
            desc = (q_def.get("description") or "").strip()
            if desc and isinstance(v, str) and v.strip() == desc:
                fails.append(f"{key}=description-echo")
            continue

    if fails:
        head = ", ".join(fails[:3])
        tail = f" (+{len(fails) - 3} more)" if len(fails) > 3 else ""
        return f"schema fail: {head}{tail}"
    return None


def build_response_example(schema_block: str) -> str:
    """schema_block(JSON)에서 LLM에 보여줄 응답 예시 JSON을 자동 생성.

    각 키의 값은 placeholder 문자열로 채워지며, LLM이 placeholder를 그대로
    복사하지 않도록 "<...>" 꺾쇠 기호로 감싼다. type/scale/options 정보를
    placeholder 텍스트에 함께 노출해 LLM이 정확한 응답값을 생성하도록 유도.
    """
    try:
        schema = json.loads(schema_block) if schema_block else {}
    except json.JSONDecodeError:
        return "{}"
    if not isinstance(schema, dict):
        return "{}"

    example: Dict[str, Any] = {}
    for key, defn in schema.items():
        if not isinstance(defn, dict):
            example[key] = "<응답값>"
            continue
        t = defn.get("type", "string")
        opts = defn.get("options") or defn.get("enum") or []
        scale = defn.get("scale", "")
        if t == "integer":
            placeholder = f"<정수 — {scale}>" if scale else "<정수>"
            example[key] = placeholder
        elif opts:
            opts_str = " / ".join(str(o) for o in opts)
            example[key] = f"<다음 중 하나: {opts_str}>"
        else:
            min_len = defn.get("min_length")
            max_len = defn.get("max_length")
            if min_len or max_len:
                example[key] = f"<자유 서술 ({min_len or 0}~{max_len or '제한 없음'}자)>"
            else:
                example[key] = "<자유 서술>"
    return json.dumps(example, ensure_ascii=False, indent=2)

REPORT_SYSTEM = textwrap.dedent("""당신은 박물관·문화 분야 큐레이터를 옆에서 돕는 비평가입니다.
큐레이터는 합성 페르소나·다중 LLM의 응답을 통해, **자기가 미처 떠올리지 못한
관점·가설**을 발견하고 싶어합니다.

중요: **본 응답은 보고서의 "해석·인사이트" 부분만 담당합니다.** 측정 개요,
페르소나 분포, 응답자 속성 축별 분포 표, 원본 질문·스키마·명세는 별도 코드에서
결정론적으로 생성되어 본 응답의 앞뒤에 자동으로 붙습니다. 따라서 본 응답에서는
통계 표를 다시 그릴 필요 없고, 아래 네 섹션만 작성해 주세요. 부록·통계 표는
만들지 마세요 — 코드가 만듭니다.

다음 원칙을 지키세요:
- 합성 페르소나의 응답은 여론조사가 아닙니다. 단언하지 말고
  "이 모델·이 표본에서는 …" 같이 한정해 말씀해 주세요.
- 영어 시스템 용어를 사용하지 마세요. 'demographic', 'segment', 'sample',
  'cohort' 같은 영어 단어 대신 '응답자 속성', '응답자 그룹', '표본'처럼
  우리말로 표현해 주세요. ('페르소나', '모델', '시뮬레이션'은 우리말로
  굳어진 외래어이므로 사용 가능합니다.)
- "핵심 발견" 표의 첫 번째 열(발견 라벨)에는 분석 결론·해석·수치를 적지
  마세요. 중립적인 차원 이름만 적습니다. 예시:
    · 권장: "01. 전체 응답 분포"
    · 금지: "01. 호감도는 5점 만점에 평균 2.78점"
    · 권장: "02. 학력별 격차"
    · 금지: "02. 학력에 따른 호감도 격차가 가장 큰 신호"
  분석 결론·수치는 두 번째 "내용" 열에 적습니다.
- 추상적 관점 진술("관람객은 다양하게 반응했다")은 피하세요. 대신
  큐레이터가 바로 사용할 수 있는 구체적 형태로 제시해 주세요. 예시:
  · SNS 마케팅 카피의 톤·문구 (대상 응답자 그룹 명시)
  · 홍보 포스터·메인 비주얼에서 강조할 지점
  · 큐레이션 동선·섹션 배치 방향
  · 도슨트 소개에서 강조할 부분
  · 전시 개막식·교육 프로그램의 주제어
- 모델 균질화·사회적 바람직성 편향 가능성을 한 줄 언급해 주세요.
- 응답수가 작은 응답자 그룹별 분석은 "N이 작아 신호로 보기 어렵다"고
  명시해 주세요.
- 각 페르소나는 명시적인 속성(거주지·연령대·성별·학력·혼인 상태·직업)을
  이미 가지고 있고, 본 자료의 응답 샘플에 그 속성이 함께 적혀 있습니다.
  따라서 응답 본문 텍스트만 보고 "고령 추정", "중산층 추정", "지방민으로
  보임" 같이 짐작·추정하는 표기는 사용하지 마세요. 정확한 속성이 자료에
  있으므로 그대로 인용하시면 됩니다.
- 응답을 직접 인용할 때는 모델명과 함께 페르소나 속성을 그대로 적어 주세요.
  예시: "(Hermes 4 70B · 60대 여성 · 전라남도 · 고졸)"
- 리커트 응답코드(1, 2, 3, 4, 5)는 "점수"가 아니라 응답을 수치화한 코드입니다.
  "1점/5점" 같은 표기는 5점이 더 좋은 것처럼 가치 판단을 시사하므로 피해
  주세요. "Q1 평균 2.28(5점 척도, 1=매우 반대)" 또는 "Q1=2가 41건"처럼
  코드 의미를 함께 전달하거나 숫자만 사용해 주세요.
""")


REPORT_USER_TEMPLATE = textwrap.dedent("""아래는 이번 측정의 결정론적 팩트 자료입니다. 이 팩트를 그대로 다시 표로
그려 답하지 마세요 — 코드가 본 응답 위아래에 측정 개요·축별 분포·부록을
자동으로 붙입니다. 본 응답에는 **해석·가설·인사이트**만 담아 주세요.

## 측정 주제
{topic}

## LLM에 주입한 컨텍스트
{context}

## 질문
{questions}

## 표본 페르소나 응답자 속성 분포 (N={n_personas})
{persona_dist}

## 모델별 응답 통계 (성공 응답만)
{stats}

{samples_block}

---

위 자료를 바탕으로 **다음 네 섹션만** 마크다운으로 작성해 주세요.
섹션 헤더는 반드시 아래 네 가지를 그대로 사용하세요(번호 없이).
부록·통계 표·축별 분포 표는 절대 만들지 마세요.

## 핵심 발견
표 형식. 첫 번째 열(발견 라벨)은 중립적인 차원 이름만 적고, 분석 결론·수치는
두 번째 "내용" 열에 적습니다. 5~8개 행 권장.

| 발견 | 내용 |
|---|---|
| 01. 전체 응답 분포 | (수치 + 해석) |
| 02. (차원 이름) | … |
| … | … |

## 큐레이터 관점·가설
3~5개. SNS 카피, 홍보 포스터 강조점, 큐레이션 방향, 도슨트 톤, 교육 프로그램
주제어 등 큐레이터가 바로 적용 가능한 형태로 제시. 대상 응답자 그룹도 함께
명시해 주세요.

## 곱씹을 만한 응답
2~3개. 특이하거나 큐레이터가 곱씹어볼 만한 응답을 raw 텍스트와 함께 인용.
어떤 모델·어떤 응답자 속성의 응답인지 같이 적어 주세요.

## 다음에 던져볼 질문·가설
3~5개. 이 측정이 답한 것이 아니라 새로 떠올리게 한 질문.
""")



# ─────────────────────────────────────────────────────────
# SIGTERM 핸들러 — 큐레이터가 [측정 취소] 누르면 systemctl stop이 보내옴
# ─────────────────────────────────────────────────────────
CANCEL = False


def _handle_sigterm(signum, frame):
    global CANCEL
    CANCEL = True


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


# ─────────────────────────────────────────────────────────
# status.json — partial read 방지 위해 tmp + os.replace
# ─────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def write_status(run_dir: Path, status: Dict[str, Any]) -> None:
    status["updated_at"] = _now_iso()
    tmp = run_dir / "status.json.tmp"
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, run_dir / "status.json")


# ─────────────────────────────────────────────────────────
# 코드 생성 보고서 섹션 (결정론적 — LLM 호출 없음)
# ─────────────────────────────────────────────────────────

# 수도권/비수도권 binary axis
SUDOGWON_PROVINCES = {"서울특별시", "서울", "경기도", "경기", "인천광역시", "인천"}


def province_to_region(p: Any) -> str:
    """거주 시도 → 수도권/비수도권 binary."""
    return "수도권" if str(p).strip() in SUDOGWON_PROVINCES else "비수도권"


def parse_questions_text(qtext: str) -> Dict[int, str]:
    """'1) ...\\n2) ...' 형식을 {1: '...', 2: '...'}로 변환."""
    out: Dict[int, str] = {}
    if not qtext:
        return out
    for m in re.finditer(
        r"^(\d+)\)\s*(.+?)(?=^\d+\)|\Z)",
        qtext, re.MULTILINE | re.DOTALL,
    ):
        text = m.group(2).strip().splitlines()[0].strip()
        out[int(m.group(1))] = text
    return out


def _topic_short(topic: str, limit: int = 60) -> str:
    """긴 주제는 limit자에서 자르고 …을 붙임."""
    if not topic:
        return ""
    first_line = topic.strip().splitlines()[0].strip()
    if len(first_line) > limit:
        return first_line[:limit] + "…"
    return first_line


def _format_kst_date(created_at: str, with_time: bool = False) -> str:
    """spec.created_at(ISO) → KST 날짜 (또는 날짜+시간)."""
    if not created_at:
        return ""
    try:
        s = created_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # spec.created_at에 timezone 정보가 없으면 UTC로 간주.
            # (과거 측정은 datetime.now().isoformat() 으로 KVM 로컬타임을
            #  naive하게 기록 — KVM은 UTC tz라 결과적으로 UTC 기준이 맞다.
            #  현재 측정부터는 gateway가 KST aware로 기록.)
            dt = dt.replace(tzinfo=timezone.utc)
        kst_dt = dt.astimezone(KST)
        return kst_dt.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")
    except Exception:
        return created_at[:16].replace("T", " ") if with_time else created_at[:10]


def compose_header(
    spec: Dict[str, Any],
    n_personas: int,
    n_models: int,
    n_responses: int,
) -> str:
    """보고서 제목 + 시나리오 메타 + 도입 한 줄 캡션."""
    lines: List[str] = []
    topic_short = _topic_short(spec.get("topic", ""), limit=60)
    date_str = _format_kst_date(spec.get("created_at", ""), with_time=False)

    lines.append("# knowing-koreans · 시뮬레이션 분석 보고서")
    lines.append("")
    if topic_short:
        lines.append(f"**시나리오**: {topic_short}")
        lines.append("")
    if date_str:
        lines.append(f"**측정일**: {date_str}")
        lines.append("")
    lines.append(
        f"**규모**: AI 페르소나 {n_personas}명 × {n_models}개 모델 → 응답 {n_responses}건"
    )
    lines.append("")
    lines.append(
        "본 보고서는 응답자 속성(연령·학력·지역·성별·혼인 등)을 분류 축으로 "
        "작성되었습니다. AI 응답을 정확도 예측이 아니라 \"어떤 응답자 그룹이 "
        "어떤 측면에 반응하는가\"의 관점·가설 발생 도구로 활용해 주세요."
    )
    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# 보고서 시각화는 Observable Framework 빌드 산출물(observable/)이 SSOT.
# 옛 matplotlib 차트 함수(_setup_korean_font, render_appeal_chart,
# render_age_pyramid, render_korea_map, render_response_distribution,
# render_response_by_axis, render_response_by_model, render_overview_charts,
# _detect_response_columns, _select_primary_response_col,
# _likert_labels_from_scale, _classify_urban)는 frontend-obs/src/data/scenario.json.py
# + frontend-obs/src/index.md 로 이전. 본 모듈에서는 측정 결과를 run_dir 에 저장만
# 한 뒤 npx observable build 를 호출해 정적 사이트(observable/index.html)를 생성한다.
# ─────────────────────────────────────────────────────────


def compose_overview(
    spec: Dict[str, Any],
    df_personas: pd.DataFrame,
    df_result: pd.DataFrame,
    run_dir: Optional[Path] = None,
) -> str:
    """## 측정 개요 — 측정일/시나리오/페르소나 출처/추출 방식/페르소나 수/응답수/속성 분포/질문 수."""
    lines: List[str] = []
    n = spec.get("n", 0)
    seed = spec.get("seed", 42)
    models = spec.get("models", [])
    n_total = len(df_result)

    if "ok" in df_result.columns:
        ok_df = df_result[df_result["ok"] == True]  # noqa: E712
    else:
        ok_df = df_result
    n_ok = len(ok_df)
    success_rate = f"{n_ok / n_total * 100:.1f}%" if n_total else "0%"

    date_str = _format_kst_date(spec.get("created_at", ""), with_time=True)
    questions = spec.get("questions", "") or ""
    q_count = len(parse_questions_text(questions))
    topic_short = _topic_short(spec.get("topic", ""), limit=60)

    lines.append("## 측정 개요")
    lines.append("")
    lines.append(
        "이번 측정에 사용된 자료의 요약입니다. 응답자 속성 분포는 보고서 "
        "본문의 축별 분포 표와 함께 읽어 주세요."
    )
    lines.append("")
    lines.append("| 항목 | 내용 |")
    lines.append("|---|---|")
    if date_str:
        lines.append(f"| 측정일 | {date_str} (KST) |")
    if topic_short:
        lines.append(f"| 시나리오 | {topic_short} |")
    lines.append("| 페르소나 출처 | NVIDIA Nemotron-Personas-Korea (한국 인구통계 합성 페르소나) |")

    # 추출 방식 — filters / stratify_by 적용 시 한 줄로 명시
    filters_dict = spec.get("filters", {}) or {}
    filter_parts: List[str] = []
    if filters_dict.get("province"):
        filter_parts.append(f"지역={filters_dict['province']}")
    if filters_dict.get("sex"):
        filter_parts.append(f"성별={filters_dict['sex']}")
    if filters_dict.get("age_min"):
        filter_parts.append(f"나이≥{filters_dict['age_min']}")
    age_max_val = filters_dict.get("age_max")
    if age_max_val and age_max_val < 120:
        filter_parts.append(f"나이≤{age_max_val}")
    if filters_dict.get("education_level"):
        filter_parts.append(f"학력={filters_dict['education_level']}")
    if filters_dict.get("occupation"):
        filter_parts.append(f"직업={filters_dict['occupation']}")
    stratify_by = filters_dict.get("stratify_by")
    stratify_label_map = {"province": "지역", "age_bucket": "연령대", "sex": "성별"}

    if stratify_by:
        s_label = stratify_label_map.get(stratify_by, stratify_by)
        lines.append(
            f"| 추출 방식 | {s_label} 균등 분배 + 시드 고정 무작위 (seed={seed}) |"
        )
    else:
        lines.append(f"| 추출 방식 | 시드 고정 무작위 추출 (seed={seed}) |")

    if filter_parts:
        lines.append(f"| 인구 필터 | {' · '.join(filter_parts)} |")
    lines.append(f"| 페르소나 수 | {n}명 |")
    lines.append(f"| 시뮬레이션 모델 수 | {len(models)}개 |")
    lines.append(f"| 응답 수 (페르소나 × 모델) | {n_total}건 |")
    lines.append(f"| 성공 응답 | {n_ok}건 ({success_rate}) |")
    lines.append(f"| 질문 수 | {q_count}개 |")

    # 페르소나 응답자 속성 분포 — 같은 표 안에 압축 행으로
    if df_personas is not None and len(df_personas) > 0:
        dist_specs = [
            ("sex", "성별 분포"),
            ("age_bucket", "연령대 분포"),
            ("education_level", "학력 분포"),
            ("marital_status", "혼인 분포"),
        ]
        for col, label in dist_specs:
            if col in df_personas.columns:
                vc = df_personas[col].astype(str).value_counts()
                summary = ", ".join(f"{val} {cnt}명" for val, cnt in vc.items())
                lines.append(f"| {label} | {summary} |")
    lines.append("")

    lines.append("**시뮬레이션 모델 목록:**")
    lines.append("")
    for m in models:
        lines.append(f"- {model_label(m)}")
    lines.append("")

    # 인포그래픽은 Observable Framework 빌드 산출물(observable/index.html)에서 노출.
    # report.md 본문에는 차트를 PNG로 박지 않는다(SSOT는 Observable).

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# (구) 응답자 속성 축별 분포 hardcoded 헬퍼 — 폐기
#
# 이전에는 _detect_numeric_range / _parse_int_in_range / compose_axis_breakdown으로
# 질문 type(integer/likert_5/likert_7/single_choice/free_text)별 분기 표를 코드로
# 생성했으나, 문항 type이 늘 때마다 분기를 추가해야 하는 땜질 구조였음.
# 인사이트 LLM이 schema와 raw 응답을 직접 보고 analysis_tables를 자율 결정하는
# 방식으로 대체. 본 영역에는 더 이상 코드 표 생성 함수를 두지 않는다.
# ─────────────────────────────────────────────────────────


def split_insights(insights_md: str) -> Tuple[str, str]:
    """LLM 산출 markdown을 보고서의 위·아래 두 영역으로 분리.

    위쪽: ## 응답 분석 + ## 핵심 발견 + ## 큐레이터 관점·가설
    아래쪽: ## 곱씹을 만한 응답 + ## 다음에 던져볼 질문·가설

    분리 마커: '## 곱씹을 만한 응답'.
    LLM이 이 헤더를 안 만들었으면 전체를 위쪽에 두고 아래쪽은 빈 문자열.
    """
    if not insights_md:
        return "", ""
    marker = "## 곱씹을 만한 응답"
    idx = insights_md.find(marker)
    if idx == -1:
        return insights_md.rstrip() + "\n", ""
    return insights_md[:idx].rstrip() + "\n", insights_md[idx:]


def compose_appendix(
    spec: Dict[str, Any],
    df_personas: pd.DataFrame,
    df_result: pd.DataFrame,
) -> str:
    """
    보고서 하단 부록을 코드로 생성.
    부록 A: 원본 질문 + 응답 스키마 + 측정 명세
    부록 B: 상세 응답 분포 (전체 통계 재출력)
    """
    lines: List[str] = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 부록")
    lines.append("")

    # 부록 A — 원본 질문 + 스키마 + 명세
    lines.append("### 부록 A — 원본 질문 및 응답 스키마")
    lines.append("")
    questions = spec.get("questions", "").strip()
    lines.append("**질문 (큐레이터 입력 그대로):**")
    lines.append("")
    for line in questions.splitlines():
        lines.append(line)
    lines.append("")

    schema_block = spec.get("schema_block", "").strip()
    if schema_block:
        lines.append("**응답 JSON 스키마:**")
        lines.append("")
        lines.append("```json")
        lines.append(schema_block)
        lines.append("```")
        lines.append("")

    lines.append("### 부록 B — 측정 명세")
    lines.append("")
    lines.append("| 항목 | 내용 |")
    lines.append("|---|---|")
    lines.append(f"| run_id | `{spec.get('run_id', '-')}` |")
    lines.append(f"| 질문 생성 모델 | {model_label(spec.get('qgen_model', '-'))} |")
    lines.append(f"| 보고서 생성 모델 | {model_label(spec.get('report_model', '-'))} |")
    lines.append(f"| 시드 | {spec.get('seed', 42)} |")
    filters = spec.get("filters", {}) or {}
    active_filters = {k: v for k, v in filters.items() if v not in (None, "", [])}
    if active_filters:
        lines.append(f"| 필터 | {active_filters} |")
    else:
        lines.append("| 필터 | 없음 (전체 페르소나 풀) |")
    lines.append("")

    lines.append("### 부록 C — 원본 컨텍스트")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>LLM에 주입한 컨텍스트 (클릭하여 펼치기)</summary>")
    lines.append("")
    ctx = spec.get("ctx", spec.get("context", "")).strip()
    for line in ctx.splitlines():
        lines.append(line)
    lines.append("")
    lines.append("</details>")
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# v6.2 인사이트 단계 — 자동 분기 5단계 파이프라인
#
# 사용자 요구: "응답통계 전체가 분석 LLM에 들어가야 인사이트 도출의 의미가 있다"
# → 발췌 없음, 전수 주입. 입력이 1M context의 50%(약 50만 토큰) 영역을
# 초과하면 자동으로 모드 B(다회 호출 5단계)로 분기.
#
# 모드 A — 단일 호출  (입력 ≤ 50만 토큰)
#   build_insight_input_single() → call_llm(INSIGHT_SINGLE_*)
#
# 모드 B — 5단계 파이프라인 (입력 > 50만 토큰)
#   1. build_clusters()                            (코드 결정론, 0 호출)
#   2. analyze_clusters_parallel()                 (cluster수 LLM 호출, 병렬)
#   3. cross_cluster_diff()                        (1 LLM 호출)
#   4. raw_retrieval_check()                       (옵션, default OFF)
#   5. synthesize_insights()                       (1 LLM 호출)
# ─────────────────────────────────────────────────────────

# 한국어 1자 ≈ 1.5~2 토큰. 보수적 추산을 위해 평균 1.7 사용.
KOREAN_CHARS_PER_TOKEN = 1.7

# 자동 분기 임계값. 1M context의 50% 영역 → retrieval 감소 진입 전.
# (1M = 1,048,576 → 50%는 약 524,288 토큰)
TOKEN_THRESHOLD_MODE_B = 500_000

# cluster당 페르소나 수 — 100명이면 응답 300건 = 약 21만자 = 32~42만 토큰
# (모드 B 단계 2 호출 1회당 1M의 32~42% 영역, retrieval 안전권)
PERSONAS_PER_CLUSTER = 100


# 페르소나 narrative 11컬럼 (Nemotron 원본)
_NARRATIVE_COLS = (
    "persona",                      # 요약
    "professional_persona",         # 직업적 면모
    "family_persona",               # 가족 면모
    "cultural_background",          # 문화적 배경
    "arts_persona",                 # 예술 관련 면모
    "travel_persona",               # 여행 면모
    "culinary_persona",             # 음식 면모
    "sports_persona",               # 스포츠
    "hobbies_and_interests",        # 관심사
    "skills_and_expertise",         # 숙련·전문성
    "career_goals_and_ambitions",   # 목표·포부
)

# 페르소나 axis 속성 (응답 raw prefix · cluster axis 분포에 사용)
_PERSONA_ATTR_COLS = (
    "province", "age_bucket", "sex",
    "education_level", "marital_status", "occupation",
)


def _ok_df(df_result: pd.DataFrame) -> pd.DataFrame:
    if "ok" in df_result.columns:
        return df_result[df_result["ok"] == True]  # noqa: E712
    return df_result


def _build_persona_attr_lookup(
    df_personas: pd.DataFrame,
) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """persona_uuid → axis 속성 dict. 응답 raw prefix용."""
    attr_cols = [
        c for c in _PERSONA_ATTR_COLS
        if df_personas is not None and c in df_personas.columns
    ]
    if (
        df_personas is None
        or "persona_uuid" not in df_personas.columns
        or not attr_cols
    ):
        return attr_cols, {}
    lookup = df_personas.set_index("persona_uuid")[attr_cols].to_dict(orient="index")
    return attr_cols, lookup


def _build_persona_narrative_block(
    df_personas: pd.DataFrame,
    persona_uuids: Optional[List[str]] = None,
) -> str:
    """페르소나 narrative 11컬럼 풀로드 → markdown 블록.

    persona_uuids가 주어지면 그 페르소나만 추출, 없으면 df_personas 전체.
    """
    if df_personas is None or len(df_personas) == 0:
        return "(페르소나 데이터 없음)"
    df = df_personas
    if persona_uuids is not None and "persona_uuid" in df.columns:
        df = df[df["persona_uuid"].isin(persona_uuids)]
    attr_cols = [c for c in _PERSONA_ATTR_COLS if c in df.columns]
    narr_cols = [c for c in _NARRATIVE_COLS if c in df.columns]

    blocks: List[str] = []
    for _, row in df.iterrows():
        attrs = ", ".join(
            f"{c}={row[c]}" for c in attr_cols
            if c in row and pd.notna(row[c])
        )
        uuid = row.get("persona_uuid", "")
        header = f"### [{uuid}] {attrs}"
        narr_lines = []
        for c in narr_cols:
            if c in row and pd.notna(row[c]) and str(row[c]).strip():
                narr_lines.append(f"- {c}: {row[c]}")
        blocks.append(header + "\n" + "\n".join(narr_lines))
    return "\n\n".join(blocks)


def _build_response_raw_block(
    df_result: pd.DataFrame,
    persona_attr_lookup: Dict[str, Dict[str, Any]],
    persona_attr_cols: List[str],
) -> str:
    """응답 raw 전수 → '[모델, 페르소나 axis] {시나리오 응답 항목 전수 JSON}' 한 줄/행."""
    ok = _ok_df(df_result)
    if len(ok) == 0:
        return "(응답 없음)"
    resp_cols = [c for c in ok.columns if c.startswith("resp_")]
    lines: List[str] = []
    for _, row in ok.iterrows():
        payload = {
            k: row[k] for k in resp_cols
            if k in row and pd.notna(row[k])
        }
        persona_attrs = persona_attr_lookup.get(row.get("persona_uuid"), {})
        attr_pairs = [
            f"{k}={persona_attrs[k]}"
            for k in persona_attr_cols
            if k in persona_attrs and pd.notna(persona_attrs[k])
        ]
        attr_block = ("[" + ", ".join(attr_pairs) + "] ") if attr_pairs else ""
        lines.append(
            f"[{model_label(row['model_id'])}] {attr_block}"
            + json.dumps(payload, ensure_ascii=False)
        )
    return "\n".join(lines)


def _build_persona_dist_lines(df_personas: pd.DataFrame) -> str:
    if df_personas is None or len(df_personas) == 0:
        return "(데이터 없음)"
    attr_specs = [
        ("province",        "거주 지역"),
        ("age_bucket",      "연령대"),
        ("sex",             "성별"),
        ("education_level", "학력"),
        ("marital_status",  "혼인 상태"),
        ("occupation",      "직업"),
    ]
    lines: List[str] = []
    for col, label in attr_specs:
        if col in df_personas.columns:
            vc = df_personas[col].astype(str).value_counts().head(8)
            items = ", ".join(f"{k} ({v})" for k, v in vc.items())
            lines.append(f"- {label}: {items}")
    return "\n".join(lines) if lines else "(데이터 없음)"


def _build_stats_lines(df_result: pd.DataFrame) -> str:
    """모델별 응답 통계 — 평균·표준편차·옵션 분포."""
    ok = _ok_df(df_result)
    if len(ok) == 0:
        return "(성공 응답 없음)"
    resp_cols = [c for c in ok.columns if c.startswith("resp_")]
    lines: List[str] = []
    for model in sorted(ok["model_id"].unique()):
        sub = ok[ok["model_id"] == model]
        lines.append(f"### {model_label(model)} (n={len(sub)})")
        for col in resp_cols:
            series = sub[col].dropna()
            if len(series) == 0:
                continue
            if pd.api.types.is_numeric_dtype(series):
                lines.append(
                    f"- {col}: 평균 {series.mean():.2f}, 표준편차 {series.std():.2f}, "
                    f"min {series.min()}, max {series.max()}"
                )
            else:
                vc = series.astype(str).value_counts().head(6)
                items = ", ".join(f"{k} ({v})" for k, v in vc.items())
                lines.append(f"- {col}: {items}")
    return "\n".join(lines)


def build_report_input(
    *,
    topic: str,
    context: str,
    questions: str,
    df_result: pd.DataFrame,
    df_personas: pd.DataFrame,
    spec: Optional[Dict[str, Any]] = None,
) -> str:
    """모드 A — 단일 호출용 user 메시지 빌더 (전수 주입, INSIGHT_SINGLE_USER_TEMPLATE 사용).

    페르소나 narrative 11컬럼 + 응답 raw 시나리오별 응답 항목 전수 모두 LLM에 풀로드. 발췌 없음.
    입력이 1M context의 50% 영역을 초과하면 main에서 모드 B로 분기되어
    이 함수는 호출되지 않는다.

    spec 인자는 axis breakdown 컴포저에 사용 가능하지만 모드 A에서는
    persona_dist + stats만으로 충분 — 본문 axis 표가 별도 섹션에 자동
    삽입됨.

    어제 N=300 CSV는 컬럼명이 `model`이고 본 라운드 새 측정은 `model_id`인데,
    본 함수는 `model_id` 기준으로 통계·grouping을 한다. 어제 데이터로 재검증
    가능하도록 진입부에서 한 번 rename. 본 라운드 새 측정에는 영향 없음.
    """
    if "model_id" not in df_result.columns and "model" in df_result.columns:
        df_result = df_result.rename(columns={"model": "model_id"})

    persona_attr_cols, persona_lookup = _build_persona_attr_lookup(df_personas)
    persona_dist = _build_persona_dist_lines(df_personas)
    stats = _build_stats_lines(df_result)

    persona_narratives = _build_persona_narrative_block(df_personas)
    samples_block = _build_response_raw_block(df_result, persona_lookup, persona_attr_cols)

    text = INSIGHT_SINGLE_USER_TEMPLATE.format(
        topic=topic,
        context=context,
        questions=questions,
        n_personas=df_personas.shape[0] if df_personas is not None else 0,
        persona_dist=persona_dist,
        persona_narratives=persona_narratives,
        stats=stats,
        samples_block=samples_block,
    )
    return text


def estimate_input_tokens(
    df_result: pd.DataFrame,
    df_personas: pd.DataFrame,
    *,
    topic: str = "",
    context: str = "",
    questions: str = "",
) -> int:
    """모드 A 단일 호출 시 user 메시지의 한국어 토큰 추산.

    실제 build_report_input을 빌드한 후 한국어 1자 ≈ 1.7 토큰으로 환산.
    실호출 launch 전 dry-run으로 호출 → decide_mode() 입력.
    """
    try:
        text = build_report_input(
            topic=topic,
            context=context,
            questions=questions,
            df_result=df_result,
            df_personas=df_personas,
        )
    except Exception:
        # 빌드 실패 시 보수적으로 큰 값 반환 → 모드 B 분기
        return 10_000_000
    return int(len(text) * KOREAN_CHARS_PER_TOKEN)


def decide_mode(input_tokens: int) -> str:
    """입력 토큰에 따라 'A' (단일 호출) or 'B' (5단계 파이프라인) 결정."""
    return "A" if input_tokens <= TOKEN_THRESHOLD_MODE_B else "B"


# ─────────────────────────────────────────────────────────
# 모드 B — 5단계 파이프라인
# ─────────────────────────────────────────────────────────

def _select_cluster_axes(df_personas: pd.DataFrame) -> List[str]:
    """cluster 분할에 사용할 axis 선택 — 분포 보존이 중요한 순서대로."""
    candidates = ["age_bucket", "sex", "region"]
    cols = []
    for c in candidates:
        if c in df_personas.columns:
            cols.append(c)
    # region 컬럼이 없으면 province에서 만들어 사용
    if "region" not in cols and "province" in df_personas.columns:
        cols.append("province")
    return cols or [df_personas.columns[0]]


def build_clusters(
    df_result: pd.DataFrame,
    df_personas: pd.DataFrame,
    *,
    n_clusters: Optional[int] = None,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """페르소나를 axis 분포 보존하며 stratified cluster로 분할 (코드 결정론, 0 LLM 호출).

    pandas groupby().indices + np.random.RandomState 패턴 (전역 CLAUDE.md
    검증: 메모리 압박 환경에서 boolean mask 반복 회피).

    n_clusters 미지정 시 ceil(n_personas / PERSONAS_PER_CLUSTER).
    각 cluster에 페르소나·응답을 배정해 dict 리스트로 반환.
    """
    import numpy as np

    if df_personas is None or len(df_personas) == 0:
        return []

    n_personas = len(df_personas)
    if n_clusters is None:
        n_clusters = max(1, (n_personas + PERSONAS_PER_CLUSTER - 1) // PERSONAS_PER_CLUSTER)
    n_clusters = max(1, min(n_clusters, n_personas))

    if n_clusters == 1:
        # 단일 cluster — 모드 B를 강제로 발동시킨 검증 시나리오에서 사용
        cluster_uuids = [list(df_personas["persona_uuid"].astype(str))]
    else:
        # axis 분포 보존: stratification key를 만들고 그 안에서 round-robin
        axes = _select_cluster_axes(df_personas)
        df = df_personas.copy()
        if "region" in axes and "region" not in df.columns and "province" in df.columns:
            df["region"] = df["province"].apply(province_to_region)
        strat_key = df[axes].astype(str).agg("|".join, axis=1)
        rng = np.random.RandomState(seed)
        cluster_assignment = np.empty(len(df), dtype=int)
        # strat 키별 round-robin은 size=1·2 키들이 cluster 0에 쏠리므로,
        # 각 strat 키마다 시작 offset을 무작위화해 long-run 균등 분배 확보.
        for key, group_idx in strat_key.groupby(strat_key).indices.items():
            shuffled = rng.permutation(group_idx)
            offset = int(rng.randint(0, n_clusters))
            for i, idx in enumerate(shuffled):
                cluster_assignment[idx] = (i + offset) % n_clusters
        cluster_uuids = []
        for cid in range(n_clusters):
            mask = cluster_assignment == cid
            uuids = list(df.loc[mask, "persona_uuid"].astype(str))
            cluster_uuids.append(uuids)

    clusters: List[Dict[str, Any]] = []
    df_result_indexed = df_result.copy()
    df_result_indexed["persona_uuid"] = df_result_indexed["persona_uuid"].astype(str)

    for cid, uuids in enumerate(cluster_uuids):
        sub_personas = df_personas[df_personas["persona_uuid"].astype(str).isin(uuids)]
        sub_result = df_result_indexed[df_result_indexed["persona_uuid"].isin(uuids)]
        axis_dist_parts = []
        for col in ("age_bucket", "sex", "education_level"):
            if col in sub_personas.columns:
                vc = sub_personas[col].astype(str).value_counts().head(5)
                items = ", ".join(f"{k}({v})" for k, v in vc.items())
                axis_dist_parts.append(f"{col}: {items}")
        clusters.append({
            "cluster_id": f"c{cid + 1}",
            "df_personas": sub_personas.reset_index(drop=True),
            "df_result": sub_result.reset_index(drop=True),
            "n_personas": len(sub_personas),
            "n_responses": len(sub_result),
            "axis_dist": " | ".join(axis_dist_parts) or "(분포 없음)",
            "share": f"{len(sub_personas) / max(1, n_personas) * 100:.1f}%",
        })
    return clusters


def _call_insight_llm(
    *,
    model_id: str,
    system: str,
    user: str,
    timeout: int = 600,
    json_mode: bool = True,
) -> Dict[str, Any]:
    """인사이트 단계 LLM 호출 — JSON 응답 강건 파싱."""
    resp = call_llm(
        model_id, system, user,
        json_mode=json_mode, temperature=0.5, timeout=timeout,
    )
    if json_mode:
        try:
            parsed = parse_json_response(resp.text)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"인사이트 LLM JSON 파싱 실패 ({model_id}): {e}. "
                f"응답 앞 500자: {resp.text[:500]}"
            ) from e
        return {"parsed": parsed, "raw_text": resp.text, "elapsed_sec": resp.elapsed_sec}
    return {"parsed": None, "raw_text": resp.text, "elapsed_sec": resp.elapsed_sec}


def analyze_cluster(
    cluster: Dict[str, Any],
    *,
    topic: str,
    context: str,
    questions: str,
    report_model: str,
    n_clusters_total: int,
    timeout: int = 600,
) -> Dict[str, Any]:
    """모드 B 단계 2 — 단일 cluster 분석 LLM 호출.

    cluster 내 페르소나 narrative + 응답 raw 전수 주입. 다른 cluster를
    추측하지 않도록 prompt에 명시. 후속 cross-cluster diff에서 통합.
    """
    df_personas = cluster["df_personas"]
    df_result = cluster["df_result"]
    persona_attr_cols, persona_lookup = _build_persona_attr_lookup(df_personas)
    persona_narratives = _build_persona_narrative_block(df_personas)
    samples_block = _build_response_raw_block(df_result, persona_lookup, persona_attr_cols)
    stats = _build_stats_lines(df_result)

    user = CLUSTER_ANALYSIS_USER_TEMPLATE.format(
        topic=topic,
        context=context,
        questions=questions,
        cluster_id=cluster["cluster_id"],
        n_personas=cluster["n_personas"],
        n_responses=cluster["n_responses"],
        axis_dist=cluster["axis_dist"],
        cluster_share=cluster["share"],
        persona_narratives=persona_narratives,
        stats=stats,
        samples_block=samples_block,
    )
    result = _call_insight_llm(
        model_id=report_model,
        system=CLUSTER_ANALYSIS_SYSTEM,
        user=user,
        timeout=timeout,
    )
    return {
        "cluster_id": cluster["cluster_id"],
        "n_personas": cluster["n_personas"],
        "n_responses": cluster["n_responses"],
        "axis_dist": cluster["axis_dist"],
        "summary": result["parsed"],
        "raw_text": result["raw_text"],
        "elapsed_sec": result["elapsed_sec"],
    }


def analyze_clusters_parallel(
    clusters: List[Dict[str, Any]],
    *,
    topic: str,
    context: str,
    questions: str,
    report_model: str,
    timeout: int = 600,
    progress_cb=None,
) -> List[Dict[str, Any]]:
    """모드 B 단계 2 — cluster 분석 병렬 호출.

    cluster들이 서로 독립이므로 ThreadPoolExecutor로 동시 호출.
    wall-clock time을 cluster 수 무관 약 1~2.5분 영역으로 만드는 핵심 단계.

    progress_cb(cluster_id, status, elapsed_sec) — cluster 완료마다 status.json
    갱신용 callback (옵션).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    n = len(clusters)
    if n == 0:
        return []

    results: List[Optional[Dict[str, Any]]] = [None] * n
    cluster_index = {c["cluster_id"]: i for i, c in enumerate(clusters)}

    # max_workers는 cluster 수와 동일 — 모든 cluster 동시 호출 (LLM provider rate limit
    # 안에서). 실측 N=10 cluster까지는 OpenRouter rate limit 한도 안.
    max_workers = max(1, min(n, 10))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                analyze_cluster,
                c,
                topic=topic,
                context=context,
                questions=questions,
                report_model=report_model,
                n_clusters_total=n,
                timeout=timeout,
            ): c["cluster_id"]
            for c in clusters
        }
        for fut in as_completed(futures):
            cid = futures[fut]
            try:
                res = fut.result()
                results[cluster_index[cid]] = res
                if progress_cb:
                    progress_cb(cid, "ok", res.get("elapsed_sec", 0.0))
            except Exception as e:
                # cluster 1개 실패해도 나머지 진행 — 단계 5 합성에서 누락 처리
                results[cluster_index[cid]] = {
                    "cluster_id": cid,
                    "summary": None,
                    "error": str(e),
                    "elapsed_sec": 0.0,
                }
                if progress_cb:
                    progress_cb(cid, "fail", 0.0)
    return [r for r in results if r is not None]


def cross_cluster_diff(
    cluster_results: List[Dict[str, Any]],
    *,
    topic: str,
    report_model: str,
    timeout: int = 600,
) -> Dict[str, Any]:
    """모드 B 단계 3 — cross-cluster diff (1회 LLM 호출).

    단계 2 cluster 분석 결과를 가로질러 비교 → 공통점·차이·약신호 발견.
    단일 cluster에서는 잡히지 않는 cross-cluster 패턴을 hierarchical merging
    방식으로 통합. 단계 4 raw retrieval 후보(suspect_cluster_ids) 지정 가능.
    """
    valid = [r for r in cluster_results if r.get("summary") is not None]
    summaries_text = "\n\n---\n\n".join(
        f"### cluster_id: {r['cluster_id']} "
        f"(n_personas={r.get('n_personas', '?')}, n_responses={r.get('n_responses', '?')}, "
        f"axis: {r.get('axis_dist', '-')})\n\n"
        + json.dumps(r["summary"], ensure_ascii=False, indent=2)
        for r in valid
    )
    if not summaries_text:
        return {
            "summary": None,
            "error": "단계 2 cluster 분석 결과가 모두 실패했습니다",
        }

    total_personas = sum(r.get("n_personas", 0) for r in valid)
    total_responses = sum(r.get("n_responses", 0) for r in valid)

    user = CROSS_CLUSTER_DIFF_USER_TEMPLATE.format(
        topic=topic,
        n_clusters=len(valid),
        total_personas=total_personas,
        total_responses=total_responses,
        cluster_summaries_block=summaries_text,
    )
    result = _call_insight_llm(
        model_id=report_model,
        system=CROSS_CLUSTER_DIFF_SYSTEM,
        user=user,
        timeout=timeout,
    )
    return {
        "summary": result["parsed"],
        "raw_text": result["raw_text"],
        "elapsed_sec": result["elapsed_sec"],
    }


def raw_retrieval_check(
    suspect_cluster_ids: List[str],
    suspect_reason: str,
    clusters: List[Dict[str, Any]],
    cluster_results: List[Dict[str, Any]],
    *,
    report_model: str,
    timeout: int = 600,
) -> List[Dict[str, Any]]:
    """모드 B 단계 4 (옵션) — 의심 cluster의 raw 자료 재주입 검증.

    cross-cluster diff가 짚은 의심 cluster들의 페르소나 narrative + 응답 raw를
    다시 LLM에 주입해 단계 2 분석을 raw에 비춰 검증·정정. default OFF.
    """
    if not suspect_cluster_ids:
        return []
    cluster_by_id = {c["cluster_id"]: c for c in clusters}
    summary_by_id = {r["cluster_id"]: r for r in cluster_results}
    out: List[Dict[str, Any]] = []
    for cid in suspect_cluster_ids:
        cluster = cluster_by_id.get(cid)
        prev = summary_by_id.get(cid)
        if cluster is None or prev is None or prev.get("summary") is None:
            out.append({"cluster_id": cid, "error": "cluster 자료 누락"})
            continue
        df_personas = cluster["df_personas"]
        df_result = cluster["df_result"]
        attr_cols, lookup = _build_persona_attr_lookup(df_personas)
        persona_narratives = _build_persona_narrative_block(df_personas)
        samples_block = _build_response_raw_block(df_result, lookup, attr_cols)

        user = RAW_RETRIEVAL_USER_TEMPLATE.format(
            cluster_id=cid,
            cluster_summary=json.dumps(prev["summary"], ensure_ascii=False, indent=2),
            suspect_reason=suspect_reason,
            persona_narratives=persona_narratives,
            samples_block=samples_block,
        )
        try:
            res = _call_insight_llm(
                model_id=report_model,
                system=RAW_RETRIEVAL_SYSTEM,
                user=user,
                timeout=timeout,
            )
            out.append({
                "cluster_id": cid,
                "verification": res["parsed"],
                "elapsed_sec": res["elapsed_sec"],
            })
        except Exception as e:
            out.append({"cluster_id": cid, "error": str(e)})
    return out


def synthesize_insights(
    cluster_results: List[Dict[str, Any]],
    diff_result: Dict[str, Any],
    retrieval_results: List[Dict[str, Any]],
    *,
    topic: str,
    context: str,
    n_clusters: int,
    total_personas: int,
    total_responses: int,
    report_model: str,
    timeout: int = 600,
) -> Dict[str, Any]:
    """모드 B 단계 5 — 최종 인사이트 합성 (1회 LLM 호출).

    모든 단계(2~4) 결과를 통합해 4섹션 JSON 출력. 단일 호출 모드 A와 동일한 schema.
    """
    valid_clusters = [r for r in cluster_results if r.get("summary") is not None]
    cluster_summaries_block = "\n\n---\n\n".join(
        f"### cluster_id: {r['cluster_id']}\n"
        + json.dumps(r["summary"], ensure_ascii=False, indent=2)
        for r in valid_clusters
    )
    diff_block = (
        json.dumps(diff_result.get("summary"), ensure_ascii=False, indent=2)
        if diff_result.get("summary")
        else f"(단계 3 실패: {diff_result.get('error', '알 수 없음')})"
    )
    retrieval_used = "예" if retrieval_results else "아니오 (default OFF)"
    if retrieval_results:
        retrieval_block = "\n\n".join(
            f"### cluster_id: {r['cluster_id']}\n"
            + (
                json.dumps(r.get("verification"), ensure_ascii=False, indent=2)
                if r.get("verification")
                else f"(검증 실패: {r.get('error', '알 수 없음')})"
            )
            for r in retrieval_results
        )
    else:
        retrieval_block = "(단계 4 미실행)"

    # 컨텍스트가 길면 절반으로 자름 — 합성 단계는 클러스터 결과 통합이 핵심,
    # 원본 컨텍스트는 단계 2에서 이미 cluster별로 봤음.
    context_short = context[:5000] + (" …(이하 생략)" if len(context) > 5000 else "")

    user = SYNTHESIS_USER_TEMPLATE.format(
        topic=topic,
        context_short=context_short,
        total_personas=total_personas,
        total_responses=total_responses,
        n_clusters=n_clusters,
        retrieval_used=retrieval_used,
        cluster_summaries_block=cluster_summaries_block,
        diff_block=diff_block,
        retrieval_block=retrieval_block,
    )
    result = _call_insight_llm(
        model_id=report_model,
        system=SYNTHESIS_SYSTEM,
        user=user,
        timeout=timeout,
    )
    return {
        "summary": result["parsed"],
        "raw_text": result["raw_text"],
        "elapsed_sec": result["elapsed_sec"],
    }


# ─────────────────────────────────────────────────────────
# 4섹션 JSON → markdown 변환 (모드 A·B 공통)
# ─────────────────────────────────────────────────────────

def _md_escape_pipe(s: Any) -> str:
    """markdown 표 셀 안에서 파이프 문자가 컬럼 구분자로 오해되지 않게 escape."""
    return str(s).replace("|", "\\|").replace("\n", " ")


def insight_json_to_markdown(insight: Optional[Dict[str, Any]]) -> str:
    """모드 A·B 출력(4섹션 JSON)을 보고서 본문 markdown 4섹션으로 변환.

    INSIGHT_SINGLE_USER_TEMPLATE / SYNTHESIS_USER_TEMPLATE의 출력 schema와
    1:1 매칭. drift 시 누락 섹션은 빈 메시지로 graceful degrade.
    """
    if not isinstance(insight, dict):
        return (
            "## 핵심 발견\n\n인사이트 생성에 실패했습니다 (응답 형식 불일치).\n\n"
            "원천 응답은 result.csv에 그대로 남아 있습니다.\n"
        )
    out: List[str] = []

    # 응답 분석 — LLM이 schema·raw 응답을 보고 자율 결정한 표 모음
    tables = insight.get("analysis_tables") or []
    if tables:
        out.append("## 응답 분석")
        out.append("")
        for t in tables:
            if isinstance(t, dict):
                title = (t.get("title") or "").strip()
                md = (t.get("markdown") or "").strip()
                if title:
                    out.append(f"### {title}")
                    out.append("")
                if md:
                    out.append(md)
                    out.append("")
            elif isinstance(t, str) and t.strip():
                out.append(t.strip())
                out.append("")

    # 핵심 발견
    out.append("## 핵심 발견")
    out.append("")
    findings = insight.get("key_findings") or []
    if findings:
        out.append("| 발견 | 내용 |")
        out.append("|---|---|")
        for f in findings:
            label = _md_escape_pipe(f.get("label", "")) if isinstance(f, dict) else _md_escape_pipe(f)
            content = _md_escape_pipe(f.get("content", "")) if isinstance(f, dict) else ""
            out.append(f"| {label} | {content} |")
    else:
        out.append("(핵심 발견 없음)")
    out.append("")

    # 큐레이터 관점·가설
    out.append("## 큐레이터 관점·가설")
    out.append("")
    hypotheses = insight.get("curator_hypotheses") or []
    if hypotheses:
        for i, h in enumerate(hypotheses, 1):
            if isinstance(h, dict):
                target = h.get("target_group", "")
                form = h.get("form", "")
                content = h.get("content", "")
                head = f"**{i}. {form}** — 대상: {target}" if form or target else f"**{i}.**"
                out.append(head)
                if content:
                    out.append("")
                    out.append(content)
            else:
                out.append(f"**{i}.** {h}")
            out.append("")
    else:
        out.append("(가설 없음)")
        out.append("")

    # 곱씹을 만한 응답
    out.append("## 곱씹을 만한 응답")
    out.append("")
    quotes = insight.get("responses_to_chew_on") or []
    if quotes:
        for q in quotes:
            if isinstance(q, dict):
                attrs = q.get("persona_attrs", "")
                model = q.get("model", "")
                quote = q.get("quote", "")
                note = q.get("curator_note", "")
                head = f"**({model} · {attrs})**" if model or attrs else ""
                if head:
                    out.append(head)
                if quote:
                    out.append("")
                    out.append(f"> {quote}")
                if note:
                    out.append("")
                    out.append(f"_{note}_")
                out.append("")
            else:
                out.append(f"- {q}")
                out.append("")
    else:
        out.append("(인용 없음)")
        out.append("")

    # 다음에 던져볼 질문·가설
    out.append("## 다음에 던져볼 질문·가설")
    out.append("")
    questions = insight.get("next_questions") or []
    if questions:
        for q in questions:
            out.append(f"- {q}")
    else:
        out.append("(후속 질문 없음)")
    out.append("")

    return "\n".join(out)


# ─────────────────────────────────────────────────────────
# PDF + PNG 렌더 (weasyprint, pypdfium2)
# ─────────────────────────────────────────────────────────

REPORT_HTML_CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Noto Sans CJK KR', 'Noto Sans KR', sans-serif;
       font-size: 10.5pt; line-height: 1.55; color: #222; }
h1 { font-size: 18pt; margin: 0 0 8pt 0; }
h2 { font-size: 13pt; margin: 14pt 0 4pt 0; border-bottom: 0.5pt solid #888; padding-bottom: 2pt; }
h3 { font-size: 11pt; margin: 8pt 0 2pt 0; }
p, li { margin: 2pt 0; }
ul, ol { margin: 2pt 0 4pt 18pt; padding: 0; }
code { background: #f0f0f0; padding: 0 2pt; border-radius: 2pt; }
pre { background: #f7f7f7; padding: 6pt; border-radius: 3pt;
      white-space: pre-wrap; word-break: break-word; font-size: 9pt; }
blockquote { border-left: 2pt solid #aaa; margin: 4pt 0 4pt 4pt;
             padding: 2pt 8pt; color: #555; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9.5pt; }
th { background: #e8e8e8; text-align: left; padding: 4pt 6pt;
     border: 0.4pt solid #aaa; font-weight: bold; }
td { padding: 3pt 6pt; border: 0.4pt solid #ccc; vertical-align: top; }
tr:nth-child(even) td { background: #f9f9f9; }
details summary { cursor: pointer; color: #444; font-style: italic; }
img { max-width: 100%; height: auto; display: block; margin: 6pt auto; }
"""


def render_report_files(run_dir: Path, report_md: str, topic: str) -> None:
    """report.md → report.pdf → report.png. 시스템 폰트 fallback 사용.

    report.md 자체가 ``# knowing-koreans · …`` 헤더를 포함하므로 별도의
    HTML <h1> wrapper는 두지 않는다. <title>만 PDF 메타로 사용.
    """
    import markdown as md_lib  # type: ignore
    from weasyprint import CSS, HTML  # type: ignore
    import pypdfium2 as pdfium  # type: ignore

    body_html = md_lib.markdown(report_md, extensions=["fenced_code", "tables"])
    title_for_pdf = (_topic_short(topic, limit=60) or "knowing-koreans 보고서")
    full_html = (
        f"<html><head><meta charset='utf-8'><title>{title_for_pdf}</title></head>"
        f"<body>{body_html}</body></html>"
    )
    pdf_path = run_dir / "report.pdf"
    # base_url=run_dir — markdown ![](chart_appeal.png) 같은 상대경로를
    # run_dir/chart_appeal.png로 해석하기 위한 weasyprint 설정.
    HTML(string=full_html, base_url=str(run_dir)).write_pdf(
        target=str(pdf_path),
        stylesheets=[CSS(string=REPORT_HTML_CSS)],
    )

    pdf = pdfium.PdfDocument(str(pdf_path))
    if len(pdf) == 0:
        raise RuntimeError("렌더된 PDF에 페이지가 없음")
    page = pdf[0]
    pil_image = page.render(scale=2.0).to_pil()  # DPI ≈ 144
    pil_image.save(run_dir / "report.png", format="PNG", optimize=True)
    pdf.close()


def build_sources_zip(run_dir: Path) -> None:
    """spec.json + personas.csv + result.csv + report.md → sources.zip."""
    zip_path = run_dir / "sources.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in ("spec.json", "personas.csv", "result.csv", "report.md"):
            p = run_dir / name
            if p.exists():
                zf.write(p, arcname=name)


# ─────────────────────────────────────────────────────────
# Observable Framework 빌드 — 측정 결과 → 정적 사이트
# ─────────────────────────────────────────────────────────

def run_observable_build(run_dir: Path) -> Optional[Path]:
    """frontend-obs 를 KK_RUN_DIR=run_dir 환경에서 빌드해 산출물을 run_dir/observable/ 로 복사.

    흐름:
      1. KK_RUN_DIR=str(run_dir) 환경변수로 ``npx --yes observable build`` 호출
      2. frontend-obs/dist 가 생성되면 run_dir/observable/ 로 복사 (기존 디렉토리는 교체)
      3. 결과 디렉토리 경로를 반환. 실패 시 None.

    Node 또는 npx 가 시스템에 없으면 즉시 None 반환. Observable Framework 빌드는 데이터 로더
    (src/data/scenario.json.py)가 ``KK_RUN_DIR`` 을 읽어 spec.json + result.csv + personas.csv +
    insight.json 을 합쳐 site 정적 JSON으로 만든다.
    """
    import shutil
    import subprocess

    fobs_root = Path(__file__).resolve().parents[1] / "frontend-obs"
    if not fobs_root.exists():
        print(f"[warn] frontend-obs 미존재: {fobs_root}", file=sys.stderr, flush=True)
        return None

    npx = shutil.which("npx")
    if not npx:
        print("[warn] npx 미설치 — Observable build 건너뜀", file=sys.stderr, flush=True)
        return None

    env = os.environ.copy()
    env["KK_RUN_DIR"] = str(run_dir)

    # data loader (src/data/scenario.json.py) 는 `python3 file.py` 로 실행되며 PATH 우선
    # 매칭이다. ssh 비대화형 세션은 systemd Environment 를 상속받지 않아 PATH 가 시스템
    # default 만 잡혀 venv site-packages (pandas 등) 가 안 보인다. systemd 자동화는
    # EnvironmentFile/PATH 가 venv/bin 우선이라 정상 동작하지만, 수동 ssh 검증 환경에서
    # 같은 빌드를 돌리면 ModuleNotFoundError. 본 라인이 두 환경 모두 보장한다.
    venv_bin = str(Path(sys.prefix) / "bin")
    if venv_bin not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")

    # 빌드 직전 캐시·옛 dist 청소.
    # Observable Framework data loader 결과는 src/.observablehq/cache/ 에 캐시되며 invalidation은
    # loader 소스 파일의 mtime/내용 기준으로만 판정한다. KK_RUN_DIR 환경변수 변경 / style.css 등
    # 본문 변경은 캐시 무효화 신호로 인식되지 않으므로, 측정마다 다른 KK_RUN_DIR 을 안전하게
    # 반영하려면 빌드 직전에 캐시·이전 dist를 명시적으로 제거한다.
    cache_dir = fobs_root / "src" / ".observablehq" / "cache"
    dist_dir = fobs_root / "dist"
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    if dist_dir.exists():
        shutil.rmtree(dist_dir, ignore_errors=True)

    try:
        result = subprocess.run(
            [npx, "--yes", "observable", "build"],
            cwd=str(fobs_root),
            env=env,
            check=True,
            timeout=600,
            capture_output=True,
            text=True,
        )
        # stdout 마지막 몇 줄만 로그로 (빌드 진행 노이즈 절감)
        tail = "\n".join((result.stdout or "").splitlines()[-5:])
        if tail.strip():
            print(f"[observable build] {tail}", flush=True)
    except subprocess.CalledProcessError as e:
        err_tail = "\n".join((e.stderr or e.stdout or "").splitlines()[-10:])
        print(
            f"[warn] Observable build 실패 (rc={e.returncode}): {err_tail}",
            file=sys.stderr,
            flush=True,
        )
        return None
    except subprocess.TimeoutExpired:
        print("[warn] Observable build 타임아웃 (600s 초과)", file=sys.stderr, flush=True)
        return None
    except Exception as e:
        print(f"[warn] Observable build 예외: {e!r}", file=sys.stderr, flush=True)
        return None

    if not dist_dir.exists():
        print(f"[warn] Observable dist 산출물 미존재: {dist_dir}", file=sys.stderr, flush=True)
        return None

    dest_dir = run_dir / "observable"
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(dist_dir, dest_dir)
    return dest_dir


def render_observable_pdf(run_dir: Path) -> Optional[Path]:
    """run_dir/observable/index.html → run_dir/report_obs.pdf (playwright Chromium 사용).

    A4 세로, 한국어 시스템 폰트 fallback (Noto Sans CJK / Nanum) 자동 적용. playwright 가
    설치되지 않았거나 Chromium 바이너리가 없으면 None 반환. Observable Framework 산출물은
    절대경로 의존성(`/_observablehq/...`, `/_file/...`)을 갖기 때문에 file:// 로 직접 열면
    리소스 로딩이 실패한다. 이를 우회하기 위해 같은 디렉토리에서 임시 HTTP 서버를 띄워 그 URL
    을 navigate 한다.
    """
    import http.server
    import socketserver
    import threading

    obs_dir = run_dir / "observable"
    obs_index = obs_dir / "index.html"
    if not obs_index.exists():
        print(f"[warn] observable/index.html 미존재 — PDF 생략: {obs_index}", file=sys.stderr, flush=True)
        return None

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        print(
            "[warn] playwright 미설치 — Observable PDF 생략. "
            "(pip install playwright + python -m playwright install chromium)",
            file=sys.stderr,
            flush=True,
        )
        return None

    pdf_path = run_dir / "report_obs.pdf"

    # 임시 HTTP 서버 — 절대경로(`/_observablehq/...`, `/_file/...`) 리소스 해결.
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(obs_dir), **kw)

        def log_message(self, *args, **kwargs):  # noqa: ARG002
            return  # noisy access log 억제

    httpd: Optional[socketserver.TCPServer] = None
    server_thread: Optional[threading.Thread] = None

    try:
        httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        url = f"http://127.0.0.1:{port}/index.html"

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                print(
                    f"[warn] playwright Chromium launch 실패: {e!r} — "
                    "(python -m playwright install chromium 으로 바이너리 설치 필요)",
                    file=sys.stderr,
                    flush=True,
                )
                return None
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=60_000)
                # Observable 차트(Plot.js)는 D3 layout 후에 그려지므로 짧은 추가 대기.
                page.wait_for_timeout(800)
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
                )
            finally:
                browser.close()
    except Exception as e:
        print(f"[warn] Observable PDF 렌더 실패: {e!r}", file=sys.stderr, flush=True)
        return None
    finally:
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass

    if not pdf_path.exists():
        return None
    return pdf_path


# ─────────────────────────────────────────────────────────
# 메인 흐름
# ─────────────────────────────────────────────────────────

def _build_result_columns(schema_block: str) -> List[str]:
    """result.csv 컬럼 합집합을 schema_block에서 미리 결정.

    success / failure row dict가 다른 키 집합을 갖기 때문에, 첫 호출이
    failure로 시작하면 resp_* 컬럼이 헤더에서 누락되어 이후 success 행
    응답이 잘려 들어간다. schema_block의 키를 미리 resp_<key>로 추가해
    합집합 fieldnames로 to_csv columns= 에 명시하면 첫 행 결과와 무관하게
    헤더가 항상 동일.
    """
    base = ["persona_uuid", "model_id", "ok", "elapsed_sec", "raw_json", "error"]
    resp_keys: List[str] = []
    if schema_block and schema_block.strip():
        try:
            schema = json.loads(schema_block)
            if isinstance(schema, dict):
                resp_keys = [f"resp_{k}" for k in schema.keys()]
        except json.JSONDecodeError:
            pass
    return base + resp_keys


def _append_result_row(
    result_path: Path,
    row: Dict[str, Any],
    columns: List[str],
    header_written: bool,
) -> bool:
    """단일 row를 result.csv에 append. columns로 모든 가능한 컬럼을 고정."""
    df = pd.DataFrame([row], columns=columns)
    if not header_written:
        df.to_csv(result_path, index=False, encoding="utf-8")
        return True
    df.to_csv(result_path, index=False, header=False, mode="a", encoding="utf-8")
    return True


def main(run_dir: Path) -> int:
    run_dir = Path(run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        print(f"[fatal] spec.json 없음: {spec_path}", file=sys.stderr)
        return 2

    spec: Dict[str, Any] = json.loads(spec_path.read_text(encoding="utf-8"))

    n_total = int(spec["n"]) * len(spec["models"])
    status: Dict[str, Any] = {
        "run_id": spec["run_id"],
        "owner": spec.get("owner", ""),
        "topic_short": (spec.get("topic", "") or "")[:30],
        "phase": "starting",
        "started_at": _now_iso(),
        "updated_at": None,
        "n_total": n_total,
        "n_done": 0,
        "n_ok": 0,
        "n_fail": 0,
        "avg_sec_per_call": 0.0,
        "eta_sec": None,
        "report_ready": False,
        "finished_at": None,
        "error": None,
    }
    write_status(run_dir, status)

    try:
        # ── 사전 검증 (schema/engine drift) ─────────────
        errors = validate_spec(spec)
        if errors:
            status["phase"] = "error"
            status["error"] = "사전 검증 실패: " + " / ".join(errors)
            status["finished_at"] = _now_iso()
            write_status(run_dir, status)
            print(f"[abort] 사전 검증 실패: {errors}", file=sys.stderr)
            return 3

        # ── 페르소나 풀 로드 ───────────────────────────
        status["phase"] = "loading_pool"
        write_status(run_dir, status)
        if CANCEL:
            return _finalize_cancelled(run_dir, status)
        print(f"[1/4] 페르소나 풀 로드 중 (PERSONA_DIR={PERSONA_DIR})", flush=True)
        df_pool = load_all_personas(PERSONA_DIR)
        print(f"      {len(df_pool):,}건 로드", flush=True)

        # ── 샘플링 ────────────────────────────────────
        if CANCEL:
            return _finalize_cancelled(run_dir, status)
        status["phase"] = "sampling"
        write_status(run_dir, status)
        filters = spec.get("filters", {}) or {}
        sample_kwargs = {k: v for k, v in filters.items() if v not in (None, "", [])}
        df_personas = sample_personas(
            n=int(spec["n"]),
            seed=int(spec.get("seed", 42)),
            df=df_pool,
            **sample_kwargs,
        )
        df_personas.to_csv(run_dir / "personas.csv", index=False, encoding="utf-8")
        print(f"[2/4] 표본 {len(df_personas)}명 추출", flush=True)
        del df_pool  # 1M행 풀은 즉시 해제

        # ── LLM 호출 루프 ─────────────────────────────
        status["phase"] = "calling_llm"
        write_status(run_dir, status)

        ctx = spec.get("ctx", "") or ""
        questions = spec.get("questions", "") or ""
        schema_block = spec.get("schema_block", "") or ""
        example_block = build_response_example(schema_block)
        result_path = run_dir / "result.csv"
        result_columns = _build_result_columns(schema_block)
        header_written = False
        elapsed_total = 0.0
        n_done = 0
        n_ok = 0
        n_fail = 0
        rows_buffer: List[Dict[str, Any]] = []  # 보고서 빌드용 메모리 버퍼

        print(f"[3/4] 응답 수집 시작 — 총 {n_total}회", flush=True)

        for _, persona_row in df_personas.iterrows():
            persona_dict = persona_row.to_dict()
            system = render_template(SYSTEM_TEMPLATE, persona_dict)
            user_msg = DYNAMIC_USER_TEMPLATE.format(
                context=ctx, questions=questions,
                schema=schema_block, example=example_block,
            )
            persona_uuid = persona_dict.get("persona_uuid", "")
            for model_id in spec["models"]:
                if CANCEL:
                    return _finalize_cancelled(run_dir, status)
                row: Dict[str, Any] = {
                    "persona_uuid": persona_uuid,
                    "model_id": model_id,
                    "ok": False,
                }
                t0 = time.monotonic()
                try:
                    resp = call_llm(
                        model_id, system, user_msg,
                        json_mode=True, temperature=0.7, timeout=180,
                    )
                    row["elapsed_sec"] = round(resp.elapsed_sec, 2)
                    row["raw_json"] = resp.text
                    try:
                        parsed = parse_json_response(resp.text)
                        if isinstance(parsed, dict):
                            # 외부 리뷰 #2 (5-06) 옵션 ㄴ — dict-wrap 응답을
                            # description leaf 로 unwrap 후 row 저장. nested
                            # dict 가 CSV 에 그대로 직렬화되면 frontend loader 의
                            # 정수 변환·options 매칭이 부정확해지는 사고 차단.
                            for k, v in parsed.items():
                                row[f"resp_{k}"] = _unwrap_dict_response(v)
                            # schema_block 기반 검증 — 실패 시 ok=False 유지 +
                            # error 기록 → _ok_df() 자동 제외로 인사이트 LLM
                            # 입력 / 통계 표본에서 자동 차단.
                            schema_fail = validate_response_against_schema(
                                parsed, schema_block
                            )
                            if schema_fail:
                                row["error"] = schema_fail
                            else:
                                row["ok"] = True
                        else:
                            row["error"] = f"JSON이 dict가 아님: {type(parsed).__name__}"
                    except json.JSONDecodeError as e:
                        row["error"] = f"JSON 파싱 실패: {e}"
                except Exception as e:
                    row["error"] = str(e)
                t1 = time.monotonic()
                elapsed_total += (t1 - t0)
                header_written = _append_result_row(result_path, row, result_columns, header_written)
                rows_buffer.append(row)
                n_done += 1
                if row.get("ok"):
                    n_ok += 1
                else:
                    n_fail += 1
                avg = elapsed_total / n_done
                eta = int(max(0.0, (n_total - n_done) * avg))
                status["n_done"] = n_done
                status["n_ok"] = n_ok
                status["n_fail"] = n_fail
                status["avg_sec_per_call"] = round(avg, 2)
                status["eta_sec"] = eta

                # 매 5건 또는 마지막에 status.json 갱신 (IO 부담 감축)
                if n_done % 5 == 0 or n_done == n_total:
                    write_status(run_dir, status)
                    print(
                        f"  [{n_done}/{n_total}] ok={n_ok} fail={n_fail} "
                        f"avg={avg:.2f}s eta={eta}s",
                        flush=True,
                    )

        # 루프 끝에 status.json 한 번 더 보장
        write_status(run_dir, status)

        # ── 유효 응답 0건이면 보고서 생성 자체를 건너뛴다 ───────────────
        # Opus 4.7이 빈 표본으로 "있어 보이는 가짜 분석"을 만들어내는 사고
        # (예: 50건 모두 rate-limit 실패인데 페르소나 분포만 보고 가설을
        #  찍어내는 케이스)을 차단합니다. 진단은 result.csv의 error 컬럼.
        if not CANCEL and n_ok == 0:
            status["phase"] = "error"
            status["error"] = (
                f"유효 응답 0건 — {n_total}건 모두 실패했습니다. "
                f"result.csv의 error 컬럼에서 원인을 확인하실 수 있습니다. "
                f"(흔한 원인: 모델 rate-limit·:free 한도 초과·토큰 한도·JSON 파싱 실패)"
            )
            status["report_ready"] = False
            status["finished_at"] = _now_iso()
            write_status(run_dir, status)
            print(
                f"[abort] n_ok=0 / n_fail={n_fail} — 보고서 생성을 건너뜁니다",
                file=sys.stderr,
                flush=True,
            )
            return 1

        # ── 보고서 컴파일 ─────────────────────────────
        if CANCEL:
            return _finalize_cancelled(run_dir, status)
        status["phase"] = "writing_report"
        write_status(run_dir, status)
        print("[4/4] 보고서 컴파일", flush=True)

        df_result = pd.DataFrame(rows_buffer)

        # (a) 헤더 — 코드 생성
        header_md = compose_header(
            spec,
            n_personas=len(df_personas),
            n_models=len(spec.get("models", [])),
            n_responses=len(df_result),
        )

        # (b) 측정 개요 — 코드 생성 (인포그래픽 PNG 3종도 run_dir에 저장)
        overview_md = compose_overview(spec, df_personas, df_result, run_dir=run_dir)

        # (c) 인사이트 — v6.2 자동 분기 파이프라인 (모드 A 단일 호출 / 모드 B 5단계)
        report_model = spec.get("report_model") or "openrouter/anthropic/claude-opus-4.7"
        topic_str = spec.get("topic", "") or "(주제 없음)"

        # 인사이트 prompt schema 사전 검증 — drift 즉시 차단 (zero cost)
        try:
            validate_insight_prompt_schema()
        except Exception as e:
            print(f"[abort] 인사이트 prompt schema 검증 실패: {e}", file=sys.stderr, flush=True)
            status["phase"] = "error"
            status["error"] = f"인사이트 prompt schema 검증 실패: {e}"
            status["finished_at"] = _now_iso()
            write_status(run_dir, status)
            return 4

        # 토큰 추산 → 모드 결정
        status["phase"] = "estimating_tokens"
        write_status(run_dir, status)
        input_tokens = estimate_input_tokens(
            df_result, df_personas,
            topic=topic_str, context=ctx, questions=questions,
        )
        mode = decide_mode(input_tokens)
        status["insight_mode"] = mode
        status["insight_input_tokens"] = input_tokens
        print(
            f"      인사이트 입력 추산: {input_tokens:,} 토큰 → 모드 {mode}",
            flush=True,
        )

        insight_json: Optional[Dict[str, Any]] = None
        insight_error: Optional[str] = None

        if mode == "A":
            # 모드 A — 단일 호출 (입력 ≤ 50만 토큰)
            status["phase"] = "calling_insight_llm"
            write_status(run_dir, status)
            try:
                report_user = build_report_input(
                    topic=topic_str,
                    context=ctx,
                    questions=questions,
                    df_result=df_result,
                    df_personas=df_personas,
                    spec=spec,
                )
                res = _call_insight_llm(
                    model_id=report_model,
                    system=INSIGHT_SINGLE_SYSTEM,
                    user=report_user,
                    timeout=600,
                )
                insight_json = res["parsed"]
            except Exception as e:
                insight_error = f"모드 A LLM 호출 실패: {e}"
                print(f"[warn] {insight_error}", file=sys.stderr, flush=True)
                status["error"] = (status.get("error") or "") + f" / insight_failed: {e}"
        else:
            # 모드 B — 5단계 파이프라인 (입력 > 50만 토큰)
            status["phase"] = "analyzing_clusters"
            write_status(run_dir, status)
            try:
                clusters = build_clusters(
                    df_result, df_personas,
                    seed=int(spec.get("seed", 42)),
                )
                n_clusters = len(clusters)
                status["insight_n_clusters"] = n_clusters
                status["insight_clusters_done"] = 0
                status["insight_clusters_failed"] = 0
                write_status(run_dir, status)
                print(
                    f"      모드 B — cluster {n_clusters}개로 분할, 병렬 분석 시작",
                    flush=True,
                )

                # 단계 2 — cluster 병렬 분석
                done_count = {"ok": 0, "fail": 0}

                def _cluster_progress(cid: str, st: str, elapsed: float) -> None:
                    if st == "ok":
                        done_count["ok"] += 1
                    else:
                        done_count["fail"] += 1
                    status["insight_clusters_done"] = done_count["ok"]
                    status["insight_clusters_failed"] = done_count["fail"]
                    write_status(run_dir, status)
                    print(
                        f"      [cluster {cid}] {st} ({elapsed:.1f}s) "
                        f"진행 {done_count['ok']}/{n_clusters}",
                        flush=True,
                    )

                cluster_results = analyze_clusters_parallel(
                    clusters,
                    topic=topic_str,
                    context=ctx,
                    questions=questions,
                    report_model=report_model,
                    timeout=600,
                    progress_cb=_cluster_progress,
                )

                # 단계 3 — cross-cluster diff
                status["phase"] = "cross_cluster_diff"
                write_status(run_dir, status)
                diff_result = cross_cluster_diff(
                    cluster_results,
                    topic=topic_str,
                    report_model=report_model,
                    timeout=600,
                )

                # 단계 4 — raw retrieval (default OFF)
                retrieval_results: List[Dict[str, Any]] = []
                if spec.get("insight_raw_retrieval"):
                    diff_summary = diff_result.get("summary") or {}
                    suspect_ids = diff_summary.get("suspect_cluster_ids") or []
                    suspect_reason = diff_summary.get("suspect_reason") or ""
                    if suspect_ids:
                        status["phase"] = "raw_retrieval"
                        write_status(run_dir, status)
                        retrieval_results = raw_retrieval_check(
                            suspect_ids, suspect_reason, clusters, cluster_results,
                            report_model=report_model, timeout=600,
                        )

                # 단계 5 — 합성
                status["phase"] = "synthesizing"
                write_status(run_dir, status)
                total_personas = sum(c["n_personas"] for c in clusters)
                total_responses = sum(c["n_responses"] for c in clusters)
                synth = synthesize_insights(
                    cluster_results, diff_result, retrieval_results,
                    topic=topic_str, context=ctx,
                    n_clusters=n_clusters,
                    total_personas=total_personas,
                    total_responses=total_responses,
                    report_model=report_model,
                    timeout=600,
                )
                insight_json = synth.get("summary")

                # 모드 B 부산물을 run_dir에 보존 — 디버깅·재현용
                try:
                    (run_dir / "insight_b_clusters.json").write_text(
                        json.dumps(
                            [
                                {
                                    "cluster_id": r.get("cluster_id"),
                                    "n_personas": r.get("n_personas"),
                                    "n_responses": r.get("n_responses"),
                                    "axis_dist": r.get("axis_dist"),
                                    "summary": r.get("summary"),
                                    "error": r.get("error"),
                                }
                                for r in cluster_results
                            ],
                            ensure_ascii=False, indent=2,
                        ),
                        encoding="utf-8",
                    )
                    (run_dir / "insight_b_diff.json").write_text(
                        json.dumps(diff_result.get("summary"), ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if retrieval_results:
                        (run_dir / "insight_b_retrieval.json").write_text(
                            json.dumps(retrieval_results, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                except Exception as e:
                    print(f"[warn] 모드 B 부산물 저장 실패: {e}", file=sys.stderr, flush=True)
            except Exception as e:
                insight_error = f"모드 B 파이프라인 실패: {e}"
                print(f"[warn] {insight_error}", file=sys.stderr, flush=True)
                status["error"] = (status.get("error") or "") + f" / insight_failed: {e}"

        status["phase"] = "writing_report"
        write_status(run_dir, status)

        if insight_json is None:
            insights_md = (
                "## 핵심 발견\n\n인사이트 생성에 실패했습니다.\n\n"
                f"오류: `{insight_error or 'JSON 파싱 실패'}`\n\n"
                "원천 응답은 result.csv에 그대로 남아 있습니다.\n"
            )
        else:
            try:
                (run_dir / "insight.json").write_text(
                    json.dumps(insight_json, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[warn] insight.json 저장 실패: {e}", file=sys.stderr, flush=True)
            insights_md = insight_json_to_markdown(insight_json)

        # (d) 인사이트를 둘로 분리 — (분석 표 + 핵심발견 + 가설) / (곱씹을응답 + 다음질문)
        # 분석 표(analysis_tables)는 인사이트 LLM이 자율 결정해 top_insights에 포함됨.
        top_insights, bottom_insights = split_insights(insights_md)

        # (e) 부록 — 코드 생성 (원본 질문/스키마/명세 포함)
        appendix_md = compose_appendix(spec, df_personas, df_result)

        # (f) 합치기: 헤더 + 주의문 + 측정개요 + (분석표·핵심발견·가설) + 곱씹을응답·다음질문 + 부록
        disclaimer = (
            "> ⚠️ **해석 주의**: 본 보고서는 합성 페르소나·LLM 시뮬레이션 결과입니다. "
            "실제 여론이 아니며, \"이 모델·이 표본에서는 ~한 신호가 보인다\" 정도로만 "
            "읽어 주세요.\n"
        )
        sections = [
            header_md,
            disclaimer,
            overview_md,
            top_insights,
            bottom_insights,
            appendix_md,
        ]
        report_md = "\n".join(s for s in sections if s and s.strip())

        (run_dir / "report.md").write_text(report_md, encoding="utf-8")

        # Observable Framework 빌드 — 측정 결과를 정적 사이트로
        status["phase"] = "observable_build"
        write_status(run_dir, status)
        observable_ok = False
        try:
            obs_dir = run_observable_build(run_dir)
            if obs_dir is not None:
                status["observable_ready"] = True
                status["observable_dir"] = obs_dir.name  # run_dir 기준 상대 (= "observable")
                observable_ok = True
            else:
                status["observable_ready"] = False
        except Exception as e:
            print(f"[warn] Observable 빌드 예외: {e!r}", file=sys.stderr, flush=True)
            status["observable_ready"] = False
            status["error"] = (status.get("error") or "") + f" / observable_build_failed: {e!r}"

        # Observable HTML → PDF (playwright Chromium) — 빌드가 성공한 경우에만 시도
        if observable_ok:
            status["phase"] = "observable_pdf"
            write_status(run_dir, status)
            try:
                pdf_path = render_observable_pdf(run_dir)
                if pdf_path is not None:
                    status["observable_pdf_ready"] = True
                else:
                    status["observable_pdf_ready"] = False
            except Exception as e:
                print(f"[warn] Observable PDF 예외: {e!r}", file=sys.stderr, flush=True)
                status["observable_pdf_ready"] = False
                status["error"] = (status.get("error") or "") + f" / observable_pdf_failed: {e!r}"

        # 옛 PDF/PNG 경로 (matplotlib 차트 제거 후에도 report.md → PDF/PNG는 호환성 유지)
        try:
            render_report_files(run_dir, report_md, spec.get("topic", "") or "보고서")
        except Exception as e:
            # PDF/PNG 실패해도 report.md는 남기고 보고서 미완성 표기
            print(f"[warn] PDF/PNG 렌더 실패: {e}", file=sys.stderr, flush=True)
            status["error"] = (status.get("error") or "") + f" / pdf_render_failed: {e}"

        try:
            build_sources_zip(run_dir)
        except Exception as e:
            print(f"[warn] sources.zip 생성 실패: {e}", file=sys.stderr, flush=True)
            status["error"] = (status.get("error") or "") + f" / zip_failed: {e}"

        status["report_ready"] = True
        status["phase"] = "done"
        status["finished_at"] = _now_iso()
        write_status(run_dir, status)
        print("[done]", flush=True)
        return 0

    except Exception as e:
        status["phase"] = "error"
        status["error"] = repr(e)
        status["finished_at"] = _now_iso()
        write_status(run_dir, status)
        print(f"[fatal] {e!r}", file=sys.stderr, flush=True)
        raise


def _finalize_cancelled(run_dir: Path, status: Dict[str, Any]) -> int:
    status["phase"] = "cancelled"
    status["finished_at"] = _now_iso()
    write_status(run_dir, status)
    print("[cancelled]", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python -m backend.run_worker <run_dir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))

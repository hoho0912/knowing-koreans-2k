"""
spec.json 사전 검증 — schema/engine drift 차단.

게이트웨이 [측정 시작] 직전과 워커 LLM 루프 진입 직전 두 군데에서 호출.
한 함수가 list[str]을 반환 — 빈 리스트면 OK, 아니면 차단·error 표시.

배경: 2026-04-29 B3 N=100 측정에서 question.md 5→7문항 갱신했으나
USER_TEMPLATE은 5문항 그대로 둠 → 25분 / 3,500원 손실. 그 재발 방지용
훅을 v5 게이트웨이에도 동일 적용.

v6.2 추가 (2026-05-01): 인사이트 단계 5종 prompt template과
공통 4섹션 JSON 출력 schema의 정합성도 함께 검증한다. 측정 단계는
통과해도 인사이트 단계가 깨져 있으면 보고서 합성에서 비용·시간
손실이 동일 패턴으로 발생하기 때문.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

_QUESTION_NUM_RE = re.compile(r"^(\d+)\)\s", re.MULTILINE)
_PREFIX_RE = re.compile(r'model_id\.startswith\(["\'](.+?)["\']\)')


def _import_validate_insight_prompt_schema():
    """prompt_builder.validate_insight_prompt_schema를 안전하게 import.

    CLI 단독 실행 시 sys.path 보정이 필요하다. 실패하면 None 반환 → 호출부에서
    "import 실패" 에러를 errors에 추가.
    """
    try:
        from backend.prompt_builder import validate_insight_prompt_schema  # noqa: F401
        return validate_insight_prompt_schema
    except ImportError:
        pass
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from backend.prompt_builder import validate_insight_prompt_schema  # noqa: F401
        return validate_insight_prompt_schema
    except Exception:
        return None


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """spec.json 내용 + 인사이트 prompt schema 검증. 빈 list = OK."""
    errors: List[str] = []

    questions = spec.get("questions", "") or ""
    qmd_nums = set(_QUESTION_NUM_RE.findall(questions))

    schema_block = spec.get("schema_block", "") or ""
    if schema_block.strip():
        try:
            schema = json.loads(schema_block)
        except json.JSONDecodeError as e:
            errors.append(f"응답 형식 JSON 파싱 실패: {e.msg} (line {e.lineno})")
            schema = None
    else:
        schema = {}

    if schema is not None and isinstance(schema, dict) and qmd_nums:
        n_q = len(qmd_nums)
        n_keys = len(schema)
        if n_q != n_keys:
            qs_sorted = sorted(int(x) for x in qmd_nums)
            errors.append(
                f"질문 {n_q}개 ↔ 응답 형식 키 {n_keys}개 불일치 "
                f"(질문 번호 {qs_sorted}, 키 {list(schema.keys())})"
            )

    # 외부 리뷰 #5 — 각 schema value가 dict인지 강제. string-value JSON이 통과하면
    # frontend-obs/src/data/scenario.json.py:108이 모든 응답 컬럼을 skip해 차트가
    # 비는 사고가 발생한다. type/scale/options/description 등 dict 필드가 필요.
    if schema is not None and isinstance(schema, dict):
        non_dict = [
            (k, type(v).__name__) for k, v in schema.items() if not isinstance(v, dict)
        ]
        if non_dict:
            preview = ", ".join(f"'{k}'({tn})" for k, tn in non_dict[:5])
            errors.append(
                f"응답 형식 값이 dict가 아닌 키 {len(non_dict)}건: {preview}. "
                "각 키는 type·scale/options·description 등을 dict로 정의해야 합니다."
            )

    runner_path = Path(__file__).parent / "llm_runner.py"
    if runner_path.exists():
        src = runner_path.read_text(encoding="utf-8")
        supported = set(_PREFIX_RE.findall(src))
        if supported:
            all_models: List[str] = list(spec.get("models", []) or [])
            for k in ("qgen_model", "report_model"):
                v = spec.get(k)
                if v:
                    all_models.append(v)
            for m in all_models:
                if not any(m.startswith(p) for p in supported):
                    errors.append(f"지원되지 않는 모델: {m}")

    # v6.2 — 인사이트 단계 prompt template ↔ 공통 출력 schema 정합성
    validator = _import_validate_insight_prompt_schema()
    if validator is None:
        errors.append("인사이트 prompt 검증 함수 import 실패 — backend/prompt_builder.py 확인 필요")
    else:
        try:
            validator()
        except Exception as e:
            errors.append(f"인사이트 prompt schema 불일치: {e}")

    return errors


if __name__ == "__main__":
    import sys

    spec_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if spec_path and spec_path.exists():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    else:
        spec = {
            "questions": "1) 첫 질문\n2) 두 번째 질문\n3) 세 번째",
            "schema_block": '{"q1": "score", "q2": "yes/no"}',
            "models": ["openrouter/qwen/qwen3-max"],
            "qgen_model": "openrouter/anthropic/claude-sonnet-4.6",
            "report_model": "openrouter/anthropic/claude-opus-4.7",
        }

    errors = validate_spec(spec)
    if errors:
        print("검증 실패:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("검증 통과 ✓")

"""
Run Scenario — 시나리오 디렉토리를 받아 N명 시뮬 실행하는 엔트리포인트

사용 예:
    python -m backend.run_scenario \\
        --scenario-id exhibition_appeal \\
        --context-snapshot 2026-04 \\
        --models "openai/gpt-4o-mini,ollama/qwen2.5:7b" \\
        --n 5 \\
        --seed 42

각 페르소나 × 모델 조합으로 1건씩 호출. 한 건이라도 성공하면
backend/results/<scenario_id>_<context_snapshot>.csv에 누적됨.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.llm_runner import call_llm, parse_json_response
from backend.persona_sampler import load_all_personas, sample_personas
from backend.prompt_builder import build_prompt
from backend.results_writer import (
    append_csv_row,
    build_result_row,
    now_compact,
    now_iso,
    write_response_json,
)

PROJECT_ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"


def load_scenario_vars(scenario_dir: Path) -> Dict[str, Any]:
    """scenario_vars.json 우선, 없으면 placeholder."""
    vars_path = scenario_dir / "scenario_vars.json"
    if vars_path.exists():
        return json.loads(vars_path.read_text(encoding="utf-8"))
    print(f"[info] {vars_path} 없음 → placeholder 가상 기획안 사용 (dry run 적합)")
    return {
        "exhibition_title": "(placeholder) 가상 전시",
        "exhibition_subtitle": "사용자 1차 자료 대기 중",
        "exhibition_period": "2026.05.01 ~ 2026.07.31",
        "exhibition_venue": "(placeholder) 미정",
        "exhibition_admission": "무료",
        "exhibition_concept": "사용자가 1차 자료 제공 시 교체 예정. 현재는 dry run용 placeholder.",
        "exhibition_highlights": "- 항목 1\n- 항목 2",
    }


def run(
    scenario_id: str,
    context_snapshot_id: str,
    models: List[str],
    n: int,
    seed: int,
    *,
    temperature: float = 0.7,
    dry_run: bool = False,
    province: Optional[str] = None,
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    sex: Optional[str] = None,
    education_level: Optional[str] = None,
    occupation: Optional[str] = None,
    stratify_by: Optional[str] = None,
) -> Dict[str, Any]:
    scenario_dir = SCENARIOS_DIR / scenario_id
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"시나리오 폴더 없음: {scenario_dir}")

    filter_desc = []
    if province:
        filter_desc.append(f"province={province}")
    if age_min is not None or age_max is not None:
        filter_desc.append(f"age={age_min or '_'}~{age_max or '_'}")
    if sex:
        filter_desc.append(f"sex={sex}")
    if education_level:
        filter_desc.append(f"education_level={education_level}")
    if occupation:
        filter_desc.append(f"occupation={occupation}")
    if stratify_by:
        filter_desc.append(f"stratify_by={stratify_by}")
    filter_summary = ", ".join(filter_desc) if filter_desc else "(필터 없음)"

    print(f"[1/4] 페르소나 로드 + 샘플링 (n={n}, seed={seed}, {filter_summary})")
    df = load_all_personas()
    print(f"      전체 {len(df):,}행, {len(df.columns)} 컬럼")
    sample = sample_personas(
        n=n,
        seed=seed,
        df=df,
        province=province,
        age_min=age_min,
        age_max=age_max,
        sex=sex,
        education_level=education_level,
        occupation=occupation,
        stratify_by=stratify_by,
    )
    print(f"      샘플 {len(sample)}건")
    if stratify_by and stratify_by in sample.columns:
        dist = sample[stratify_by].value_counts().to_dict()
        print(f"      {stratify_by} 분포: {dist}")

    print(f"[2/4] 시나리오 변수 로드: {scenario_dir.name}")
    scenario_vars = load_scenario_vars(scenario_dir)

    total_calls = len(sample) * len(models)
    print(
        f"[3/4] 시뮬 실행 ({len(sample)} 페르소나 × {len(models)} 모델 = {total_calls}건)"
    )

    summary: Dict[str, Any] = {
        "scenario_id": scenario_id,
        "context_snapshot_id": context_snapshot_id,
        "n": n,
        "seed": seed,
        "models": models,
        "successes": 0,
        "failures": 0,
        "errors": [],
    }

    for i, persona in sample.iterrows():
        for model_id in models:
            try:
                prompt = build_prompt(persona, scenario_dir, scenario_vars)
                if dry_run:
                    print(f"  [dry] persona {i} × {model_id} — 프롬프트 빌드만")
                    summary["successes"] += 1
                    continue

                resp = call_llm(
                    model_id=model_id,
                    system=prompt["system"],
                    user=prompt["user"],
                    temperature=temperature,
                    json_mode=True,
                )
                parsed = parse_json_response(resp.text)

                ts = now_compact()
                persona_uuid = str(persona.get("persona_uuid", f"row{i}"))
                response_file = write_response_json(
                    persona_uuid=persona_uuid,
                    model_id=model_id,
                    payload={
                        "persona_uuid": persona_uuid,
                        "model_id": model_id,
                        "scenario_id": scenario_id,
                        "context_snapshot_id": context_snapshot_id,
                        "seed": seed,
                        "timestamp": now_iso(),
                        "prompt": prompt,
                        "response": resp.to_dict(),
                        "parsed": parsed,
                    },
                    timestamp=ts,
                )

                row = build_result_row(
                    persona_row=persona.to_dict(),
                    scenario_id=scenario_id,
                    context_snapshot_id=context_snapshot_id,
                    model_id=model_id,
                    seed=seed,
                    parsed_response=parsed,
                    elapsed_sec=resp.elapsed_sec,
                    response_file=response_file.name,
                )
                append_csv_row(scenario_id, context_snapshot_id, row)

                score = parsed.get("appeal_score", "?")
                print(
                    f"  [ok] persona {i} × {model_id} "
                    f"({resp.elapsed_sec:.2f}s, score={score})"
                )
                summary["successes"] += 1

            except Exception as e:
                print(f"  [fail] persona {i} × {model_id}: {type(e).__name__}: {e}")
                traceback.print_exc()
                summary["failures"] += 1
                summary["errors"].append(
                    {"i": int(i), "model": model_id, "error": str(e)}
                )

    print(
        f"[4/4] 완료. 성공 {summary['successes']} / 실패 {summary['failures']}\n"
        f"      CSV: backend/results/{scenario_id}_{context_snapshot_id}.csv"
    )
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="시나리오 시뮬 실행기")
    p.add_argument("--scenario-id", required=True, help="예: exhibition_appeal")
    p.add_argument("--context-snapshot", required=True, help="예: 2026-04")
    p.add_argument(
        "--models",
        required=True,
        help="콤마로 구분된 model_id 목록 (예: openai/gpt-4o-mini,ollama/qwen2.5:7b)",
    )
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="LLM 호출 없이 프롬프트 빌드만 (API 키 불필요)",
    )
    # demographic 필터·층화 추출
    p.add_argument("--province", help="시도 필터 (예: '서울' 또는 '서울,경기')")
    p.add_argument("--age-min", type=int, help="최소 나이 (포함)")
    p.add_argument("--age-max", type=int, help="최대 나이 (포함)")
    p.add_argument("--sex", help="'남자' 또는 '여자'")
    p.add_argument("--education-level", help="학력 필터 (예: '4년제 대학교')")
    p.add_argument("--occupation", help="직업 필터 (정확히 일치)")
    p.add_argument(
        "--stratify-by",
        help="균등 추출 기준 컬럼 (예: age_bucket, province, sex)",
    )

    args = p.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        print("[error] --models 비어있음", file=sys.stderr)
        return 2

    summary = run(
        scenario_id=args.scenario_id,
        context_snapshot_id=args.context_snapshot,
        models=models,
        n=args.n,
        seed=args.seed,
        temperature=args.temperature,
        dry_run=args.dry_run,
        province=args.province,
        age_min=args.age_min,
        age_max=args.age_max,
        sex=args.sex,
        education_level=args.education_level,
        occupation=args.occupation,
        stratify_by=args.stratify_by,
    )
    return 0 if summary["failures"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

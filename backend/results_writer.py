"""
Results Writer — CSV 누적 + raw JSON 저장

CSV: backend/results/<scenario_id>_<context_snapshot>.csv  (한 시뮬 행 = CSV 한 행)
Raw: backend/response/<persona_uuid>_<model_safe>_<timestamp>.json
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

BACKEND_DIR = Path(__file__).parent
RESULTS_DIR = BACKEND_DIR / "results"
RESPONSE_DIR = BACKEND_DIR / "response"


def _safe(s: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def now_compact() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def write_response_json(
    persona_uuid: str,
    model_id: str,
    payload: Dict[str, Any],
    timestamp: Optional[str] = None,
    response_dir: Path = RESPONSE_DIR,
) -> Path:
    """raw JSON 1건을 별도 파일로 저장. 저장 경로 반환."""
    timestamp = timestamp or now_compact()
    response_dir = Path(response_dir)
    response_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe(persona_uuid)}_{_safe(model_id)}_{timestamp}.json"
    path = response_dir / filename
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def append_csv_row(
    scenario_id: str,
    context_snapshot_id: str,
    row: Dict[str, Any],
    results_dir: Path = RESULTS_DIR,
) -> Path:
    """CSV 한 행 추가. 파일 없으면 헤더 포함 신규 생성.

    이미 존재하는 CSV에 새 컬럼이 추가되면 경고 후 기존 헤더 기준으로만 저장
    (조용히 새 컬럼 추가는 위험 — 기존 행이 빈칸으로 변하기 때문).
    """
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe(scenario_id)}_{_safe(context_snapshot_id)}.csv"
    path = results_dir / filename

    file_exists = path.exists()
    fieldnames = list(row.keys())

    if file_exists:
        with path.open("r", encoding="utf-8") as f:
            existing_header = f.readline().strip().split(",")
        new_cols = [c for c in fieldnames if c not in existing_header]
        if new_cols:
            print(f"[warn] CSV에 없는 새 컬럼 무시: {new_cols}")
        fieldnames = existing_header

    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})

    return path


def build_result_row(
    persona_row: Dict[str, Any],
    scenario_id: str,
    context_snapshot_id: str,
    model_id: str,
    seed: int,
    parsed_response: Dict[str, Any],
    elapsed_sec: float,
    response_file: str,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """페르소나 + 시뮬 결과를 CSV 한 행으로 평탄화."""
    row: Dict[str, Any] = {
        "persona_uuid": persona_row.get("persona_uuid", ""),
        "model": model_id,
        "scenario_id": scenario_id,
        "context_snapshot_id": context_snapshot_id,
        "seed": seed,
        "elapsed_sec": round(elapsed_sec, 3),
        "timestamp": timestamp or now_iso(),
        "response_file": response_file,
    }
    # 응답 필드 (시나리오별 가변)
    for k, v in parsed_response.items():
        row[k] = v
    # 페르소나 26 필드 사본 (이미 있는 키는 덮어쓰지 않음)
    for k, v in persona_row.items():
        if k not in row and not k.startswith("_"):
            row[k] = v
    return row

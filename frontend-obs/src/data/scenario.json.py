"""Schema-aware Observable Framework data loader.

KK_RUN_DIR 환경변수에 측정 결과 디렉토리(spec.json/result.csv/personas.csv/
status.json/insight.json 보유)를 넘기면 자동 분석. 미지정 시 default(N=1000
박물관 관람료 무료화)로 fallback.

설계 원칙:
  1. spec.schema_block 자동 파싱 → numeric/categorical/freetext 분류
  2. distributions 자동 — numeric은 1~5 빈도, categorical은 옵션 빈도
  3. crosstab 축은 spec.primary_outcome_col 또는 첫 numeric 질문 자동 선택
  4. sample_responses 키는 detected schema에 따라 동적
  5. Likert label은 scale 텍스트에서 자동 추출 (한글)
  6. freetext 키워드 빈도 — spec.freetext_keywords 명시 안 되면 skip
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import pandas as pd


# ─────────────────────────────────────────────────────────
# 입력 경로 — KK_RUN_DIR 우선, 없으면 default
# ─────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = ROOT / "frontend" / "data" / "run_N1000_museum-admission-free"
RUN_DIR = Path(os.environ.get("KK_RUN_DIR") or DEFAULT_RUN_DIR)


# ─────────────────────────────────────────────────────────
# Likert 한글 라벨 — backend/run_worker.py 와 동일 패턴
# ─────────────────────────────────────────────────────────

def _likert_labels_from_scale(scale: Any) -> Optional[list[str]]:
    if not isinstance(scale, str) or not scale.strip():
        return None
    s = scale
    if "반대" in s and "찬성" in s:
        return ["매우 반대", "반대", "중립", "찬성", "매우 찬성"]
    if "그렇지" in s and "그렇다" in s:
        return ["전혀 아니다", "아니다", "보통", "그렇다", "매우 그렇다"]
    if "만족" in s and ("불만" in s or "매우" in s):
        return ["매우 불만족", "불만족", "보통", "만족", "매우 만족"]
    if "중요" in s and ("않" in s or "전혀" in s):
        return ["전혀 중요X", "중요 낮음", "보통", "중요", "매우 중요"]
    if ("빈도" in s or "자주" in s) and ("없" in s or "않" in s):
        return ["전혀 없음", "거의 없음", "가끔", "자주", "매우 자주"]

    matches = dict(re.findall(r"(\d)\s*=\s*([^,)]+?)(?=\s*[,)]|$)", s))
    if "1" in matches and "5" in matches:
        def _short(t: str, n: int = 14) -> str:
            t = t.strip().rstrip(".")
            return t if len(t) <= n else t[:n] + "…"
        l1 = _short(matches["1"])
        l5 = _short(matches["5"])
        l3 = _short(matches.get("3", "")) if matches.get("3", "").strip() else "3"
        return [l1, "2", l3, "4", l5]
    return None


def _classify_urban(province: Any) -> str:
    """페르소나 province → 수도권/광역시/그 외."""
    if not isinstance(province, str):
        return "그 외"
    if province in ("서울", "서울특별시", "경기", "경기도", "인천", "인천광역시"):
        return "수도권"
    if province in (
        "부산", "부산광역시", "대구", "대구광역시", "광주", "광주광역시",
        "대전", "대전광역시", "울산", "울산광역시",
    ):
        return "광역시"
    return "그 외"


# ─────────────────────────────────────────────────────────
# schema 자동 검출
# ─────────────────────────────────────────────────────────

def _detect_schema(schema_block_raw: Any, df: pd.DataFrame) -> dict:
    """spec.schema_block + result.csv 컬럼 교차해서 응답 컬럼 메타 추출."""
    try:
        schema = (
            json.loads(schema_block_raw)
            if isinstance(schema_block_raw, str)
            else schema_block_raw
        )
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(schema, dict):
        return {}

    detected: dict = {}
    for q_key, q_def in schema.items():
        col = f"resp_{q_key}"
        if col not in df.columns or not isinstance(q_def, dict):
            continue
        t = q_def.get("type", "")
        options = q_def.get("options") or q_def.get("enum")
        scale = q_def.get("scale", "")
        min_length = q_def.get("min_length")
        desc = q_def.get("description", "") or ""

        scale_range = None
        if t == "integer" or "Likert" in str(scale) or "likert" in str(scale).lower():
            type_class = "numeric"
            scale_range = [1, 5]
            m = re.search(r"(\d+)\s*[-~]\s*(\d+)", str(scale))
            if m:
                scale_range = [int(m.group(1)), int(m.group(2))]
        elif options and isinstance(options, list) and len(options) > 0:
            type_class = "categorical"
        elif t == "string" and (min_length or "자유" in desc or "서술" in desc):
            type_class = "freetext"
        else:
            type_class = "categorical" if options else "freetext"

        likert_labels = (
            _likert_labels_from_scale(scale) if type_class == "numeric" else None
        )

        detected[col] = {
            "q_key": q_key,
            "col": col,
            "type_class": type_class,
            "options": options if isinstance(options, list) else None,
            "scale_range": scale_range,
            "scale_text": str(scale) if scale else "",
            "description": desc,
            "likert_labels": likert_labels,
        }
    return detected


# ─────────────────────────────────────────────────────────
# 정규화 헬퍼
# ─────────────────────────────────────────────────────────

def to_int_likert(v: Any) -> Optional[int]:
    """Likert 응답을 1~5 정수로 강제. schema echo·NaN·범위 외 → None."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    m = re.match(r"^([1-5])\b", s)
    if not m:
        return None
    return int(m.group(1))


def normalize_categorical(v: Any, options: list) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    if not s:
        return None
    for opt in options:
        if opt in s:
            return opt
    return None


def parse_questions_text(qtxt: str) -> dict:
    """1) ... 2) ... 형태 → {1: "질문본문", 2: "..."} dict."""
    if not qtxt:
        return {}
    out: dict = {}
    blocks = re.split(r"^(\d+)\)\s*", qtxt.strip(), flags=re.MULTILINE)
    for i in range(1, len(blocks), 2):
        try:
            num = int(blocks[i])
            text = blocks[i + 1].strip()
            out[num] = text
        except (IndexError, ValueError):
            continue
    return out


# ─────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────

def main() -> None:
    spec_path = RUN_DIR / "spec.json"
    result_csv = RUN_DIR / "result.csv"
    personas_csv = RUN_DIR / "personas.csv"
    status_path = RUN_DIR / "status.json"
    insight_path = RUN_DIR / "insight.json"

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    status = (
        json.loads(status_path.read_text(encoding="utf-8"))
        if status_path.exists()
        else {}
    )
    insight = (
        json.loads(insight_path.read_text(encoding="utf-8"))
        if insight_path.exists()
        else {}
    )

    result = pd.read_csv(result_csv)
    personas = pd.read_csv(personas_csv)

    persona_cols = [
        c
        for c in [
            "persona_uuid",
            "sex",
            "age",
            "age_bucket",
            "province",
            "education_level",
            "bachelors_field",
            "occupation",
            "marital_status",
            "family_type",
            "arts_persona",
            "professional_persona",
            "cultural_background",
            "hobbies_and_interests",
        ]
        if c in personas.columns
    ]
    df = result.merge(personas[persona_cols], on="persona_uuid", how="left")

    # ok 필터
    if "ok" in df.columns:
        df_ok = df[df["ok"] == True].copy()  # noqa: E712
    else:
        df_ok = df.copy()
    n_ok = len(df_ok)

    # urban region 자동 부여
    if "province" in df_ok.columns:
        df_ok["region"] = df_ok["province"].apply(_classify_urban)

    # schema 자동 검출
    detected = _detect_schema(spec.get("schema_block", ""), df_ok)

    # 응답 정규화
    for col, meta in detected.items():
        if meta["type_class"] == "numeric":
            df_ok[col + "_int"] = df_ok[col].apply(to_int_likert)
        elif meta["type_class"] == "categorical" and meta["options"]:
            opts = meta["options"]
            df_ok[col + "_norm"] = df_ok[col].apply(
                lambda v, o=opts: normalize_categorical(v, o)
            )

    # numeric 응답이 모두 valid한 행만 분포·crosstab에 활용
    numeric_cols = [c for c, m in detected.items() if m["type_class"] == "numeric"]
    if numeric_cols:
        df_ok["_likert_valid"] = df_ok[
            [c + "_int" for c in numeric_cols]
        ].notna().all(axis=1)
        df_valid = df_ok[df_ok["_likert_valid"]].copy()
    else:
        df_valid = df_ok.copy()
    n_schema_echo = n_ok - len(df_valid)
    valid_n = len(df_valid)

    # 질문 텍스트 매핑
    q_text_map = parse_questions_text(spec.get("questions", "") or "")

    # questions 메타 — index.md 에 그대로 넘김 (q_num 순 정렬)
    questions = []
    for col, meta in detected.items():
        m = re.match(r"q(\d+)", meta["q_key"])
        q_num = int(m.group(1)) if m else 0
        q_text = q_text_map.get(q_num, meta["q_key"])
        entry = dict(meta)
        entry["q_num"] = q_num
        entry["q_text"] = q_text
        questions.append(entry)
    questions.sort(key=lambda e: e["q_num"])

    # distributions 자동 생성
    freetext_kws_block = spec.get("freetext_keywords")
    if not isinstance(freetext_kws_block, dict):
        freetext_kws_block = {}

    distributions: dict = {}
    for q in questions:
        col = q["col"]
        tc = q["type_class"]
        if tc == "numeric":
            r = q["scale_range"] or [1, 5]
            lo, hi = r[0], r[1]
            cnt = Counter(int(v) for v in df_valid[col + "_int"].dropna())
            distributions[col] = {
                "type": "numeric",
                "data": [{"value": v, "count": cnt.get(v, 0)} for v in range(lo, hi + 1)],
                "labels": q["likert_labels"],
                "range": [lo, hi],
            }
        elif tc == "categorical" and q["options"]:
            cnt = Counter(v for v in df_valid[col + "_norm"] if v)
            distributions[col] = {
                "type": "categorical",
                "data": [
                    {"label": opt, "count": cnt.get(opt, 0)} for opt in q["options"]
                ],
            }
        elif tc == "freetext":
            kws_pairs = freetext_kws_block.get(q["q_key"]) if freetext_kws_block else None
            items = []
            if isinstance(kws_pairs, list):
                for entry in kws_pairs:
                    if (
                        isinstance(entry, (list, tuple))
                        and len(entry) == 2
                        and isinstance(entry[1], list)
                    ):
                        label, kws = entry
                        cnt = sum(
                            1
                            for txt in df_valid[col].dropna()
                            if any(kw in str(txt) for kw in kws)
                        )
                        items.append({"label": label, "count": cnt})
            distributions[col] = {"type": "freetext", "data": items}

    # primary numeric col — crosstab 축
    primary_col = spec.get("primary_outcome_col")
    if primary_col not in detected:
        primary_col = None
    if not primary_col:
        for q in questions:
            if q["type_class"] == "numeric":
                primary_col = q["col"]
                break

    crosstabs: dict = {}
    if primary_col:
        primary_int = primary_col + "_int"
        primary_meta = next(q for q in questions if q["col"] == primary_col)
        for axis_col, axis_label in [
            ("age_bucket", "age"),
            ("sex", "sex"),
            ("province", "province"),
            ("education_level", "education"),
            ("occupation", "occupation"),
            ("region", "region"),
        ]:
            if axis_col not in df_valid.columns:
                continue
            sub = df_valid[[axis_col, primary_int]].dropna()
            if axis_col == "occupation":
                top12 = sub[axis_col].value_counts().head(12).index.tolist()
                sub = sub[sub[axis_col].isin(top12)]
            rows = []
            for (key, val), g in sub.groupby([axis_col, primary_int]):
                rows.append(
                    {"group": str(key), "value": int(val), "count": int(len(g))}
                )
            crosstabs[axis_label] = rows
        crosstabs["_meta"] = {
            "primary_col": primary_col,
            "primary_q_num": primary_meta["q_num"],
            "primary_q_text": primary_meta["q_text"],
            "labels": primary_meta["likert_labels"],
            "range": primary_meta["scale_range"],
        }

    # sample 응답 카드 — primary numeric 분포에 맞춰 골고루
    sample_rows = []
    if primary_col:
        primary_int = primary_col + "_int"
        for v in range(1, 6):
            sub = df_valid[df_valid[primary_int] == v]
            take = min(6, len(sub))
            if take == 0:
                continue
            for _, row in sub.sample(n=take, random_state=42 + v).iterrows():
                rec = {
                    "persona_uuid": str(row.get("persona_uuid", "")),
                    "sex": str(row.get("sex", "") or ""),
                    "age": int(row["age"]) if pd.notna(row.get("age")) else None,
                    "age_bucket": str(row.get("age_bucket", "") or ""),
                    "province": str(row.get("province", "") or ""),
                    "education_level": str(row.get("education_level", "") or ""),
                    "occupation": str(row.get("occupation", "") or ""),
                    "marital_status": str(row.get("marital_status", "") or ""),
                    "arts_persona": str(row.get("arts_persona", "") or "")[:200],
                    "_primary": int(v),
                }
                # 모든 응답 컬럼 동적 dump
                for q in questions:
                    col = q["col"]
                    if q["type_class"] == "numeric":
                        v_int = row.get(col + "_int")
                        rec[q["q_key"]] = int(v_int) if pd.notna(v_int) else None
                    elif q["type_class"] == "categorical":
                        rec[q["q_key"]] = str(row.get(col + "_norm", "") or "")
                    else:
                        rec[q["q_key"]] = str(row.get(col, "") or "")[:240]
                sample_rows.append(rec)

    # 출력
    out = {
        "meta": {
            "run_id": status.get("run_id", spec.get("run_id", "")),
            "n_total": status.get("n_total", spec.get("n", 0)),
            "n_ok": n_ok,
            "n_fail": status.get("n_fail", 0),
            "n_schema_echo": n_schema_echo,
            "valid_n": valid_n,
            "started_at": status.get("started_at", ""),
            "finished_at": status.get("finished_at", ""),
            "avg_sec_per_call": status.get("avg_sec_per_call", 0),
            "insight_mode": status.get("insight_mode", ""),
            "insight_n_clusters": status.get("insight_n_clusters", 0),
            "models": spec.get("models", []),
            "report_model": spec.get("report_model", ""),
            "qgen_model": spec.get("qgen_model", ""),
            "seed": spec.get("seed", None),
            "filters": spec.get("filters", {}),
        },
        "spec": {
            "topic": spec.get("topic", ""),
            "ctx": spec.get("ctx", ""),
            "questions": spec.get("questions", ""),
            "schema_block": spec.get("schema_block", ""),
        },
        "questions": questions,
        "primary_col": primary_col,
        "distributions": distributions,
        "crosstabs": crosstabs,
        "sample_responses": sample_rows,
        "insight": {
            "key_findings": insight.get("key_findings", []),
            "curator_hypotheses": insight.get("curator_hypotheses", []),
            "responses_to_chew_on": insight.get("responses_to_chew_on", []),
            "next_questions": insight.get("next_questions", []),
        },
    }

    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()

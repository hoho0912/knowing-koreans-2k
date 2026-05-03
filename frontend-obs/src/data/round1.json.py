"""Observable Framework data loader — N=1,000 박물관 관람료 무료화 라운드.

result.csv (998건 응답) + personas.csv (1,000건 페르소나)를 join.
schema echo 행을 제외한 valid 응답만 분포·crosstab 계산에 활용.
시각화 페이지에서 쓰는 모든 집계를 한 번에 stdout JSON 으로 출력.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

# 입력 경로 — frontend-obs/src/data 기준 ../../../frontend/data/...
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "frontend" / "data" / "run_N1000_museum-admission-free"

RESULT_CSV = DATA_DIR / "result.csv"
PERSONAS_CSV = DATA_DIR / "personas.csv"
INSIGHT_JSON = DATA_DIR / "insight.json"
STATUS_JSON = DATA_DIR / "status.json"
SPEC_JSON = DATA_DIR / "spec.json"

LIKERT_QS = [
    "resp_q1_admission_fee_support",
    "resp_q2_alternative_first",
    "resp_q3_oppose_even_with_exemption",
]
Q4 = "resp_q4_willingness_to_pay"
Q5 = "resp_q5_open_opinion"

Q4_ORDER = [
    "무료여야 한다",
    "1,000원 미만",
    "1,000~3,000원",
    "3,000~5,000원",
    "5,000~10,000원",
    "10,000원 이상",
]


def to_int_likert(v) -> int | None:
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


def normalize_q4(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    if not s:
        return None
    for opt in Q4_ORDER:
        if opt in s:
            return opt
    return None


def main() -> None:
    result = pd.read_csv(RESULT_CSV)
    personas = pd.read_csv(PERSONAS_CSV)

    persona_cols = [
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
    personas_slim = personas[persona_cols].copy()

    df = result.merge(personas_slim, on="persona_uuid", how="left")

    # Likert 정규화
    for col in LIKERT_QS:
        df[col + "_int"] = df[col].apply(to_int_likert)
    df[Q4 + "_norm"] = df[Q4].apply(normalize_q4)

    # ok 필터
    df_ok = df[df["ok"] == True].copy()  # noqa: E712
    n_ok = len(df_ok)

    # schema echo: q1~q3 어느 하나라도 정수 변환 실패시 → schema echo로 분류
    likert_int_cols = [c + "_int" for c in LIKERT_QS]
    df_ok["_likert_valid"] = df_ok[likert_int_cols].notna().all(axis=1)
    df_valid = df_ok[df_ok["_likert_valid"]].copy()
    n_schema_echo = n_ok - len(df_valid)
    valid_n = len(df_valid)

    # q1~q3 분포
    def likert_dist(col: str) -> list[dict]:
        c = Counter(int(v) for v in df_valid[col + "_int"].dropna())
        return [{"value": v, "count": c.get(v, 0)} for v in [1, 2, 3, 4, 5]]

    q1_dist = likert_dist("resp_q1_admission_fee_support")
    q2_dist = likert_dist("resp_q2_alternative_first")
    q3_dist = likert_dist("resp_q3_oppose_even_with_exemption")

    # q4 분포 (정규화 후)
    q4_counter = Counter(v for v in df_valid[Q4 + "_norm"] if v)
    q4_dist = [{"label": opt, "count": q4_counter.get(opt, 0)} for opt in Q4_ORDER]

    # q5 토픽 키워드 빈도 (간이 — 보고서 시각화용)
    topic_keywords = [
        ("취약계층·학생·어르신 무료/할인", ["취약계층", "학생", "어르신", "무료", "할인", "저소득"]),
        ("기본 전시 무료 유지 + 특별전·기부", ["기본", "특별전", "기부", "후원", "무료 유지"]),
        ("재정 다변화·품질 향상", ["재정", "품질", "수준", "향상", "다변화"]),
        ("접근성·문화 향유권", ["접근", "향유", "공공", "문화재", "공동"]),
        ("SNS 사진족·진지 관람층 구분", ["SNS", "사진", "진지", "관람층"]),
        ("해외 사례 인용 (루브르·대영)", ["루브르", "대영", "외국", "해외"]),
    ]
    q5_freq = []
    for label, kws in topic_keywords:
        cnt = 0
        for txt in df_valid[Q5].dropna():
            if any(kw in str(txt) for kw in kws):
                cnt += 1
        q5_freq.append({"label": label, "count": cnt})

    # demographic crosstab — q1 기준
    def crosstab(field: str, top_n: int | None = None) -> list[dict]:
        if field not in df_valid.columns:
            return []
        sub = df_valid[[field, "resp_q1_admission_fee_support_int"]].dropna()
        if top_n is not None:
            top_vals = sub[field].value_counts().head(top_n).index.tolist()
            sub = sub[sub[field].isin(top_vals)]
        rows = []
        for (key, q1), g in sub.groupby([field, "resp_q1_admission_fee_support_int"]):
            rows.append({"group": str(key), "q1": int(q1), "count": int(len(g))})
        return rows

    crosstab_age = crosstab("age_bucket")
    crosstab_sex = crosstab("sex")
    crosstab_province = crosstab("province")
    crosstab_education = crosstab("education_level")
    crosstab_occupation = crosstab("occupation", top_n=12)

    # 응답 카드 — 30건 골고루 (q1 1~5 분포에 맞춰)
    sample_rows = []
    for q1_val in [1, 2, 3, 4, 5]:
        sub = df_valid[df_valid["resp_q1_admission_fee_support_int"] == q1_val]
        take = min(6, len(sub))
        for _, row in sub.sample(n=take, random_state=42 + q1_val).iterrows():
            sample_rows.append(
                {
                    "persona_uuid": str(row.get("persona_uuid", "")),
                    "sex": str(row.get("sex", "") or ""),
                    "age": int(row["age"]) if pd.notna(row.get("age")) else None,
                    "age_bucket": str(row.get("age_bucket", "") or ""),
                    "province": str(row.get("province", "") or ""),
                    "education_level": str(row.get("education_level", "") or ""),
                    "occupation": str(row.get("occupation", "") or ""),
                    "marital_status": str(row.get("marital_status", "") or ""),
                    "q1": int(row["resp_q1_admission_fee_support_int"]),
                    "q2": int(row["resp_q2_alternative_first_int"]),
                    "q3": int(row["resp_q3_oppose_even_with_exemption_int"]),
                    "q4": str(row.get(Q4 + "_norm", "") or ""),
                    "q5": str(row.get(Q5, "") or "")[:240],
                    "arts_persona": str(row.get("arts_persona", "") or "")[:200],
                }
            )

    # meta + status + insight + spec
    status = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
    insight = json.loads(INSIGHT_JSON.read_text(encoding="utf-8"))
    spec = json.loads(SPEC_JSON.read_text(encoding="utf-8"))

    out = {
        "meta": {
            "run_id": status.get("run_id", ""),
            "n_total": status.get("n_total", 1000),
            "n_ok": n_ok,
            "n_fail": status.get("n_fail", 0),
            "n_schema_echo": n_schema_echo,
            "valid_n": valid_n,
            "started_at": status.get("started_at", ""),
            "finished_at": status.get("finished_at", ""),
            "avg_sec_per_call": status.get("avg_sec_per_call", 0),
            "insight_mode": status.get("insight_mode", "B"),
            "insight_n_clusters": status.get("insight_n_clusters", 0),
            "models": spec.get("models", []),
            "report_model": spec.get("report_model", ""),
            "qgen_model": spec.get("qgen_model", ""),
            "seed": spec.get("seed", None),
        },
        "spec": {
            "topic": spec.get("topic", ""),
            "ctx": spec.get("ctx", ""),
            "questions": spec.get("questions", ""),
            "schema_block": spec.get("schema_block", ""),
        },
        "distributions": {
            "q1": q1_dist,
            "q2": q2_dist,
            "q3": q3_dist,
            "q4": q4_dist,
            "q5_topic_freq": q5_freq,
        },
        "crosstabs": {
            "age": crosstab_age,
            "sex": crosstab_sex,
            "province": crosstab_province,
            "education": crosstab_education,
            "occupation": crosstab_occupation,
        },
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

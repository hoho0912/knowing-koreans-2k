"""
Smoke test 결과 분석 — 7 후보 모델의 within-model std 비교

기존 측정(claude-haiku 0.75 기준)에 새 후보 모델들이 어떤 std를 보이는지 측정.
페르소나 신호를 통과시키는 정도를 std로 잡고, 0.5 이상이면 본 측정 후보로 추천.
"""

import pandas as pd

CSV = "backend/results/exhibition_appeal_2026-04-where-things-linger-smoke-models.csv"

# 비교 baseline — A+B 통합 측정 (작업일지 기록)
BASELINE = {
    "openai/gpt-4o-mini": {"mean": 3.97, "std": 0.17},
    "openrouter/anthropic/claude-haiku-4.5": {"mean": 2.48, "std": 0.75},
    "openrouter/google/gemini-2.5-flash": {"mean": 2.80, "std": 0.43},
    "openrouter/qwen/qwen-2.5-72b-instruct": {"mean": 3.02, "std": 0.25},
}


def main():
    df = pd.read_csv(CSV)
    print(f"smoke 측정 행: {len(df)}")
    print(f"페르소나: {df['persona_uuid'].nunique()}")
    print(f"모델: {df['model'].nunique()}\n")

    df["model_short"] = df["model"].str.replace("openrouter/", "", regex=False)

    print("=== 후보 모델 핑거프린트 (smoke 5명 기준) ===")
    agg = (
        df.groupby("model_short")["appeal_score"]
        .agg(["mean", "std", "min", "max", "count"])
        .round(2)
        .sort_values("std", ascending=False)
    )
    print(agg)

    print("\n=== 기존 4 모델 baseline (A+B 통합 100명) ===")
    baseline_df = pd.DataFrame.from_dict(BASELINE, orient="index").round(2)
    baseline_df.index.name = "model"
    print(baseline_df)

    print("\n=== 페르소나별 응답 (모델 비교용) ===")
    pivot = df.pivot_table(
        index="persona_uuid",
        columns="model_short",
        values="appeal_score",
        aggfunc="first",
    ).round(2)
    # 세대 정보 추가
    age_lookup = df.groupby("persona_uuid")["age_bucket"].first()
    pivot.insert(0, "age_bucket", age_lookup)
    print(pivot)

    print("\n=== visit_intent 분포 ===")
    intent = df.groupby(["model_short", "visit_intent"]).size().unstack(fill_value=0)
    print(intent)

    print("\n=== 응답 시간 ===")
    print(df.groupby("model_short")["elapsed_sec"].agg(["mean", "max"]).round(2))

    print("\n=== 추천 (within-model std 기준) ===")
    rec = agg.copy()
    rec["judge"] = rec["std"].apply(
        lambda s: "[GO] 본측정 강추 (std>=0.7)"
        if s >= 0.7
        else "[GO] 본측정 후보 (std>=0.5)"
        if s >= 0.5
        else "[?] 보류 (std 0.3~0.5)"
        if s >= 0.3
        else "[NO] 비추 (페르소나 신호 약함)"
    )
    print(rec[["mean", "std", "judge"]])


if __name__ == "__main__":
    main()

"""
A+B 통합 분석 — Where Things Linger 측정 결과

CSV에서 smoke test 행을 제외하고 A(수도권 50)·B(전국 50)를 timestamp로 분리,
모델별 핑거프린트와 페르소나 효과(거주지·세대·소득)를 본다.
"""

import pandas as pd

CSV = "backend/results/exhibition_appeal_2026-04-where-things-linger.csv"

# A 측정은 22:55:30~ 시작, B 측정은 22:55:30 이후 새 timestamp.
# 가장 정확한 분리는 _sample_seed (A=42, B=43)인데 칼럼이 없으니
# persona_uuid 기준으로 분리. A·B는 다른 시드라 persona_uuid 자체가 다름.
def main():
    df = pd.read_csv(CSV)
    print(f"전체 행: {len(df)}")

    # smoke test 1건 제외 (22:51:18)
    df = df[df["timestamp"] >= "2026-04-28T22:55:00"].copy()
    print(f"smoke 제외: {len(df)}")

    # A·B 분리 — persona_uuid는 시드+인덱스로 결정론. seed42(A)와 seed43(B)는 100% 분리됨
    ts_max_a = "2026-04-28T23:16:30"  # A 마지막 타임스탬프 직후
    df_a = df[df["timestamp"] <= ts_max_a].copy()
    df_b = df[df["timestamp"] > ts_max_a].copy()
    df_a["측정"] = "A (수도권)"
    df_b["측정"] = "B (전국)"
    print(f"\nA: {len(df_a)} 행, {df_a['persona_uuid'].nunique()} 페르소나")
    print(f"B: {len(df_b)} 행, {df_b['persona_uuid'].nunique()} 페르소나")

    combined = pd.concat([df_a, df_b])
    combined["model_short"] = combined["model"].str.replace("openrouter/", "", regex=False)

    print("\n=== 모델 핑거프린트 (A+B 통합) ===")
    agg = combined.groupby("model_short")["appeal_score"].agg(
        ["mean", "std", "count"]
    ).round(2)
    print(agg)

    print("\n=== A vs B — 모델별 평균 비교 ===")
    cross = (
        combined.groupby(["측정", "model_short"])["appeal_score"]
        .mean()
        .unstack()
        .round(2)
    )
    print(cross)
    print()
    print("A vs B 차이 (B - A):")
    if len(cross) == 2:
        diff = cross.iloc[1] - cross.iloc[0]
        print(diff.round(2).to_string())

    print("\n=== 모델별 관람 의향 분포 (A+B) ===")
    intent = combined.groupby(["model_short", "visit_intent"]).size().unstack(fill_value=0)
    intent_pct = intent.div(intent.sum(axis=1), axis=0).mul(100).round(1)
    print(intent)
    print()
    print("(% 기준)")
    print(intent_pct)

    print("\n=== 거주지(province) × 모델 평균 — 거주지 효과 검증 ===")
    prov_model = (
        combined.groupby(["province", "model_short"])["appeal_score"]
        .mean()
        .unstack()
        .round(2)
    )
    prov_count = combined.groupby("province")["persona_uuid"].nunique()
    prov_model["_N페르소나"] = prov_count
    print(prov_model.sort_values("_N페르소나", ascending=False).head(15))

    print("\n=== 세대(age_bucket) × 모델 평균 ===")
    bins = [0, 19, 29, 39, 49, 59, 200]
    labels = ["~19", "20대", "30대", "40대", "50대", "60+"]
    combined["세대"] = pd.cut(combined["age"], bins=bins, labels=labels, right=True)
    age_model = (
        combined.groupby(["세대", "model_short"], observed=False)["appeal_score"]
        .mean()
        .unstack()
        .round(2)
    )
    print(age_model)

    print("\n=== 다양성 지표 (vuski Models aren't polls) ===")
    within_persona = combined.groupby("persona_uuid")["appeal_score"].std().mean()
    within_model = combined.groupby("model_short")["appeal_score"].std().mean()
    print(f"같은 페르소나 내 모델 간 평균 std: {within_persona:.2f}")
    print(f"같은 모델 내 페르소나 간 평균 std: {within_model:.2f}")
    print(f"비율 (모델 편향 / 페르소나 변동): {within_persona / within_model:.2f}배")

    print("\n=== A에 비해 B에서 새로 들어온 province (전국 다양성) ===")
    a_provs = set(df_a["province"].unique())
    b_provs = set(df_b["province"].unique())
    new_provs = b_provs - a_provs
    print(f"A에 있던: {sorted(a_provs)}")
    print(f"B에 있던: {sorted(b_provs)}")
    print(f"B에서 새로 등장: {sorted(new_provs)}")


if __name__ == "__main__":
    main()

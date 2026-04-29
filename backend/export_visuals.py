"""
시각화 자료 일괄 export — Where Things Linger A+B 측정 결과

PDF 보고서 1장 + 차트별 PNG + 분석 결과 markdown.
한글 폰트는 macOS 기본 Apple SD Gothic Neo.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

CSV = Path(__file__).parent / "results" / "exhibition_appeal_2026-04-where-things-linger.csv"
OUT_DIR = Path(__file__).parent / "exports" / "2026-04-where-things-linger"

plt.rcParams["font.family"] = "Apple SD Gothic Neo"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["axes.facecolor"] = "white"

MODEL_ORDER = [
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4.5",
    "google/gemini-2.5-flash",
    "qwen/qwen-2.5-72b-instruct",
]
MODEL_LABELS = {
    "openai/gpt-4o-mini": "gpt-4o-mini",
    "anthropic/claude-haiku-4.5": "claude-haiku-4.5",
    "google/gemini-2.5-flash": "gemini-2.5-flash",
    "qwen/qwen-2.5-72b-instruct": "qwen-2.5-72b",
}
MODEL_COLORS = {
    "openai/gpt-4o-mini": "#10A37F",
    "anthropic/claude-haiku-4.5": "#D4A373",
    "google/gemini-2.5-flash": "#4285F4",
    "qwen/qwen-2.5-72b-instruct": "#7B2CBF",
}


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df = df[df["timestamp"] >= "2026-04-28T22:55:00"].copy()  # smoke 제외
    df["model_short"] = df["model"].str.replace("openrouter/", "", regex=False)
    ts_max_a = "2026-04-28T23:16:30"
    df["측정"] = np.where(df["timestamp"] <= ts_max_a, "A (수도권)", "B (전국)")
    bins = [0, 19, 29, 39, 49, 59, 200]
    labels = ["~19", "20대", "30대", "40대", "50대", "60+"]
    df["세대"] = pd.cut(df["age"], bins=bins, labels=labels, right=True)
    return df


def fig_model_means(df: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    grouped = df.groupby("model_short")["appeal_score"].agg(["mean", "std", "count"])
    grouped = grouped.reindex(MODEL_ORDER)
    x = np.arange(len(grouped))
    colors = [MODEL_COLORS[m] for m in grouped.index]
    bars = ax.bar(
        x, grouped["mean"], yerr=grouped["std"], capsize=4,
        color=colors, edgecolor="white", linewidth=1.2,
    )
    for bar, mean_, n_ in zip(bars, grouped["mean"], grouped["count"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2, mean_ + 0.08,
            f"{mean_:.2f}\n(n={n_})", ha="center", va="bottom", fontsize=9,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_LABELS[m] for m in grouped.index], fontsize=10)
    ax.set_ylabel("평균 호감도 (1~5)")
    ax.set_ylim(0, 5)
    ax.axhline(3, color="gray", linestyle=":", linewidth=0.8, alpha=0.7)
    ax.set_title("모델별 평균 호감도 (A+B 통합 396건)", fontsize=12, pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_intent_stacked(df: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    intent_order = ["yes", "maybe", "no"]
    intent_colors = {"yes": "#2E7D32", "maybe": "#F9A825", "no": "#C62828"}
    counts = (
        df.groupby(["model_short", "visit_intent"]).size().unstack(fill_value=0)
    )
    counts = counts.reindex(MODEL_ORDER)
    pct = counts.div(counts.sum(axis=1), axis=0).mul(100)
    bottom = np.zeros(len(MODEL_ORDER))
    for intent in intent_order:
        if intent not in pct.columns:
            continue
        vals = pct[intent].values
        ax.bar(
            np.arange(len(MODEL_ORDER)), vals, bottom=bottom,
            color=intent_colors[intent], label=intent, edgecolor="white", linewidth=1,
        )
        for i, v in enumerate(vals):
            if v >= 5:
                ax.text(
                    i, bottom[i] + v / 2, f"{v:.0f}%",
                    ha="center", va="center", color="white", fontsize=9, weight="bold",
                )
        bottom = bottom + vals
    ax.set_xticks(np.arange(len(MODEL_ORDER)))
    ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER])
    ax.set_ylabel("관람 의향 비율 (%)")
    ax.set_ylim(0, 100)
    ax.set_title("모델별 관람 의향 분포 (yes / maybe / no)", fontsize=12, pad=12)
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_persona_model_heatmap(df: pd.DataFrame) -> plt.Figure:
    pivot = df.pivot_table(
        index="persona_uuid", columns="model_short", values="appeal_score"
    )
    pivot = pivot[MODEL_ORDER]
    pivot = pivot.assign(_var=pivot.std(axis=1)).sort_values("_var", ascending=False).drop(columns="_var")
    top30 = pivot.head(30)
    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(top30.values, aspect="auto", cmap="RdYlGn", vmin=1, vmax=5)
    ax.set_xticks(np.arange(len(MODEL_ORDER)))
    ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER], rotation=20, ha="right")
    ax.set_yticks(np.arange(len(top30)))
    ax.set_yticklabels([uid[:8] for uid in top30.index], fontsize=7)
    for i in range(len(top30)):
        for j in range(len(MODEL_ORDER)):
            v = top30.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", color="black", fontsize=7)
    ax.set_title("페르소나 × 모델 호감도 (모델 간 분산 큰 30명 발췌)", fontsize=12, pad=12)
    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("호감도 (1~5)")
    fig.tight_layout()
    return fig


def fig_diversity(df: pd.DataFrame) -> plt.Figure:
    within_persona_per = df.groupby("persona_uuid")["appeal_score"].std().dropna()
    within_model_per = df.groupby("model_short")["appeal_score"].std()
    wp_mean = within_persona_per.mean()
    wm_mean = within_model_per.mean()
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2))

    ax = axs[0]
    bars = ax.bar(
        ["페르소나 내\n모델 간 std", "모델 내\n페르소나 간 std"],
        [wp_mean, wm_mean],
        color=["#7B2CBF", "#10A37F"], edgecolor="white", linewidth=1.5,
    )
    for bar, val in zip(bars, [wp_mean, wm_mean]):
        ax.text(
            bar.get_x() + bar.get_width() / 2, val + 0.02,
            f"{val:.2f}", ha="center", va="bottom", fontsize=11, weight="bold",
        )
    ax.set_ylim(0, max(wp_mean, wm_mean) * 1.3)
    ax.set_ylabel("평균 표준편차")
    ax.set_title(f"다양성 지표 — 모델 편향 / 페르소나 변동 = {wp_mean / wm_mean:.2f}배", fontsize=11, pad=10)
    ax.spines[["top", "right"]].set_visible(False)

    ax = axs[1]
    x_labels = [MODEL_LABELS[m] for m in within_model_per.reindex(MODEL_ORDER).index]
    vals = within_model_per.reindex(MODEL_ORDER).values
    colors = [MODEL_COLORS[m] for m in MODEL_ORDER]
    bars = ax.bar(x_labels, vals, color=colors, edgecolor="white", linewidth=1.2)
    for bar, val in zip(bars, vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2, val + 0.02,
            f"{val:.2f}", ha="center", va="bottom", fontsize=10,
        )
    ax.set_ylabel("페르소나 간 std")
    ax.set_title("모델별 페르소나 반영도 (높을수록 demographic 신호 통과)", fontsize=11, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    plt.setp(ax.get_xticklabels(), rotation=15, ha="right")

    fig.suptitle("vuski \"Models aren't polls\" 실증 — N=100", fontsize=13, y=1.02)
    fig.tight_layout()
    return fig


def fig_province_heatmap(df: pd.DataFrame) -> plt.Figure:
    prov_count = df.groupby("province")["persona_uuid"].nunique()
    keep = prov_count[prov_count >= 2].index
    sub = df[df["province"].isin(keep)]
    pivot = sub.pivot_table(index="province", columns="model_short", values="appeal_score", aggfunc="mean")
    pivot = pivot[MODEL_ORDER]
    pivot["_n"] = prov_count[pivot.index]
    pivot = pivot.sort_values("_n", ascending=False)
    n_per_prov = pivot["_n"].astype(int).values
    pivot = pivot.drop(columns="_n")

    fig, ax = plt.subplots(figsize=(8, max(4, 0.42 * len(pivot) + 1)))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=1.5, vmax=4.5)
    ax.set_xticks(np.arange(len(MODEL_ORDER)))
    ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER], rotation=20, ha="right")
    ax.set_yticks(np.arange(len(pivot)))
    ax.set_yticklabels([f"{p} (n={n})" for p, n in zip(pivot.index, n_per_prov)])
    for i in range(len(pivot)):
        for j in range(len(MODEL_ORDER)):
            v = pivot.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", color="black", fontsize=8)
    ax.set_title("거주지(province) × 모델 평균 호감도 (n≥2 페르소나)", fontsize=12, pad=12)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    return fig


def fig_age_heatmap(df: pd.DataFrame) -> plt.Figure:
    pivot = df.pivot_table(
        index="세대", columns="model_short", values="appeal_score", aggfunc="mean", observed=False,
    )
    pivot = pivot[MODEL_ORDER]
    pivot = pivot.dropna(how="all")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=1.5, vmax=4.5)
    ax.set_xticks(np.arange(len(MODEL_ORDER)))
    ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER], rotation=20, ha="right")
    ax.set_yticks(np.arange(len(pivot)))
    ax.set_yticklabels(pivot.index)
    for i in range(len(pivot)):
        for j in range(len(MODEL_ORDER)):
            v = pivot.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", color="black", fontsize=10)
    ax.set_title("세대(age_bucket) × 모델 평균 호감도", fontsize=12, pad=12)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    return fig


def fig_ab_diff(df: pd.DataFrame) -> plt.Figure:
    cross = df.pivot_table(index="측정", columns="model_short", values="appeal_score", aggfunc="mean")
    cross = cross[MODEL_ORDER]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(MODEL_ORDER))
    width = 0.35
    a_vals = cross.loc["A (수도권)"].values
    b_vals = cross.loc["B (전국)"].values
    ax.bar(x - width / 2, a_vals, width, label="A (수도권 50)", color="#1f77b4", edgecolor="white")
    ax.bar(x + width / 2, b_vals, width, label="B (전국 50)", color="#ff7f0e", edgecolor="white")
    for i, (a, b) in enumerate(zip(a_vals, b_vals)):
        ax.text(i - width / 2, a + 0.05, f"{a:.2f}", ha="center", fontsize=9)
        ax.text(i + width / 2, b + 0.05, f"{b:.2f}", ha="center", fontsize=9)
        diff = b - a
        ax.text(
            i, max(a, b) + 0.35, f"Δ {diff:+.2f}",
            ha="center", fontsize=9, color="gray",
        )
    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER])
    ax.set_ylim(0, 5)
    ax.set_ylabel("평균 호감도")
    ax.set_title("A (수도권) vs B (전국) — 거주지 효과", fontsize=12, pad=12)
    ax.legend(frameon=False, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def write_summary_md(df: pd.DataFrame, path: Path) -> None:
    grouped = df.groupby("model_short")["appeal_score"].agg(["mean", "std", "count"])
    grouped = grouped.reindex(MODEL_ORDER)

    intent = df.groupby(["model_short", "visit_intent"]).size().unstack(fill_value=0)
    intent_pct = intent.div(intent.sum(axis=1), axis=0).mul(100)
    intent_pct = intent_pct.reindex(MODEL_ORDER)

    cross = df.pivot_table(index="측정", columns="model_short", values="appeal_score", aggfunc="mean").reindex(columns=MODEL_ORDER)
    diff = (cross.loc["B (전국)"] - cross.loc["A (수도권)"]).round(2)

    wp = df.groupby("persona_uuid")["appeal_score"].std().mean()
    wm = df.groupby("model_short")["appeal_score"].std().mean()

    lines = []
    lines.append("# Where Things Linger — A+B 측정 결과 요약")
    lines.append("")
    lines.append(f"- 측정일: 2026-04-28 (밤) ~ 2026-04-29 (새벽)")
    lines.append(f"- 분석 대상: {len(df)}건 (smoke 1건 제외, A 수도권 50명 + B 전국 50명, 모델 4개)")
    lines.append("- 시나리오: 한양대학교박물관 \"Where Things Linger\" 특별전 (2026.05.06~07.18, 무료 관람)")
    lines.append("")
    lines.append("## 모델별 핑거프린트")
    lines.append("")
    lines.append("| 모델 | 평균 | std | n | yes% | no% |")
    lines.append("|------|------|-----|---|------|-----|")
    for m in MODEL_ORDER:
        g = grouped.loc[m]
        ip = intent_pct.loc[m] if m in intent_pct.index else None
        yes_ = ip.get("yes", 0) if ip is not None else 0
        no_ = ip.get("no", 0) if ip is not None else 0
        lines.append(
            f"| {MODEL_LABELS[m]} | {g['mean']:.2f} | {g['std']:.2f} | {int(g['count'])} | {yes_:.0f}% | {no_:.0f}% |"
        )
    lines.append("")
    lines.append("## A vs B 평균 차이 (B - A)")
    lines.append("")
    lines.append("| 모델 | 차이 |")
    lines.append("|------|------|")
    for m in MODEL_ORDER:
        lines.append(f"| {MODEL_LABELS[m]} | {diff[m]:+.2f} |")
    lines.append("")
    lines.append(f"→ 거주지 효과 작음. 비수도권 50명 추가가 평균을 거의 안 움직임 (|Δ| ≤ 0.12).")
    lines.append("")
    lines.append("## 다양성 지표")
    lines.append("")
    lines.append(f"- 같은 페르소나 내 모델 간 std (모델 편향): **{wp:.2f}**")
    lines.append(f"- 같은 모델 내 페르소나 간 std (페르소나 변동): **{wm:.2f}**")
    lines.append(f"- 비율: **{wp / wm:.2f}배** — 모델 편향이 페르소나 변동의 약 {wp / wm:.1f}배")
    lines.append("")
    lines.append("## 핵심 결론")
    lines.append("")
    lines.append("1. 모델 편향이 페르소나 변동의 1.88배 — vuski \"Models aren't polls\" 비판 재현")
    lines.append("2. 모델별 페르소나 반영도가 극단적: claude-haiku std 0.75 ↔ gpt-4o-mini std 0.17")
    lines.append("3. 거주지(수도권 vs 전국) 효과는 작음. 본 시나리오 주제(도자/철학)는 지역 격차가 작음")
    lines.append("4. \"60대가 도자 향수로 호감 높을 것\" 가설 반박 — 60+ 2.12 ↔ 20대 2.67 (claude-haiku)")
    lines.append("5. 다중 모델 비교가 본 프로젝트의 차별점 — 단일 모델은 systematic bias가 결과 지배")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load()
    print(f"분석 대상: {len(df)}건, 페르소나 {df['persona_uuid'].nunique()}명, 모델 {df['model_short'].nunique()}개")

    figs = {
        "01_model_means.png": fig_model_means(df),
        "02_intent_stacked.png": fig_intent_stacked(df),
        "03_persona_model_heatmap.png": fig_persona_model_heatmap(df),
        "04_diversity.png": fig_diversity(df),
        "05_province_heatmap.png": fig_province_heatmap(df),
        "06_age_heatmap.png": fig_age_heatmap(df),
        "07_ab_diff.png": fig_ab_diff(df),
    }
    for name, fig in figs.items():
        fig.savefig(OUT_DIR / name, dpi=150, bbox_inches="tight")
        print(f"  PNG → {name}")

    pdf_path = OUT_DIR / "report_where_things_linger_AB.pdf"
    with PdfPages(pdf_path) as pdf:
        for name, fig in figs.items():
            pdf.savefig(fig, bbox_inches="tight")
        d = pdf.infodict()
        d["Title"] = "Where Things Linger — A+B 측정 보고서"
        d["Author"] = "knowing-koreans"
        d["Subject"] = "전시 콘셉트 호감도 (한양대학교박물관, 2026.05.06~07.18)"
    print(f"  PDF → {pdf_path.name}")

    md_path = OUT_DIR / "summary.md"
    write_summary_md(df, md_path)
    print(f"  MD  → {md_path.name}")

    for fig in figs.values():
        plt.close(fig)
    print(f"\n모든 산출물: {OUT_DIR}")


if __name__ == "__main__":
    main()

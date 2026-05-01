"""
knowing-koreans · 한국인 페르소나 시뮬레이터 — exhibition_appeal 시각화 prototype (stlite)

페르소나 5명 × 5모델 = 25건 응답 데이터를 기반으로 모델별 편향과
페르소나 차원 cross-tab을 보여준다. 박물관·문화 분야 한국 페르소나
시뮬레이터의 첫 단면.
"""

import pandas as pd
import altair as alt
import streamlit as st

st.set_page_config(
    page_title="knowing-koreans · 한국인 페르소나 시뮬레이터 — 전시 호감도",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- 데이터 ----------
df = pd.read_csv("data.csv")
df["model_short"] = df["model"].str.replace("openrouter/", "", regex=False)
df["persona_label"] = df.apply(
    lambda r: f"{r['sex']} {int(r['age'])}세 · {r['province']} · {str(r['occupation'])[:14]}",
    axis=1,
)
df["age_bucket"] = pd.cut(
    df["age"],
    bins=[0, 19, 29, 39, 49, 59, 200],
    labels=["~19", "20대", "30대", "40대", "50대", "60+"],
)

# ---------- 헤더 ----------
st.title("knowing-koreans · 한국인 페르소나 시뮬레이터 — 전시 콘셉트 호감도")
st.caption(
    "한국 인구통계 합성 페르소나(NVIDIA Nemotron-Personas-Korea, 1M)에 "
    "박물관·문화 시나리오를 던져 다중 LLM 응답을 비교하는 perspective-taking 도구."
)
st.caption(
    f"시나리오: **exhibition_appeal** · 시점: **2026-04** · "
    f"페르소나 **{df['persona_uuid'].nunique()}명** × 모델 **{df['model_short'].nunique()}개** "
    f"= 응답 **{len(df)}건** (prototype)"
)

# ---------- 전시 기획안 ----------
with st.expander("📋 전시 기획안", expanded=False):
    st.markdown(
        """
**제목** — 사물의 시간
**부제** — 한 일상 사물이 거쳐가는 네 자리
**기간** — 2026.05 ~ 2026.07
**장소** — 수도권 소재 박물관 (가상)
**관람료** — 무료 관람

한 일상 사물이 만들어지고, 사용되고, 놓이고, 결국 박물관 소장품이 되는 과정을
네 단계로 따라가는 narrative 전시입니다. 관람객은 자신이 일상에서 마주치는
사물이 시간을 거쳐 어떤 자리에 놓이는지를 다시 보게 됩니다.

**주요 볼거리**
- 일상 사물 한 가지의 시간을 네 단계로 구성한 narrative 전시
- 사물의 자리 변화를 따라가는 구성
- 작가 아티스트 토크 1회
- 오프닝 행사 1회
- 박물관 관람료 무료화 정책 시뮬용 가상 전시 변수
"""
    )

# ---------- KPI ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("응답 수", f"{len(df)}건")
c2.metric("평균 호감도", f"{df['appeal_score'].mean():.2f} / 5")
yes_n = int((df["visit_intent"] == "yes").sum())
c3.metric("관람 의향 yes", f"{yes_n} / {len(df)} ({yes_n / len(df) * 100:.0f}%)")
c4.metric("응답 평균 시간", f"{df['elapsed_sec'].mean():.1f}초")

st.divider()

# ---------- 모델별 호감도 (핵심: 모델 편향 노출) ----------
st.subheader("① 모델별 호감도 — *모델 편향 노출* 시각화")
st.caption(
    "다중 LLM 시뮬에서 흔히 나타나는 패턴: 같은 페르소나·같은 질문에도 모델마다 "
    "일관된 점수를 부여하면, 그것은 페르소나의 의견이 아니라 모델의 편향이다. "
    "이 25건에서 그 패턴이 그대로 드러난다."
)

model_agg = (
    df.groupby("model_short")["appeal_score"]
    .agg(mean="mean", std="std", n="count")
    .reset_index()
    .sort_values("mean", ascending=False)
)
model_agg["std"] = model_agg["std"].fillna(0)

bar = (
    alt.Chart(model_agg)
    .mark_bar()
    .encode(
        x=alt.X("model_short:N", title="모델", sort="-y"),
        y=alt.Y(
            "mean:Q",
            title="평균 호감도 (1~5)",
            scale=alt.Scale(domain=[0, 5]),
        ),
        color=alt.Color(
            "mean:Q",
            scale=alt.Scale(scheme="redyellowgreen", domain=[1, 5]),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("model_short", title="모델"),
            alt.Tooltip("mean", title="평균", format=".2f"),
            alt.Tooltip("std", title="표준편차", format=".2f"),
            alt.Tooltip("n", title="응답 수"),
        ],
    )
    .properties(height=300)
)
st.altair_chart(bar, use_container_width=True)

# ---------- 페르소나 × 모델 매트릭스 ----------
st.subheader("② 페르소나 × 모델 점수 매트릭스")
st.caption("페르소나마다 모델별로 일관된 패턴이 보이는지 — 가로축 색이 모델 편향을, 세로축 변화가 페르소나 영향을 보여준다.")

pivot = df.pivot_table(
    index="persona_label",
    columns="model_short",
    values="appeal_score",
    aggfunc="mean",
)
try:
    st.dataframe(
        pivot.style.background_gradient(cmap="RdYlGn", vmin=1, vmax=5).format(
            "{:.0f}"
        ),
        use_container_width=True,
    )
except Exception:
    st.dataframe(pivot.round(0), use_container_width=True)

# ---------- 모델별 관람 의향 ----------
st.subheader("③ 모델별 관람 의향 분포")
intent_df = (
    df.groupby(["model_short", "visit_intent"])
    .size()
    .reset_index(name="count")
)
intent_chart = (
    alt.Chart(intent_df)
    .mark_bar()
    .encode(
        x=alt.X("model_short:N", title="모델"),
        y=alt.Y("count:Q", title="비율", stack="normalize"),
        color=alt.Color(
            "visit_intent:N",
            scale=alt.Scale(
                domain=["yes", "maybe", "no"],
                range=["#2E7D32", "#F9A825", "#C62828"],
            ),
            title="관람 의향",
        ),
        tooltip=["model_short", "visit_intent", "count"],
    )
    .properties(height=260)
)
st.altair_chart(intent_chart, use_container_width=True)

# ---------- 다양성 지표 ----------
st.subheader("④ 다양성 지표 (균질화 비판 대응)")
g1, g2 = st.columns(2)
within_persona_std = df.groupby("persona_uuid")["appeal_score"].std().mean()
within_model_std = df.groupby("model_short")["appeal_score"].std().mean()
g1.metric(
    "같은 페르소나 내 모델 간 표준편차 (평균)",
    f"{within_persona_std:.2f}",
    help="높을수록 모델 의견이 갈림 — 모델 편향이 강하다는 신호",
)
g2.metric(
    "같은 모델 내 페르소나 간 표준편차 (평균)",
    f"{within_model_std:.2f}",
    help="0에 가까우면 모델이 페르소나를 무시한다는 신호 — stereotyping 경고",
)

st.divider()

# ---------- 응답 카드 ----------
st.subheader("⑤ 개별 응답 카드")
sel_col1, sel_col2 = st.columns([1, 1])
selected_model = sel_col1.selectbox(
    "모델 선택", sorted(df["model_short"].unique()), index=0
)
sort_by = sel_col2.selectbox(
    "정렬", ["페르소나 라벨", "호감도 ↓", "호감도 ↑"], index=0
)

filtered = df[df["model_short"] == selected_model].copy()
if sort_by == "호감도 ↓":
    filtered = filtered.sort_values("appeal_score", ascending=False)
elif sort_by == "호감도 ↑":
    filtered = filtered.sort_values("appeal_score", ascending=True)
else:
    filtered = filtered.sort_values("persona_label")

for _, row in filtered.iterrows():
    intent_emoji = {"yes": "🟢", "maybe": "🟡", "no": "🔴"}.get(
        row["visit_intent"], "⚪"
    )
    with st.expander(
        f"{intent_emoji} {row['persona_label']} — {row['appeal_score']}/5",
        expanded=False,
    ):
        left, right = st.columns([1, 2])
        with left:
            st.markdown(f"**관람 의향**: {row['visit_intent']}")
            st.markdown(f"**호감도**: {row['appeal_score']} / 5")
            st.markdown(f"**가장 끌리는 요소**:  \n{row['key_attraction']}")
            st.markdown(f"**걱정·망설임**:  \n{row['key_concern']}")
        with right:
            st.markdown(f"**사유**:  \n{row['reason']}")
            st.markdown("---")
            st.caption(f"📌 **페르소나 요약**: {row.get('persona', '-')}")
            st.caption(f"🎨 **예술 면모**: {row.get('arts_persona', '-')}")
            st.caption(
                f"🌏 **문화 배경**: {row.get('cultural_background', '-')}"
            )
            st.caption(
                f"💼 **직업 면모**: {row.get('professional_persona', '-')}"
            )

st.divider()

# ---------- raw 데이터 ----------
with st.expander("🗄 raw CSV 보기", expanded=False):
    st.dataframe(df, use_container_width=True)

st.caption(
    "⚙ knowing-koreans · 데이터: NVIDIA Nemotron-Personas-Korea (CC BY 4.0) · "
    "다중 LLM via OpenRouter · stlite 정적 호스팅"
)

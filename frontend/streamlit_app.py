"""
knowing-koreans · 한국인 페르소나 시뮬레이터 — exhibition_appeal 시각화 prototype (stlite)

페르소나 5명 × 5모델 = 25건 응답 데이터를 기반으로 모델별 편향과
페르소나 차원 cross-tab을 보여준다. 박물관·문화 분야 한국 페르소나
시뮬레이터의 첫 단면.
"""

import json
from pathlib import Path

import pandas as pd
import altair as alt
import streamlit as st

st.set_page_config(
    page_title="knowing-koreans · 한국인 페르소나 시뮬레이터",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- 본 라운드 (N=1,000 박물관 관람료 시나리오) 데이터 ----------
N1000_DIR = Path("data/run_N1000")


def _safe_load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _safe_load_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except Exception:
        return b""


INSIGHT = _safe_load_json(N1000_DIR / "insight.json")
SPEC = _safe_load_json(N1000_DIR / "spec.json")
STATUS = _safe_load_json(N1000_DIR / "status.json")
REPORT_MD = _safe_load_text(N1000_DIR / "report.md")
HAS_N1000 = INSIGHT is not None and SPEC is not None and STATUS is not None

# ---------- prototype (페르소나 25건) 데이터 ----------
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
st.title("knowing-koreans · 한국인 페르소나 시뮬레이터")
st.caption("합성 페르소나로 큐레이터 가설을 점검하는 도구.")
st.markdown(
    "한국 인구통계 분포 합성 페르소나(NVIDIA Nemotron-Personas-Korea, 약 700만)에 "
    "박물관·문화 시나리오를 던져 여러 LLM이 어떻게 응답하는지 비교합니다."
)
if HAS_N1000:
    n_total = STATUS.get("n_total", 1000)
    n_ok = STATUS.get("n_ok", 998)
    st.markdown(
        f"이 페이지는 두 단면을 함께 보여줍니다. "
        f"**① prototype** (페르소나 25건, 전시 콘셉트 호감도 시나리오)으로 도구 동작을 보여주고, "
        f"**② 본 라운드 N={n_total:,}건** (박물관 관람료 무료화 시나리오, 응답 성공 {n_ok}건)의 "
        f"4섹션 보고서 — 발견 패턴·큐레이터 가설·곱씹을 만한 응답·다음에 던져볼 질문 — 를 함께 노출합니다."
    )
else:
    st.markdown(
        "이 페이지는 **첫 시나리오 prototype**의 응답을 시각화합니다."
    )
st.caption(
    f"prototype 단면 — **전시 콘셉트 호감도** (시점 **2026-04**) · "
    f"페르소나 **{df['persona_uuid'].nunique()}명** × 모델 **{df['model_short'].nunique()}개** "
    f"= 응답 **{len(df)}건**"
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
네 단계 흐름으로 따라가는 이야기 구성 전시입니다. 관람객은 자신이 일상에서 마주치는
사물이 시간을 거쳐 어떤 자리에 놓이는지를 다시 보게 됩니다.

**주요 볼거리**
- 일상 사물 한 가지의 시간을 네 단계로 풀어낸 이야기 구성 전시
- 사물의 자리 변화를 따라가는 구성
- 작가 토크 1회
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
st.subheader("① 모델별 호감도 — 모델 편향이 보이는가")
st.caption(
    "여러 LLM에 같은 페르소나와 같은 질문을 던졌을 때, 모델마다 점수가 일관되게 갈리면 "
    "그건 페르소나의 의견이 아니라 모델 자체의 성향입니다. 이 25건에서도 그 패턴이 드러납니다."
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
st.subheader("② 페르소나 × 모델 점수 표")
st.caption(
    "같은 페르소나에 모델별 점수가 일관된가, 같은 모델에 페르소나별 점수가 갈리는가를 한눈에 봅니다. "
    "가로축(모델 간) 색 차이가 모델 편향, 세로축(페르소나 간) 변화가 페르소나 신호입니다."
)

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
st.subheader("④ 응답 변동 지표 — 모델·페르소나 신호 분리")
g1, g2 = st.columns(2)
within_persona_std = df.groupby("persona_uuid")["appeal_score"].std().mean()
within_model_std = df.groupby("model_short")["appeal_score"].std().mean()
g1.metric(
    "같은 페르소나 내 모델 간 표준편차 (평균)",
    f"{within_persona_std:.2f}",
    help="높을수록 같은 페르소나에 모델별 점수 차이가 크다는 뜻입니다 — 모델 편향이 강한 신호.",
)
g2.metric(
    "같은 모델 내 페르소나 간 표준편차 (평균)",
    f"{within_model_std:.2f}",
    help="0에 가까우면 같은 모델이 모든 페르소나에 비슷한 점수를 매긴다는 뜻입니다 — 모델이 페르소나 차이를 평균치로 깎아내리고 있다는 신호.",
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

# ---------- raw 데이터 (prototype) ----------
with st.expander("🗄 prototype raw CSV 보기", expanded=False):
    st.dataframe(df, use_container_width=True)

# =========================================================================
# 본 라운드 — N=1,000 박물관 관람료 무료화 시나리오 (4섹션 보고서)
# =========================================================================
if HAS_N1000:
    st.divider()
    n_total = STATUS.get("n_total", 1000)
    n_ok = STATUS.get("n_ok", 998)
    n_fail = STATUS.get("n_fail", 0)
    avg_sec = STATUS.get("avg_sec_per_call", 0)
    insight_mode = STATUS.get("insight_mode", "B")
    insight_n_clusters = STATUS.get("insight_n_clusters", 0)
    insight_input_tokens = STATUS.get("insight_input_tokens", 0)
    started_at = STATUS.get("started_at", "")
    finished_at = STATUS.get("finished_at", "")
    models_list = SPEC.get("models", [])
    model_short_list = [
        m.replace("openrouter/", "").replace("nousresearch/", "")
        for m in models_list
    ]
    seed = SPEC.get("seed", "-")

    st.header("⑥ 본 라운드 — N=1,000 박물관 관람료 무료화 시나리오")
    st.caption(
        "한국 인구통계 분포에서 합성한 페르소나 1,000명에 박물관 관람료 무료화 "
        "찬반 논쟁 시나리오를 던지고, 응답을 4섹션 보고서로 정리한 단면입니다."
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("응답 수", f"{n_ok} / {n_total}")
    k2.metric("실패", f"{n_fail}건")
    k3.metric("평균 응답 시간", f"{avg_sec:.1f}초")
    k4.metric(
        "보고서 생성 모드",
        f"모드 {insight_mode}",
        help=(
            f"입력 {insight_input_tokens / 1_000_000:.2f}M 토큰을 "
            f"{insight_n_clusters}개 cluster로 분할 후 "
            "cluster 분석 → cross-cluster diff → synthesis 5단계 합성. "
            "모드 B는 1M context 한도를 넘는 대규모 N에 자동 적용됩니다."
        ),
    )

    meta_cols = st.columns(2)
    meta_cols[0].markdown(
        f"**측정 시작** {started_at[:19].replace('T', ' ')}  \n"
        f"**측정 완료** {finished_at[:19].replace('T', ' ')}"
    )
    meta_cols[1].markdown(
        f"**측정 모델** {', '.join(model_short_list) if model_short_list else '-'}  \n"
        f"**페르소나 시드** {seed}"
    )

    with st.expander("📋 시나리오 기획안 — 주제·맥락·질문지·응답 schema", expanded=False):
        st.markdown("**주제 (찬성·반대 논거 포함)**")
        st.markdown(SPEC.get("topic", "-"))
        st.markdown("---")
        st.markdown("**페르소나 주입 맥락**")
        st.markdown(SPEC.get("ctx", "-"))
        st.markdown("---")
        st.markdown("**질문지**")
        st.markdown(SPEC.get("questions", "-"))
        st.markdown("---")
        st.markdown("**응답 schema (JSON)**")
        st.code(SPEC.get("schema_block", "-"), language="json")

    # ---------- ⑦ 발견 패턴 ----------
    st.subheader("⑦ 발견 패턴 — key findings")
    st.caption(
        f"보고서 생성 LLM이 {n_ok}건 raw 응답 + 페르소나 narrative 전수를 "
        f"{insight_n_clusters}개 cluster로 분석한 뒤 종합한 패턴입니다."
    )
    findings = INSIGHT.get("key_findings", [])
    for finding in findings:
        with st.container():
            st.markdown(f"**{finding.get('label', '')}**")
            st.markdown(finding.get("content", ""))
            st.markdown("")

    # ---------- ⑧ 큐레이터 관점·가설 ----------
    st.subheader("⑧ 큐레이터 관점·가설 — curator hypotheses")
    st.caption(
        "발견 패턴을 큐레이터 도메인 어조로 옮긴 가설 후보입니다. "
        "타깃 그룹·전달 형식·메시지 본문 세 차원으로 정리됩니다."
    )
    hypotheses = INSIGHT.get("curator_hypotheses", [])
    for i, h in enumerate(hypotheses, start=1):
        with st.container():
            st.markdown(
                f"**가설 {i:02d}** · 타깃: `{h.get('target_group', '-')}` · "
                f"전달 형식: `{h.get('form', '-')}`"
            )
            st.markdown(h.get("content", ""))
            st.markdown("")

    # ---------- ⑨ 응답자 속성 축별 분포 ----------
    st.subheader("⑨ 응답자 속성 축별 분포 — 차트")
    st.caption(
        "페르소나 분포(연령·지역)와 응답 분포(전체·모델별·축별)를 "
        "5장의 차트로 보여줍니다."
    )
    chart_files = [
        ("페르소나 연령 분포", "chart_age.png"),
        ("페르소나 지역 분포 (지도)", "chart_map.png"),
        ("응답 분포 (전체)", "chart_response_dist.png"),
        ("응답 분포 — 인구통계 축별", "chart_response_by_axis.png"),
        ("응답 분포 — 모델별", "chart_response_by_model.png"),
    ]
    for caption, fname in chart_files:
        chart_path = N1000_DIR / fname
        if chart_path.exists():
            st.markdown(f"**{caption}**")
            st.image(str(chart_path), use_container_width=True)
            st.markdown("")

    # ---------- ⑩ 곱씹을 만한 응답 ----------
    st.subheader("⑩ 곱씹을 만한 응답 — 인용 + 큐레이터 노트")
    st.caption(
        "보고서 생성 LLM이 998건 응답 중 큐레이터에게 의미 있는 인용을 골라 "
        "큐레이션 활용 노트와 함께 정리한 카드입니다."
    )
    quotes = INSIGHT.get("responses_to_chew_on", [])
    for q in quotes:
        with st.container():
            st.markdown(
                f"**{q.get('persona_attrs', '-')}**  ·  모델: `{q.get('model', '-')}`"
            )
            st.markdown(f"> {q.get('quote', '')}")
            st.caption(f"📝 **큐레이터 노트** — {q.get('curator_note', '')}")
            st.markdown("")

    # ---------- ⑪ 다음에 던져볼 질문 ----------
    st.subheader("⑪ 다음에 던져볼 질문 — next questions")
    st.caption(
        "본 라운드에서 잡힌 약신호와 모델 편향 의심 패턴을 후속 시나리오 "
        "질문으로 옮긴 큐레이터용 work item입니다."
    )
    next_questions = INSIGHT.get("next_questions", [])
    for i, q in enumerate(next_questions, start=1):
        st.markdown(f"**Q{i:02d}** — {q}")
        st.markdown("")

    # ---------- ⑫ 보고서 다운로드 + 전문 ----------
    st.subheader("⑫ 보고서 전문 + 다운로드")
    st.caption(
        "위 ⑦~⑪ 4섹션은 보고서 본문에서 추출한 영역입니다. "
        "전체 12섹션 보고서는 PDF 또는 Markdown 전문에서 보실 수 있습니다."
    )

    pdf_bytes = _safe_load_bytes(N1000_DIR / "report.pdf")
    if pdf_bytes:
        st.download_button(
            label="📥 보고서 PDF 다운로드 (report.pdf)",
            data=pdf_bytes,
            file_name="knowing-koreans_N1000_museum-admission_report.pdf",
            mime="application/pdf",
        )

    if REPORT_MD:
        with st.expander("📄 보고서 전문 (Markdown)", expanded=False):
            st.markdown(REPORT_MD)

st.divider()

st.caption(
    "⚙ knowing-koreans · 데이터: NVIDIA Nemotron-Personas-Korea (CC BY 4.0) · "
    "OpenRouter 경유 다중 LLM · stlite 정적 호스팅"
)

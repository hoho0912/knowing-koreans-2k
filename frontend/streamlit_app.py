"""
knowing-koreans · 한국인 페르소나 시뮬레이터 — 본 라운드 N=1,000 보고서 (stlite)

박물관 관람료 무료화 시나리오에 합성 페르소나 1,000명을 던져 응답을 4섹션
보고서로 정리한 단면을 정적 페이지로 노출한다.
"""

import json
from pathlib import Path

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

# ---------- 헤더 ----------
st.title("knowing-koreans · 한국인 페르소나 시뮬레이터")
st.caption("합성 페르소나로 큐레이터 가설을 점검하는 도구.")
st.markdown(
    "한국 인구통계 분포 합성 페르소나(NVIDIA Nemotron-Personas-Korea, 약 700만)에 "
    "박물관·문화 시나리오를 던져 여러 LLM이 어떻게 응답하는지 비교합니다."
)

if not HAS_N1000:
    st.error("본 라운드 N=1,000 데이터(`data/run_N1000/`)를 찾을 수 없습니다.")
    st.stop()

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
    m.replace("openrouter/", "").replace("nousresearch/", "") for m in models_list
]
seed = SPEC.get("seed", "-")

st.markdown(
    f"이 페이지는 본 라운드 **N={n_total:,}건** (박물관 관람료 무료화 시나리오, "
    f"응답 성공 {n_ok}건)의 4섹션 보고서 — 발견 패턴·큐레이터 가설·곱씹을 만한 "
    f"응답·다음에 던져볼 질문 — 를 노출합니다."
)

st.divider()
st.header("본 라운드 — N=1,000 박물관 관람료 무료화 시나리오")

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

# ---------- ① 발견 패턴 ----------
st.subheader("① 발견 패턴 — key findings")
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

# ---------- ② 큐레이터 관점·가설 ----------
st.subheader("② 큐레이터 관점·가설 — curator hypotheses")
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

# ---------- ③ 응답자 속성 축별 분포 ----------
st.subheader("③ 응답자 속성 축별 분포 — 차트")
st.caption(
    "페르소나 분포(연령·지역)와 응답 분포(전체·모델별·축별)를 5장의 차트로 보여줍니다."
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

# ---------- ④ 곱씹을 만한 응답 ----------
st.subheader("④ 곱씹을 만한 응답 — 인용 + 큐레이터 노트")
st.caption(
    f"보고서 생성 LLM이 {n_ok}건 응답 중 큐레이터에게 의미 있는 인용을 골라 "
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

# ---------- ⑤ 다음에 던져볼 질문 ----------
st.subheader("⑤ 다음에 던져볼 질문 — next questions")
st.caption(
    "본 라운드에서 잡힌 약신호와 모델 편향 의심 패턴을 후속 시나리오 질문으로 "
    "옮긴 큐레이터용 work item입니다."
)
next_questions = INSIGHT.get("next_questions", [])
for i, q in enumerate(next_questions, start=1):
    st.markdown(f"**Q{i:02d}** — {q}")
    st.markdown("")

# ---------- ⑥ 보고서 전문 + 다운로드 ----------
st.subheader("⑥ 보고서 전문 + 다운로드")
st.caption(
    "위 발견 패턴·큐레이터 가설·곱씹을 만한 응답·다음 질문 4섹션은 보고서 "
    "본문에서 추출한 영역입니다. 전체 12섹션 보고서는 PDF 또는 Markdown "
    "전문에서 보실 수 있습니다."
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

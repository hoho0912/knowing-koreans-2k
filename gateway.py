"""knowing-koreans 협업 게이트웨이 v5 — 측정 워커 분리 (브라우저 의존성 제거).

v4 → v5 변경:
- 4·5단계가 streamlit 안에서 직접 LLM을 호출하지 않음.
  대신 systemd-run으로 backend.run_worker를 띄우고 status.json만 폴링.
  → 큐레이터가 브라우저를 닫아도 측정·보고서 생성이 끊기지 않음.
- 1단계 하단에 owner의 "진행 중·최근 측정" 카드.
- 4단계 [측정 취소] 버튼 — systemctl stop으로 워커에 SIGTERM.
- 5단계는 report.png 한 장 + [PDF 다운로드] + [원천소스 zip 다운로드].
- 측정 시작 직전 backend.run_validate.validate_spec()로 schema/engine drift 차단.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import bcrypt
import streamlit as st
from streamlit_cookies_controller import CookieController

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm_runner import call_llm  # noqa: E402
from backend.run_validate import validate_spec  # noqa: E402

RESULTS_DIR = PROJECT_ROOT / "results" / "gateway_runs"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 휴지통 — 카드 삭제 시 즉시 영구 삭제 대신 _trash/{run_id}/로 이동.
# 30일 지난 항목은 페이지 로드 시 자동 비움(아래 purge_old_trash).
TRASH_DIR = RESULTS_DIR / "_trash"
TRASH_RETENTION_DAYS = 30

# ─────────────────────────────────────────────────────────
# 모델 라인업 (워커와 동일하게 유지)
# ─────────────────────────────────────────────────────────

DEFAULT_SIM_MODELS = [
    "openrouter/qwen/qwen3-max",
    "openrouter/nousresearch/hermes-4-70b",
    "openrouter/anthropic/claude-haiku-4.5",
]

EXTRA_SIM_MODELS = [
    "openrouter/nousresearch/hermes-4-405b",
    "openrouter/qwen/qwen3.6-max-preview",
    "openrouter/qwen/qwen3.6-plus",
    "openrouter/mistralai/mistral-large-2512",
    "openrouter/anthropic/claude-sonnet-4.6",
    "openrouter/openai/gpt-4o-mini",
    "openrouter/google/gemini-2.5-flash",
    "openrouter/deepseek/deepseek-v4-flash",
    "openrouter/x-ai/grok-4-fast",
    "openrouter/cohere/command-a",
    "openrouter/cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
]

MODEL_LABELS = {
    "openrouter/qwen/qwen3-max":               "Qwen3 Max (Alibaba)",
    "openrouter/nousresearch/hermes-4-405b":   "Hermes 4 405B (NousResearch)",
    "openrouter/anthropic/claude-haiku-4.5":   "Claude Haiku 4.5 (Anthropic)",
    "openrouter/nousresearch/hermes-4-70b":    "Hermes 4 70B (NousResearch)",
    "openrouter/qwen/qwen3.6-max-preview":     "Qwen3.6 Max Preview (Alibaba)",
    "openrouter/qwen/qwen3.6-plus":            "Qwen3.6 Plus (Alibaba)",
    "openrouter/mistralai/mistral-large-2512": "Mistral Large (Mistral, 프랑스)",
    "openrouter/anthropic/claude-sonnet-4.6":  "Claude Sonnet 4.6 (Anthropic)",
    "openrouter/openai/gpt-4o-mini":           "GPT-4o mini (OpenAI)",
    "openrouter/google/gemini-2.5-flash":      "Gemini 2.5 Flash (Google)",
    "openrouter/deepseek/deepseek-v4-flash":   "DeepSeek v4 Flash (DeepSeek)",
    "openrouter/x-ai/grok-4-fast":             "Grok 4 Fast (xAI, 2M context)",
    "openrouter/x-ai/grok-4.20":               "Grok 4.20 (xAI, 2M context, reasoning)",
    "openrouter/qwen/qwen-plus-2025-07-28:thinking":
                                                "Qwen Plus thinking (Alibaba, 1M context)",
    "openrouter/cohere/command-a":             "Cohere Command A (Cohere)",
    "openrouter/anthropic/claude-opus-4.7":    "Claude Opus 4.7 (Anthropic, 1M context)",
    "openrouter/cognitivecomputations/dolphin-mistral-24b-venice-edition:free":
                                                "Dolphin Mistral 24B (Cognitive Computations, uncensored)",
}

GEN_LLM_MODELS = [
    "openrouter/anthropic/claude-sonnet-4.6",
    "openrouter/anthropic/claude-opus-4.7",
    "openrouter/anthropic/claude-haiku-4.5",
    "openrouter/qwen/qwen3.6-max-preview",
    "openrouter/openai/gpt-4o-mini",
]

# v6.2 — 분석 단계(수집된 응답 전수 → 통찰 보고서)에 쓸 후보.
# 분석 LLM은 페르소나 narrative + 응답 raw를 한 번에 시야로 봐야 해서
# context length 1M + 강한 추론을 동시에 만족해야 합니다. 측정용 모델
# (qwen3-max, hermes-4-405b 등)을 분석에 그대로 쓰면 ambivalence 해석·
# 한국어 자유서술 의미·페르소나 narrative ↔ 응답 정합성 분석이 약해집니다.
ANALYSIS_LLM_MODELS = [
    "openrouter/anthropic/claude-opus-4.7",
    "openrouter/anthropic/claude-sonnet-4.6",
    "openrouter/x-ai/grok-4.20",
    "openrouter/x-ai/grok-4-fast",
    "openrouter/qwen/qwen-plus-2025-07-28:thinking",
]

QGEN_MODEL_DEFAULT = "openrouter/anthropic/claude-sonnet-4.6"
REPORT_MODEL_DEFAULT = "openrouter/anthropic/claude-opus-4.7"

# 진행 중 phase 집합 (1단계 카드 / 동시성 정책 / 4단계 polling 분기)
ACTIVE_PHASES = {
    "starting",
    "loading_pool",
    "sampling",
    "calling_llm",
    "writing_report",
    # 인사이트 파이프라인 phase (run_worker.py v6.x)
    "estimating_tokens",
    "calling_insight_llm",
    "analyzing_clusters",
    "cross_cluster_diff",
    "raw_retrieval",
    "synthesizing",
}

# phase 한글 표기 — status.json의 phase 코드를 사용자 화면용 라벨로 매핑.
# 매핑 누락 시 phase 코드 그대로 노출 → 영문이 그대로 보이는 사고 방지.
PHASE_LABELS_KO = {
    "starting":             "시작 중",
    "loading_pool":         "페르소나 풀 불러오는 중",
    "sampling":             "페르소나 표본 추출 중",
    "calling_llm":          "응답 수집 중",
    "writing_report":       "보고서 정리 중",
    "estimating_tokens":    "토큰 추산 중",
    "calling_insight_llm":  "분석 LLM 호출 중",
    "analyzing_clusters":   "클러스터 분석 중",
    "cross_cluster_diff":   "클러스터 비교 중",
    "raw_retrieval":        "원본 발췌 중",
    "synthesizing":         "보고서 합성 중",
    "done":                 "완료",
    "cancelled":            "취소됨",
    "error":                "오류",
}


def phase_label_ko(phase: str) -> str:
    return PHASE_LABELS_KO.get(phase, phase or "—")


def model_label(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id)


# ─────────────────────────────────────────────────────────
# 1·2단계 — 질문 정리·다시 정리 LLM (v4와 동일)
# ─────────────────────────────────────────────────────────
QUESTION_GEN_SYSTEM = textwrap.dedent("""\
당신은 박물관·문화 분야의 시뮬레이션 설계 보조자입니다.
큐레이터가 제시한 측정 주제·전시 개요를 바탕으로, 합성 페르소나에게 던질
질문 1~5개를 정리하고, 각 질문에 대한 응답 JSON 스키마를 제안하세요.

출력은 반드시 다음 마크다운 형식이어야 합니다 (헤더·블록 위치 변경 금지):

## 컨텍스트
(LLM에 함께 주입할 짧은 배경, 1~3문단, 수치·여론조사 인용 없음, 중립 톤)

## 질문
1) 첫 번째 질문 — 자연어로 명확히
2) 두 번째 질문
...

## 응답 스키마 (JSON)
```json
{
  "field_1": "값 또는 척도 설명",
  "field_2": "..."
}
```

규칙:
- 질문은 페르소나 1명 분량 30초 이내로 답할 수 있게 짧게.
- 척도는 1~5 또는 1~7 likert를 우선 검토.
- 자유 응답은 한 응답당 1개 이내, 50~200자로 길이를 제한.
""")

QUESTION_GEN_USER_TEMPLATE = textwrap.dedent("""\
## 측정 주제·전시 개요 / 가설
{topic}

위 내용을 바탕으로, 명시한 형식대로 컨텍스트·질문·응답 스키마를 작성하세요.
""")

QUESTION_REPOLISH_USER_TEMPLATE = textwrap.dedent("""\
## 측정 주제·전시 개요 / 가설
{topic}

## 사용자가 자연어로 수정한 버전 (형식이 흐트러져 있을 수 있음)
{edited}

위 수정 의도를 그대로 반영하면서, 명시한 형식(## 컨텍스트 / ## 질문 /
## 응답 스키마 (JSON) + ```json 블록)을 정확히 맞춰 다시 작성해 주세요.
사용자가 의도적으로 손본 표현·뉘앙스는 가능한 한 보존하세요.
""")

# ─────────────────────────────────────────────────────────
# UI 상수
# ─────────────────────────────────────────────────────────
SEX_OPTIONS = ["(상관없음)", "남자", "여자"]
STEP_LABELS = [
    "1) 무엇을 알아보고 싶으세요?",
    "2) 질문 확인",
    "3) 누구에게 묻나요?",
    "4) 응답 수집 중",
    "5) 통찰 정리",
]


# ─────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "step": 1,
        "topic_text": "",
        "qgen_model": QGEN_MODEL_DEFAULT,
        "report_model": REPORT_MODEL_DEFAULT,
        "draft_md": "",
        "question_md": "",
        "ctx": "",
        "questions": "",
        "schema_block": "",
        "selected_models": list(DEFAULT_SIM_MODELS),
        "extra_picked": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def split_question_md(md: str):
    ctx_match = re.search(r"##\s*컨텍스트\s*\n(.*?)(?=\n##\s|\Z)", md, re.DOTALL)
    q_match = re.search(r"##\s*질문\s*\n(.*?)(?=\n##\s|\Z)", md, re.DOTALL)
    s_match = re.search(r"##\s*응답[\s\S]*?```json\s*\n(.*?)\n```", md, re.DOTALL)
    ctx = ctx_match.group(1).strip() if ctx_match else ""
    questions = q_match.group(1).strip() if q_match else ""
    schema = s_match.group(1).strip() if s_match else ""
    return ctx, questions, schema


CREDS_PATH = PROJECT_ROOT / ".creds-kk.json"

# ─────────────────────────────────────────────────────────
# 쿠키 기반 인증 영속화
# ─────────────────────────────────────────────────────────
# Streamlit `session_state`만으로는 (a) 게이트웨이 재시작 (b) 브라우저 닫기·새 탭
# 두 경우 모두 로그인 상태가 사라집니다. 그래서 HMAC 서명 쿠키 1개로 owner를
# 7일간 유지합니다. 쿠키는 큐레이터 ID + 만료 epoch + sha256 서명 3조각.
# 비밀키는 .env의 KK_COOKIE_SECRET (게이트웨이 재시작에도 유지). 비밀키가
# 회전되면 모든 큐레이터가 자동으로 로그아웃되어 강제 로그인 흐름으로 떨어짐.

COOKIE_NAME = "kk_auth"
COOKIE_TTL_SEC = 7 * 24 * 3600  # 7일

# CookieController 인스턴스는 Streamlit 컴포넌트라 반드시 한 번만 생성. 모듈
# 로드 시점에 만들면 ScriptRunContext가 없어 경고가 뜨므로 lazy 캐시.
def _cookies() -> CookieController:
    if "_kk_cookies" not in st.session_state:
        st.session_state["_kk_cookies"] = CookieController(key="kk_cookies")
    return st.session_state["_kk_cookies"]


def _cookie_secret() -> bytes:
    raw = os.getenv("KK_COOKIE_SECRET", "")
    if not raw:
        raise RuntimeError(
            "KK_COOKIE_SECRET 환경변수가 설정되어 있지 않습니다. "
            ".env.local에 다음 한 줄을 추가하세요:\n"
            '    KK_COOKIE_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")\n'
            "또는 직접 64자 hex 문자열을 생성해 셋업하세요."
        )
    return raw.encode("utf-8")


def _make_token(owner: str, ttl_sec: int = COOKIE_TTL_SEC) -> str:
    """owner|exp_unix|hmac_b64 형태의 쿠키 토큰 생성."""
    exp = int(time.time()) + ttl_sec
    payload = f"{owner}|{exp}".encode("utf-8")
    sig = hmac.new(_cookie_secret(), payload, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{owner}|{exp}|{sig_b64}"


def _verify_token(token: Optional[str]) -> Optional[str]:
    """쿠키 토큰이 서명·만료 모두 OK면 owner 반환, 아니면 None."""
    if not token or not isinstance(token, str):
        return None
    try:
        owner, exp_str, sig_b64 = token.split("|")
        exp = int(exp_str)
        if exp < int(time.time()):
            return None
        payload = f"{owner}|{exp}".encode("utf-8")
        expected = hmac.new(_cookie_secret(), payload, hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode("ascii")
        if not hmac.compare_digest(sig_b64, expected_b64):
            return None
        return owner
    except Exception:
        return None


def _set_auth_cookie(owner: str) -> None:
    token = _make_token(owner)
    _cookies().set(
        COOKIE_NAME,
        token,
        max_age=COOKIE_TTL_SEC,
        path="/",
        same_site="lax",
        secure=True,  # HTTPS 전용 (사이트는 nginx HTTPS 뒤에 있음)
    )


def _clear_auth_cookie() -> None:
    try:
        _cookies().remove(COOKIE_NAME, path="/")
    except Exception:
        pass


def _load_creds() -> Dict[str, str]:
    try:
        return json.loads(CREDS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _check_password(uid: str, pw: str) -> bool:
    """bcrypt 해시 검증. 성공 시 True."""
    creds = _load_creds()
    stored = creds.get(uid)
    if not stored:
        return False
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), stored.encode("utf-8"))
    except Exception:
        return False


def login_gate() -> None:
    """미로그인이면 로그인 폼 보여주고 st.stop(). 성공 시 owner 세팅 + 쿠키 발급.

    흐름:
    1. session_state.owner가 이미 있으면 그대로 통과.
    2. 없으면 브라우저 쿠키에서 토큰 복원 시도. 유효하면 owner 복원 + 통과.
    3. 그것도 없으면 로그인 폼. 성공 시 owner 세팅 + 쿠키 발급 + rerun.

    중요: streamlit-cookies-controller는 hidden iframe으로 document.cookie를
    fetch하므로, **첫 페이지 로드/WebSocket reconnect 시점에는 쿠키 값이 None**
    으로 도착할 수 있습니다. 곧장 None을 보고 로그인 폼을 띄우면, 사용자 입장
    에선 입력 도중 갑자기 로그아웃된 것처럼 보입니다(특히 streamlit이 widget
    변경을 받아 rerun을 트리거할 때). 이를 막기 위해 첫 None은 한두 번 spinner
    rerun으로 쿠키 도착을 기다린 뒤에야 진짜 "쿠키 없음"으로 판정합니다.
    """
    if st.session_state.get("owner"):
        return

    # (2) 쿠키 복원 — race condition 회피
    cookies = _cookies()
    token = cookies.get(COOKIE_NAME)

    if token is None:
        # 첫 None은 controller iframe 미수신일 수 있으므로 짧게 기다린다.
        n_tries = st.session_state.get("_kk_cookie_tries", 0)
        if n_tries < 2:
            st.session_state["_kk_cookie_tries"] = n_tries + 1
            with st.spinner("세션 복원 중..."):
                time.sleep(0.4)
            st.rerun()
            return
        # 2회 연속 None이면 진짜 쿠키 없음 → 로그인 폼으로 진행
    else:
        # 정상 도착 — 다음 라운드를 위해 카운터 리셋
        st.session_state["_kk_cookie_tries"] = 0

    restored = _verify_token(token)
    if restored:
        # 자격증명 파일에 여전히 존재하는 ID인지 한 번 더 확인 (권한 회수 시 강제 로그아웃)
        if _load_creds().get(restored):
            st.session_state.owner = restored
            return
        # 쿠키는 유효하지만 ID가 사라졌으면 쿠키 청소 후 로그인 폼으로 떨어뜨림
        _clear_auth_cookie()

    # (3) 로그인 폼
    st.title("knowing-koreans · 한국인 페르소나 시뮬레이터")
    st.caption("협업자 로그인 후 이용해 주세요. (한 번 로그인하면 7일간 자동 유지)")
    with st.form("kk_login_form", clear_on_submit=False):
        uid = st.text_input("ID", autocomplete="username")
        pw = st.text_input("비밀번호", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("로그인", type="primary")
    if submitted:
        if _check_password(uid.strip(), pw):
            st.session_state.owner = uid.strip()
            st.session_state["_kk_cookie_tries"] = 0  # 다음 reconnect 대비 리셋
            _set_auth_cookie(uid.strip())
            st.rerun()
        else:
            st.error("ID 또는 비밀번호가 틀렸습니다.")
    st.stop()


def get_owner() -> str:
    """로그인된 owner ID 반환. login_gate()가 우선 호출되어 보장된다."""
    return st.session_state.get("owner", "")


def logout_button() -> None:
    """사이드바에 로그아웃 버튼. 쿠키도 함께 비웁니다."""
    with st.sidebar:
        st.caption(f"로그인: **{get_owner()}**")
        if st.button("로그아웃", key="kk_logout"):
            _clear_auth_cookie()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def list_runs_for_owner(owner: str, limit: int = 5) -> List[Dict[str, Any]]:
    """results/gateway_runs/ 아래 owner의 최근 run 디렉토리 메타 반환."""
    if not RESULTS_DIR.exists():
        return []
    runs = []
    for d in sorted(RESULTS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        status_path = d / "status.json"
        if not status_path.exists():
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if status.get("owner") != owner:
            continue
        runs.append({"dir": d, "status": status})
        if len(runs) >= limit:
            break
    return runs


def find_active_run(owner: str) -> Optional[Dict[str, Any]]:
    for r in list_runs_for_owner(owner, limit=20):
        if r["status"].get("phase") in ACTIVE_PHASES:
            return r
    return None


def fmt_eta(sec: Optional[int]) -> str:
    if not sec or sec <= 0:
        return "—"
    if sec < 60:
        return f"{int(sec)}초"
    return f"{int(sec) // 60}분 {int(sec) % 60}초"


def fmt_time_short(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "—"
    try:
        return datetime.fromisoformat(iso_str).strftime("%m/%d %H:%M")
    except Exception:
        return iso_str[:16]


def new_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    token = secrets.token_hex(3)
    return f"{ts}-{token}"


def spawn_worker(run_dir: Path, run_id: str) -> None:
    """systemd-run으로 워커를 transient unit으로 띄우고 즉시 detach."""
    venv_python = PROJECT_ROOT / "venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable
    env_file = PROJECT_ROOT / ".env"
    cmd = [
        "systemd-run",
        "--collect",
        f"--unit=kk-run-{run_id}",
        f"--working-directory={PROJECT_ROOT}",
        f"--setenv=PATH={PROJECT_ROOT}/venv/bin:/usr/local/bin:/usr/bin:/bin",
    ]
    if env_file.exists():
        cmd.append(f"--property=EnvironmentFile={env_file}")
    cmd += [python_bin, "-m", "backend.run_worker", str(run_dir)]
    subprocess.Popen(cmd)


def cancel_worker(run_id: str) -> None:
    """systemctl stop으로 워커에 SIGTERM 전달."""
    subprocess.run(
        ["systemctl", "stop", f"kk-run-{run_id}"],
        check=False,
        capture_output=True,
    )


def trash_run(run_id: str, owner: str) -> tuple[bool, str]:
    """run_dir을 _trash/{run_id}/로 이동.

    검증:
      - run_dir 존재 + status.json 읽기 가능
      - status.owner == 호출자 owner (본인 것만 삭제)
      - phase가 ACTIVE_PHASES에 없음 (진행 중 차단)

    실패 시 (False, 사유) 반환. 성공 시 (True, 이동된 경로 문자열).
    """
    rd = RESULTS_DIR / run_id
    if not rd.exists() or not rd.is_dir():
        return False, "run 디렉토리 없음"
    status_path = rd / "status.json"
    if not status_path.exists():
        return False, "status.json 없음"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"status.json 읽기 실패: {e}"
    if status.get("owner") != owner:
        return False, "본인 측정만 삭제 가능"
    if status.get("phase") in ACTIVE_PHASES:
        return False, "진행 중 측정 — [측정 취소] 후 삭제 가능"

    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    target = TRASH_DIR / run_id
    if target.exists():
        target = TRASH_DIR / f"{run_id}__{int(time.time())}"
    try:
        rd.rename(target)
    except OSError as e:
        return False, f"이동 실패: {e}"
    return True, str(target)


def purge_old_trash(days: int = TRASH_RETENTION_DAYS) -> int:
    """휴지통에서 days일 지난 run_dir 영구 삭제. 반환: 삭제된 항목 수."""
    if not TRASH_DIR.exists():
        return 0
    cutoff = time.time() - days * 86400
    n_purged = 0
    for d in TRASH_DIR.iterdir():
        if not d.is_dir():
            continue
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d)
                n_purged += 1
        except Exception:
            continue
    return n_purged


@st.cache_data(ttl=3600 * 24, show_spinner=False)
def _purge_old_trash_throttled() -> int:
    """페이지 로드 시 1회 호출. 24h ttl로 매번 실행 회피."""
    return purge_old_trash()


# ─────────────────────────────────────────────────────────
# 페이지 레이아웃
# ─────────────────────────────────────────────────────────
st.set_page_config(page_title="knowing-koreans · 한국인 페르소나 시뮬레이터", layout="wide")
_init_state()
_purge_old_trash_throttled()
login_gate()
logout_button()

OWNER = get_owner()

# URL ?run={run_id}로 진입하면 4·5단계로 이동
qp_run_id = st.query_params.get("run")
if qp_run_id and st.session_state.get("active_run_id") != qp_run_id:
    candidate = RESULTS_DIR / qp_run_id
    if candidate.exists() and candidate.is_dir():
        st.session_state.active_run_id = qp_run_id
        # phase에 따라 4 or 5 결정
        try:
            status = json.loads((candidate / "status.json").read_text(encoding="utf-8"))
            st.session_state.step = 5 if status.get("phase") == "done" else 4
        except Exception:
            st.session_state.step = 4

st.title("knowing-koreans · 한국인 페르소나 시뮬레이터")
st.markdown(
    "**합성 페르소나로 큐레이터 가설을 점검하는 도구.** 한국 인구통계를 반영한 합성 페르소나 "
    "약 700만 명에게 전시·정책·기획 주제를 던져, 큐레이터가 미처 떠올리지 못한 "
    "관점·가설을 찾기 위한 도구입니다."
)
st.caption(
    "여기서 나온 응답은 여론조사·시장조사가 아닙니다. 합성 페르소나·AI의 응답이며 "
    f"정확도 예측에는 쓰지 마세요. (작업자: {OWNER})"
)

with st.expander("ℹ️ 이 도구가 쓰는 AI 3종의 역할", expanded=False):
    st.markdown(
        "이 도구는 **서로 다른 역할의 AI 3종**을 순서대로 사용합니다. "
        "역할이 분리된 이유는 단계마다 요구되는 능력이 다르기 때문입니다.\n\n"
        "1. **질문 정리 AI** — 1단계에서 큐레이터가 적은 자유 주제를 "
        "페르소나에게 던질 수 있는 질문 형식(컨텍스트 + 1~5개 질문 + 응답 JSON)으로 "
        "다듬습니다. 한국어 글쓰기 정확도와 형식 준수가 중요하므로 "
        "Anthropic Claude Sonnet 4.6(기본값)을 권장합니다. 1단계 [▸ 고급]에서 변경 가능합니다.\n"
        "2. **측정용 AI (페르소나 응답)** — 3단계에서 페르소나 1명당 1번씩, "
        "그 페르소나 입장에서 질문에 시나리오별 응답 항목 전수의 구조화 응답을 만듭니다. **여러 종을 동시에** "
        "돌려 모델별 응답 차이를 비교 시야로 보존합니다. 기본 3종은 페르소나 반영도 "
        "사전 검증을 통과한 Qwen3 Max·Hermes 4 70B·Claude Haiku 4.5입니다. "
        "3단계 [▸ 고급]에서 추가/교체 가능합니다.\n"
        "3. **분석용 AI (통찰 정리)** — 5단계 직전, 수집된 모든 응답·페르소나 narrative를 "
        "한 번에 시야로 받아 큐레이터용 4섹션 보고서(핵심 발견·관점·인용·후속 질문)를 "
        "작성합니다. 응답 전수를 발췌 없이 보아야 ambivalence·약신호가 잡히므로 "
        "**1M context + 강한 추론**을 동시에 만족해야 합니다. 기본값은 "
        "Anthropic Claude Opus 4.7(1M)이며, **3단계에서 측정 시작 직전에 직접 선택**하실 수 있습니다."
    )

step = st.session_state.step
cols = st.columns(5)
for i, (col, label) in enumerate(zip(cols, STEP_LABELS), start=1):
    with col:
        if i < step:
            st.success(label)
        elif i == step:
            st.info(label)
        else:
            st.write(label)
st.divider()


# ============ 1단계 ============
if step == 1:
    st.header("1) 무엇을 알아보고 싶으세요?")
    st.write(
        "측정하고 싶은 주제, 전시 개요, 또는 검토 중인 가설을 자유롭게 적어 주세요. "
        "AI가 합성 페르소나에게 던질 질문으로 정리해 드립니다."
    )

    topic = st.text_area(
        "측정 주제 / 전시 개요 / 가설 (자유 형식)",
        value=st.session_state.topic_text,
        height=240,
        placeholder=(
            "예시) 일상 도구를 모은 전시 〈사물이 머무는 곳〉에 관람객이 어떤 정서적 "
            "반응을 가질지 알고 싶다. 핵심 가설은 ‘머무름’이라는 시간의 의미에 대한 "
            "공감 여부…"
        ),
    )

    with st.expander("▸ 고급 — 질문 정리용 AI 모델 직접 고르기"):
        st.caption(
            "큐레이터가 적은 자유 주제를 페르소나용 질문 형식(컨텍스트 + 1~5개 질문 + "
            "응답 JSON)으로 다듬는 AI입니다. 한국어 글쓰기 정확도와 형식 준수가 중요해 "
            "기본값(Claude Sonnet 4.6) 그대로 두셔도 됩니다."
        )
        qgen_choice = st.selectbox(
            "질문 정리 AI",
            options=GEN_LLM_MODELS,
            index=GEN_LLM_MODELS.index(st.session_state.qgen_model)
            if st.session_state.qgen_model in GEN_LLM_MODELS else 0,
            format_func=model_label,
            label_visibility="collapsed",
        )

    cgen, _ = st.columns([1, 4])
    if cgen.button("질문 만들기", type="primary", disabled=not topic.strip()):
        st.session_state.topic_text = topic
        st.session_state.qgen_model = qgen_choice
        with st.spinner(f"{model_label(qgen_choice)}이(가) 질문을 정리하는 중…"):
            try:
                resp = call_llm(
                    qgen_choice,
                    QUESTION_GEN_SYSTEM,
                    QUESTION_GEN_USER_TEMPLATE.format(topic=topic),
                    json_mode=False,
                    temperature=0.4,
                    timeout=180,
                )
                st.session_state.draft_md = resp.text
                st.session_state.question_md = resp.text
                st.session_state.step = 2
                st.rerun()
            except Exception as e:
                st.error(f"질문 생성 실패: {e}")

    # ── 진행 중·최근 측정 카드 ──────────────────────────
    runs = list_runs_for_owner(OWNER, limit=5)
    if runs:
        st.divider()
        st.subheader(f"진행 중·최근 측정 ({OWNER})")
        for r in runs:
            status = r["status"]
            phase = status.get("phase", "")
            run_id = status.get("run_id", r["dir"].name)
            topic_short = status.get("topic_short", "(주제 없음)")
            started = fmt_time_short(status.get("started_at"))
            n_done = status.get("n_done", 0)
            n_total = status.get("n_total", 0)

            confirm_key = f"confirm_del_{run_id}"
            with st.container(border=True):
                # 헤더 — phase별 라벨
                if phase in ACTIVE_PHASES:
                    if phase == "calling_llm" and n_total:
                        eta = fmt_eta(status.get("eta_sec"))
                        st.markdown(
                            f"🟢 **진행 중** · {n_done}/{n_total} 응답 (ETA {eta})"
                        )
                    elif phase == "writing_report":
                        st.markdown("🟡 **보고서 정리 중**")
                    else:
                        st.markdown(f"🟡 **{phase_label_ko(phase)}**")
                elif phase == "done":
                    st.markdown(f"✅ **완료** · {n_done}/{n_total} 응답 + 보고서")
                elif phase == "cancelled":
                    st.markdown("⚪ **취소됨**")
                elif phase == "error":
                    st.markdown("🔴 **오류**")
                else:
                    st.markdown(f"⚪ **{phase_label_ko(phase)}**")

                st.markdown(f"“{topic_short}”")
                if phase == "error":
                    st.caption(
                        f"시작 {started}  ·  사유: {status.get('error', '(없음)')[:80]}"
                    )
                else:
                    st.caption(f"시작 {started}")

                # 액션 버튼 — phase별 분기
                if phase in ACTIVE_PHASES:
                    c1, c2 = st.columns([1, 2])
                    if c1.button("모니터링으로 이동", key=f"goto_{run_id}"):
                        st.query_params["run"] = run_id
                        st.session_state.active_run_id = run_id
                        st.session_state.step = 4
                        st.rerun()
                    c2.caption("진행 중 — [측정 취소] 후 삭제 가능")
                elif st.session_state.get(confirm_key):
                    # 두 단계 확인 모드
                    cc1, cc2, _ = st.columns([1, 1, 2])
                    if cc1.button("🗑️ 정말 삭제", key=f"del_yes_{run_id}", type="primary"):
                        ok, msg = trash_run(run_id, OWNER)
                        st.session_state.pop(confirm_key, None)
                        if ok:
                            st.toast("휴지통으로 이동했습니다 (30일 후 자동 비움)")
                            st.rerun()
                        else:
                            st.error(f"삭제 실패: {msg}")
                    if cc2.button("취소", key=f"del_no_{run_id}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                elif phase == "done":
                    c1, c2, _ = st.columns([1, 1, 2])
                    if c1.button("결과 다시 보기", key=f"goto_{run_id}"):
                        st.query_params["run"] = run_id
                        st.session_state.active_run_id = run_id
                        st.session_state.step = 5
                        st.rerun()
                    if c2.button("삭제", key=f"del_{run_id}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    c1, _ = st.columns([1, 3])
                    if c1.button("삭제", key=f"del_{run_id}"):
                        st.session_state[confirm_key] = True
                        st.rerun()


# ============ 2단계 ============
elif step == 2:
    st.header("2) 질문 확인")
    st.caption(
        "AI가 정리한 질문입니다. 자연어로 자유롭게 고치셔도 됩니다. 응답 형식(아래 회색 박스)을 "
        "직접 건드리지 않으셔도 되고, 고치셨다면 [AI에게 다시 정리받기]를 한 번 눌러 주세요."
    )
    md = st.text_area(
        "질문 (컨텍스트 + 질문 + 응답 형식)",
        value=st.session_state.question_md,
        height=480,
        label_visibility="collapsed",
    )

    c_back, c_redo, c_repolish, c_next = st.columns([1, 1, 1.4, 1.4])
    if c_back.button("← 1단계로"):
        st.session_state.step = 1
        st.rerun()
    if c_redo.button("처음부터 다시"):
        st.session_state.step = 1
        st.session_state.draft_md = ""
        st.rerun()
    if c_repolish.button("AI에게 다시 정리받기"):
        st.session_state.question_md = md
        with st.spinner(
            f"{model_label(st.session_state.qgen_model)}이(가) 수정본을 다시 정리하는 중…"
        ):
            try:
                resp = call_llm(
                    st.session_state.qgen_model,
                    QUESTION_GEN_SYSTEM,
                    QUESTION_REPOLISH_USER_TEMPLATE.format(
                        topic=st.session_state.topic_text,
                        edited=md,
                    ),
                    json_mode=False,
                    temperature=0.4,
                    timeout=180,
                )
                st.session_state.question_md = resp.text
                st.rerun()
            except Exception as e:
                st.error(f"다시 정리 실패: {e}")
    if c_next.button("그대로 다음 단계로", type="primary"):
        ctx, qs, schema = split_question_md(md)
        if not (ctx and qs and schema):
            st.error(
                "마크다운 형식을 확인해 주세요. ‘## 컨텍스트’, ‘## 질문’, "
                "‘## 응답 스키마 (JSON)’ 세 섹션과 ```json 코드 블록이 모두 필요합니다. "
                "혹시 형식을 직접 고치셨다면 [AI에게 다시 정리받기]를 한 번 눌러 주세요."
            )
        else:
            st.session_state.question_md = md
            st.session_state.ctx = ctx
            st.session_state.questions = qs
            st.session_state.schema_block = schema
            st.session_state.step = 3
            st.rerun()


# ============ 3단계 ============
elif step == 3:
    st.header("3) 누구에게 묻나요?")
    st.write("페르소나 표본 수·인구 필터·AI 모델을 정해 주세요.")

    # 동시성 정책 — 활성 측정이 있으면 차단
    active = find_active_run(OWNER)
    if active:
        active_run_id = active["status"].get("run_id", active["dir"].name)
        st.warning(
            "현재 진행 중인 측정이 있습니다. 완료 또는 취소 후 새로 시작하실 수 있습니다."
        )
        if st.button("진행 중 측정 모니터링으로 이동", type="primary"):
            st.query_params["run"] = active_run_id
            st.session_state.active_run_id = active_run_id
            st.session_state.step = 4
            st.rerun()
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        n_personas = st.number_input(
            "페르소나 수 (N)", min_value=1, value=20, step=1,
            help="처음에는 10~30 권장. 이 값이 곧 호출 수와 비용을 결정합니다. "
                 "본 라운드는 페르소나 1000명 영역까지 — 700만 Nemotron narrative 안에서 추출합니다.",
        )
    with c2:
        # 페이지 첫 진입 시마다 새 random seed 생성 (매 측정 다른 표본 보장).
        # 사용자가 직접 같은 시드를 입력하면 reproducibility 확보 가능.
        if "_default_seed" not in st.session_state:
            st.session_state["_default_seed"] = secrets.randbelow(2**31)
        seed = st.number_input(
            "랜덤 시드",
            min_value=0, max_value=2**31 - 1,
            value=st.session_state["_default_seed"],
            help="페이지 첫 진입 시마다 새 시드가 자동 생성됩니다. 같은 표본을 재현하려면 "
                 "이전 측정의 시드값을 직접 입력하세요.",
        )

    st.subheader("인구 필터 (선택)")
    st.caption(
        "랜덤 시드만 쓰면 약 700만 narrative에서 무작위 표본을 뽑습니다. "
        "아래 필터를 지정하면 해당 조건 안에서만 무작위 표본을 뽑습니다 — 예: "
        "‘서울 거주 + 20-29세 여성’."
    )
    f1, f2, f3 = st.columns(3)
    with f1:
        province = st.text_input("거주지 시·도 (province)", value="", placeholder="예: 서울")
        sex_choice = st.selectbox("성별 (Nemotron 라벨)", SEX_OPTIONS)
    with f2:
        age_min = st.number_input("나이 최소", min_value=0, max_value=120, value=0)
        age_max = st.number_input("나이 최대", min_value=0, max_value=120, value=120)
    with f3:
        education_level = st.text_input("교육 수준", value="")
        occupation = st.text_input("직업 (정확 일치)", value="")

    stratify_choice = st.selectbox(
        "균등 추출 차원 (선택)",
        ["(없음 — 단순 무작위)", "province", "age_bucket", "sex"],
        help="‘없음’이면 단순 무작위. 차원을 고르면 그 차원으로 그룹을 나눠 N/그룹씩 균등 추출.",
    )

    st.subheader("측정용 AI 모델 (페르소나 응답을 만드는 AI)")
    st.caption(
        "각 페르소나 1명마다 1번씩 호출되어 그 페르소나 입장에서 시나리오별 응답 항목 전수의 구조화 응답을 "
        "만듭니다. **여러 종을 동시에** 돌려 모델별 응답 차이도 비교 시야로 보존합니다. "
        "사전 검증에서 페르소나 반영도가 좋았던 3종을 기본으로 골라뒀습니다 — 일부만 "
        "쓰셔도 되고(1~2종 측정도 가능), 아래 [▸ 고급]에서 다른 모델을 추가하셔도 됩니다."
    )

    selected_default = st.multiselect(
        "기본 3종",
        options=DEFAULT_SIM_MODELS,
        default=[m for m in st.session_state.selected_models if m in DEFAULT_SIM_MODELS]
        or DEFAULT_SIM_MODELS,
        format_func=model_label,
        label_visibility="collapsed",
    )

    with st.expander("▸ 고급 — 다른 측정용 AI 모델 추가하기"):
        st.caption("기본 3종 외에 직접 골라 추가하실 수 있습니다.")
        extra_picked = st.multiselect(
            "추가 옵션",
            options=EXTRA_SIM_MODELS,
            default=st.session_state.extra_picked,
            format_func=model_label,
            label_visibility="collapsed",
        )

    selected_models = list(dict.fromkeys(selected_default + extra_picked))

    # ── 분석용 AI (v6.2 — 응답 전수 → 통찰 보고서) ──────
    st.subheader("분석용 AI 모델 (응답 전수를 읽고 통찰을 정리하는 AI)")
    st.caption(
        "측정이 끝나면 수집된 응답 전수와 페르소나 narrative를 한 번에 시야로 받아 "
        "큐레이터용 4섹션 보고서(핵심 발견·관점·인용·후속 질문)를 작성합니다. "
        "응답 전수를 발췌 없이 보아야 ambivalence·약신호가 잡히므로 **1M context + "
        "강한 추론**을 동시에 만족해야 합니다. 응답수가 많아 단일 호출 한도(약 50만 토큰)를 "
        "초과하면 자동으로 cluster 분할·병렬 분석 + cross-cluster diff + 합성 흐름으로 "
        "전환됩니다(map-reduce). 여기서 고른 모델이 분석 단계 모든 호출에 사용됩니다.\n\n"
        "**후보 비교** (입력/출력 $/MTok, context):\n"
        "- Opus 4.7: $5 / $25, 1M — 한국어 어조 강함, 가장 비쌈\n"
        "- Sonnet 4.6: $3 / $15, 1M — Opus 60% 가격 fallback\n"
        "- **Grok 4.20**: $1.20 / $6, 2M — 본 세션 E2E 검증 완료(실측 단가), 2M context로 단일 호출 유리\n"
        "- Grok 4-fast: $0.20 / $0.50, 2M — Grok 4.20의 약 1/10 가격, 한국어 어조 미검증\n"
        "- Qwen Plus thinking: $0.26 / $0.78, 1M — 1M reasoning 가성비, 한국어 어조 미검증"
    )

    analysis_default = (
        st.session_state.report_model
        if st.session_state.report_model in ANALYSIS_LLM_MODELS
        else ANALYSIS_LLM_MODELS[0]
    )
    analysis_choice = st.selectbox(
        "분석용 AI",
        options=ANALYSIS_LLM_MODELS,
        index=ANALYSIS_LLM_MODELS.index(analysis_default),
        format_func=model_label,
        label_visibility="collapsed",
    )

    with st.expander("▸ 고급 — 분석용 AI 모델 직접 입력 (다른 1M context 하이엔드)"):
        st.caption(
            "위 후보 외의 1M context 하이엔드 모델(예: `openrouter/google/gemini-2.5-pro`, "
            "`openrouter/openai/gpt-5`)을 쓰고 싶으시면 모델 ID를 그대로 입력해 주세요. "
            "비워두시면 위에서 고른 모델이 사용됩니다. 입력한 ID는 저장 직전 사전 검증을 "
            "통과해야 합니다."
        )
        analysis_custom = st.text_input(
            "model_id (예: openrouter/google/gemini-2.5-pro)",
            value="",
            placeholder="비워두시면 위 선택 사용",
            label_visibility="collapsed",
        )
    analysis_model = analysis_custom.strip() or analysis_choice
    st.session_state.report_model = analysis_model

    n_questions = max(1, len(re.findall(r"^\d+\)\s", st.session_state.questions, re.MULTILINE)))
    n_calls = int(n_personas) * len(selected_models)
    est_seconds = n_calls * 7
    est_min, est_sec = divmod(est_seconds, 60)
    if selected_models:
        st.info(
            f"예상 호출 수: {n_calls:,}회 (페르소나 {int(n_personas)}명 × AI "
            f"{len(selected_models)}종). 질문 {n_questions}개, 호출당 약 7초 가정 → "
            f"예상 소요 약 {est_min}분 {est_sec}초."
        )
    else:
        st.warning("AI 모델을 1종 이상 골라 주세요.")

    c_back, c_run = st.columns([1, 2])
    if c_back.button("← 2단계로"):
        st.session_state.selected_models = selected_default
        st.session_state.extra_picked = extra_picked
        st.session_state.step = 2
        st.rerun()

    if c_run.button("측정 시작 →", type="primary", disabled=not selected_models):
        filters: Dict[str, Any] = {}
        if province.strip():
            filters["province"] = province.strip()
        if sex_choice != "(상관없음)":
            filters["sex"] = sex_choice
        if int(age_min) > 0:
            filters["age_min"] = int(age_min)
        if int(age_max) < 120:
            filters["age_max"] = int(age_max)
        if education_level.strip():
            filters["education_level"] = education_level.strip()
        if occupation.strip():
            filters["occupation"] = occupation.strip()
        if stratify_choice != "(없음 — 단순 무작위)":
            filters["stratify_by"] = stratify_choice

        run_id = new_run_id()
        run_dir = RESULTS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "run_id": run_id,
            "owner": OWNER,
            "created_at": datetime.now().isoformat(),
            "topic": st.session_state.topic_text,
            "ctx": st.session_state.ctx,
            "questions": st.session_state.questions,
            "schema_block": st.session_state.schema_block,
            "qgen_model": st.session_state.qgen_model,
            "report_model": st.session_state.report_model,
            "n": int(n_personas),
            "seed": int(seed),
            "filters": filters,
            "models": list(selected_models),
        }

        # 사전 검증 (schema/engine drift)
        errors = validate_spec(spec)
        if errors:
            for e in errors:
                st.error(e)
            st.info("응답 형식이 어긋납니다. 2단계에서 [AI에게 다시 정리받기]를 한 번 눌러 주세요.")
            run_dir.rmdir()  # 빈 디렉토리 정리
            st.stop()

        (run_dir / "spec.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        st.session_state.selected_models = selected_default
        st.session_state.extra_picked = extra_picked

        try:
            spawn_worker(run_dir, run_id)
        except Exception as e:
            st.error(f"워커 실행 실패: {e}")
            st.stop()

        st.session_state.active_run_id = run_id
        st.session_state.step = 4
        st.query_params["run"] = run_id
        st.rerun()


# ============ 4단계 ============
elif step == 4:
    st.header("4) 응답 수집 중")

    run_id = st.query_params.get("run") or st.session_state.get("active_run_id")
    if not run_id:
        st.error("측정 ID가 없습니다. 1단계로 돌아가 주세요.")
        if st.button("← 1단계로"):
            st.session_state.step = 1
            st.rerun()
        st.stop()

    run_dir = RESULTS_DIR / run_id
    if not run_dir.exists():
        st.error(f"측정 디렉토리를 찾을 수 없습니다: {run_id}")
        if st.button("← 1단계로"):
            st.session_state.step = 1
            st.query_params.clear()
            st.rerun()
        st.stop()

    st.caption(
        f"측정 ID: `{run_id}`  ·  이 페이지를 닫으셔도 측정은 서버에서 계속 진행됩니다. "
        f"나중에 메인페이지(`/kk/`)로 다시 들어오시면 1단계 화면 상단의 "
        f"**“진행 중·최근 측정”** 카드에 이 측정이 보이고, [모니터링으로 이동] / "
        f"[결과 다시 보기] 버튼으로 이 화면에 돌아오실 수 있습니다. "
        f"URL을 따로 기억해두실 필요는 없습니다."
    )

    @st.fragment(run_every=2)
    def progress_fragment():
        status_path = run_dir / "status.json"
        if not status_path.exists():
            st.info("측정 시작 중…")
            return
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as e:
            st.warning(f"상태 파일을 읽는 중 오류: {e}")
            return

        phase = status.get("phase", "")
        n_done = status.get("n_done", 0)
        n_total = status.get("n_total", 0)
        n_ok = status.get("n_ok", 0)
        n_fail = status.get("n_fail", 0)

        if phase == "starting":
            st.info("측정 시작 — 워커 부팅 중…")
        elif phase == "loading_pool":
            st.info("페르소나 풀 로드 중… (첫 1회는 약 1분)")
        elif phase == "sampling":
            st.info("페르소나 표본 추출 중…")
        elif phase == "calling_llm":
            ratio = (n_done / n_total) if n_total else 0.0
            st.progress(min(1.0, ratio))
            m1, m2, m3 = st.columns(3)
            m1.metric("응답 수집", f"{n_done} / {n_total}")
            m2.metric("성공 / 실패", f"{n_ok} / {n_fail}")
            m3.metric("남은 시간 (ETA)", fmt_eta(status.get("eta_sec")))
            avg = status.get("avg_sec_per_call", 0)
            if avg:
                st.caption(f"평균 응답 시간: {avg:.2f}초/건")
        elif phase == "writing_report":
            st.info("응답 수집 완료. 통찰 정리 중… (1~3분)")
        elif phase == "done":
            st.success("측정 완료. 통찰 보고서가 준비되었습니다.")
            if st.button("통찰 보고서 보기 →", type="primary", key="goto_report"):
                st.session_state.step = 5
                st.rerun()
        elif phase == "error":
            st.error(f"오류로 중단됨: {status.get('error', '(원인 미상)')}")
            # 진단용: result.csv가 있으면 error 컬럼을 큐레이터가 직접 볼 수 있게 다운로드 제공
            result_csv_err = run_dir / "result.csv"
            if result_csv_err.exists():
                st.download_button(
                    "진단용 result.csv 다운로드",
                    data=result_csv_err.read_bytes(),
                    file_name=f"{run_id}_result.csv",
                    mime="text/csv",
                    help="각 호출의 성공/실패와 실패 원인(error 컬럼)이 들어 있습니다.",
                )
        elif phase == "cancelled":
            st.warning("측정이 취소되었습니다.")
        else:
            st.write(f"phase: {phase}")

        st.caption(f"마지막 갱신: {fmt_time_short(status.get('updated_at'))}")

    progress_fragment()

    st.divider()
    c_cancel, c_back = st.columns([1, 1])
    # 활성 phase일 때만 [측정 취소]
    try:
        cur_phase = json.loads((run_dir / "status.json").read_text(encoding="utf-8")).get("phase")
    except Exception:
        cur_phase = None
    if cur_phase in ACTIVE_PHASES:
        if c_cancel.button("측정 취소", type="secondary"):
            cancel_worker(run_id)
            st.toast("취소 요청 전송 — 워커 종료 대기")
    if c_back.button("← 1단계로 (다른 측정)"):
        st.session_state.step = 1
        st.query_params.clear()
        st.rerun()


# ============ 5단계 ============
elif step == 5:
    st.header("5) 통찰 정리")

    run_id = st.query_params.get("run") or st.session_state.get("active_run_id")
    if not run_id:
        st.error("측정 ID가 없습니다.")
        if st.button("← 1단계로"):
            st.session_state.step = 1
            st.rerun()
        st.stop()

    run_dir = RESULTS_DIR / run_id
    status_path = run_dir / "status.json"
    if not status_path.exists():
        st.error(f"상태 파일이 없습니다: {run_id}")
        st.stop()

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as e:
        st.error(f"상태 파일 파싱 실패: {e}")
        st.stop()

    if status.get("phase") != "done":
        st.warning(
            f"보고서가 아직 준비되지 않았습니다. (현재 phase: {status.get('phase')}). "
            "4단계에서 진행상황을 보실 수 있습니다."
        )
        if st.button("← 4단계로"):
            st.session_state.step = 4
            st.rerun()
        st.stop()

    report_png = run_dir / "report.png"
    report_pdf = run_dir / "report.pdf"
    sources_zip = run_dir / "sources.zip"

    st.write(
        "AI가 응답 전체를 읽고, 큐레이터가 미처 떠올리지 못했을 만한 관점·가설을 "
        "정리한 보고서입니다."
    )

    if report_png.exists():
        st.image(str(report_png), use_container_width=True)
    else:
        # PDF/PNG 렌더가 실패한 경우 마크다운 fallback
        report_md = run_dir / "report.md"
        if report_md.exists():
            st.markdown(report_md.read_text(encoding="utf-8"))
        else:
            st.error("보고서 파일을 찾을 수 없습니다.")

    col_pdf, col_zip = st.columns(2)
    with col_pdf:
        if report_pdf.exists():
            st.download_button(
                "보고서 PDF 다운로드",
                data=report_pdf.read_bytes(),
                file_name=f"{run_id}_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.button("보고서 PDF (생성 실패)", disabled=True, use_container_width=True)
    with col_zip:
        if sources_zip.exists():
            st.download_button(
                "원천소스 묶음 다운로드 (셀프분석용)",
                data=sources_zip.read_bytes(),
                file_name=f"{run_id}_sources.zip",
                mime="application/zip",
                use_container_width=True,
            )
        else:
            st.button("원천소스 묶음 (생성 실패)", disabled=True, use_container_width=True)

    st.caption(
        "PDF는 인쇄·공유용. 원천소스 묶음은 페르소나 샘플·원본 응답·명세를 포함해 "
        "큐레이터가 직접 raw 응답을 파고들 수 있도록 한 묶음입니다."
    )

    st.divider()
    c_back, c_new = st.columns([1, 1])
    if c_back.button("← 4단계로 (진행상황 다시 보기)"):
        st.session_state.step = 4
        st.rerun()
    if c_new.button("새 측정 시작 (1단계로)", type="primary"):
        st.session_state.step = 1
        st.query_params.clear()
        for k in ["topic_text", "draft_md", "question_md",
                  "ctx", "questions", "schema_block", "active_run_id"]:
            st.session_state.pop(k, None)
        st.rerun()

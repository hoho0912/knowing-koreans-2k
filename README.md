# knowing-koreans · 한국인 페르소나 시뮬레이터

> **합성 페르소나로 큐레이터 가설을 점검하는 도구.**

NVIDIA Nemotron-Personas-Korea 700만 합성 페르소나에 박물관·문화·정책 시나리오를 던져, 여러 LLM이 어떻게 응답하는지 비교·시각화합니다.

이 도구는 **여론 예측기가 아닙니다**. "이 모델·이 표본에서는 ~한 신호가 보인다" 정도의 약한 시사점을 큐레이터·연구자가 다음 질문을 만드는 데 쓰도록 설계된 **가설 점검용 도구**입니다.

---

## 라이선스

| 구성 요소 | 라이선스 |
|---|---|
| 본 저장소 코드 | MIT (`LICENSE` 참조) |
| 페르소나 데이터셋 (Nemotron-Personas-Korea) | CC BY 4.0 (NVIDIA) |
| LLM 응답 데이터 | 각 LLM 제공자의 약관에 따름 — 본 저장소에 포함된 측정 결과 CSV는 모델 응답 본문이라 재배포 시 출처 명시 권장 |

---

## 무엇을 하나

```
[시나리오: context.md + question.md]
        ↓
[페르소나 N명 무작위 추출 (인구통계 stratified)]
        ↓
[페르소나 narrative + 시나리오 → LLM 다중 호출]
        ↓
[result.csv (N × 모델수 행, 응답 메타·자유서술 포함)]
        ↓
[코드 결정론 통계 + 분석용 LLM 인사이트 → report.md / report.pdf / report.png]
```

핵심 차별점:
- **컨텍스트 grounding**: 시나리오마다 1차 자료(전시 기획서·정책 문헌·인터뷰)를 컨텍스트로 LLM에 주입.
- **시나리오 모듈화**: `scenarios/<name>/` 디렉토리 4파일(`context.md` / `question.md` / `scenario_vars.json` / `viz.py`)만 채우면 새 주제 추가.
- **다중 LLM 동시 비교**: OpenAI · OpenRouter (Anthropic / Google / xAI / Meta 등) · Ollama 로컬을 단일 인터페이스로 호출.
- **시점 메타데이터**: 각 응답에 `context_snapshot_id` + `timestamp` 기록 — 같은 시나리오를 시점별 컨텍스트로 반복 측정해 시계열 분석.

---

## 본 저장소가 검증해 본 것

본 저장소는 단순히 합성 페르소나에 LLM을 호출해 결과를 보여주는 것이 아니라, 페르소나 시뮬이 의미 있게 작동하기 위한 사전 단계와 한국 박물관 도메인의 첫 공개 사례를 함께 수행했다. 핵심은 다음 셋이다.

### 1. 페르소나 신호를 통과시키는 모델만 본 측정에 사용한다

다중 LLM 시뮬에서 가장 흔히 나타나는 실패는 RLHF로 정렬된 모델이 페르소나 narrative를 무시하고 평균 응답에 회귀하는 패턴이다. 같은 페르소나에 다른 모델을 던졌을 때 모델 간 응답 격차(모델 편향)가 다른 페르소나에 같은 모델을 던졌을 때 페르소나 간 응답 격차(페르소나 변동)보다 크면, 페르소나 시뮬은 사실상 모델 fingerprint 보고서가 된다.

본 저장소는 본 측정 전에 사전 측정 단계를 두어 이 비율을 노출하고, 페르소나 변동을 살리는 모델만 본 측정에 사용한다.

| 차수 | 시점 | 측정 규모 | 핵심 발견 |
|---|---|---|---|
| ① 1차 prototype | 4-28 오후 | 페르소나 5명 × 모델 5종 = 응답 25건 | 모델 편향 0.71 vs 페르소나 변동 0.29 — **2.5배 격차** |
| ② N=100 본 측정 A+B | 4-28 밤 | 페르소나 100명 × 모델 4종 = 응답 397건 | 비율 **1.88배**. 모델별 std 격차 극단: claude-haiku-4.5 std 0.75(no 67%) ↔ gpt-4o-mini std 0.17(yes 97%) ↔ gemini-2.5-flash std 0.43(yes 0%·maybe 82%) ↔ qwen-2.5-72b std 0.25 |
| ③ 3차 모델 후보 smoke | 4-29 오전 | 페르소나 5명 × 모델 7종 = 응답 35건 | qwen3-max·hermes-4-405b 공동 1위 (std 0.89, claude-haiku-4.5 baseline 초과). deepseek-v3.2 std 0.00 — mode collapse |
| ④ 본 측정 7항목 | 4-29 저녁 | 페르소나 100명 × 모델 3종 = 응답 300건 | qwen3-max(std 0.89) / hermes-4-70b(std 0.69) / claude-haiku-4.5(mean 2.58) — 7항목 구조화 응답으로 ambivalence 가시화 |
| ⑤ 본 라운드 N=1,000 | 5-01 새벽 | 페르소나 1,000명 × hermes-4-405b 단일 = 응답 1,000건 | **박물관 관람료 무료화 시나리오**. 5질문(Likert 3 + 카테고리 1 + 자유서술 1)을 단일 모델로 던져 페르소나 변동 폭을 본다 |

사전 측정 없이 모델 1~2개로 곧바로 본 측정에 들어가면 모델 편향이 결과를 지배해 페르소나 시뮬 의미가 사라진다. 본 저장소는 이 절차를 공개해 후속 연구·도메인 응용이 같은 함정에 빠지지 않게 한다.

### 2. 한국 박물관·문화 도메인 첫 시도

본 저장소는 한국의 박물관·문화 분야에서 합성 페르소나 시뮬을 적용한 첫 공개 시도다. NVIDIA Nemotron-Personas-Korea의 한국 인구통계 분포(약 700만 페르소나 × 7개 narrative 컬럼)를 기반으로 박물관·전시·문화재 시나리오에 대한 응답을 큐레이터의 가설 발생 도구로 변환한다.

**본 저장소가 외부 공개로 진행한 첫 사례는 박물관 관람료 무료화다** — 박물관·미술관 관람료를 무료화했을 때 한국 인구통계 분포의 시민이 "실제 가서 볼 의향"·"가장 끌리는 요소"·"가장 걱정되는 점"을 어떻게 자유서술하는지를 ⑤단계 N=1,000 측정으로 본다.

후속 시나리오 후보:

- 문화재 환수 의제(해외 한국 문화재 반환 우선순위)
- 전통 vs 현대 전시 콘셉트(같은 주제를 어느 어조로 풀어야 시민이 응답하는가)
- 야간개장·동행자별 관람 패턴(`preferred_companion` 차원 활용)

### 3. 결과 소개 페이지

원시 데이터(CSV·JSON)와 분석 코드는 본 저장소에 그대로 있지만, 큐레이터·기획자가 결과를 빠르게 훑을 수 있도록 결과 소개 페이지를 GitHub Pages에 별도 배포한다:

→ https://hoho0912.github.io/knowing-koreans-2k/

페이지는 stlite + Pyodide 기반으로 브라우저에서 직접 Python을 돌려 시뮬 결과 CSV를 차트로 띄운다. 첫 화면은 ① prototype(페르소나 25건) 시각화로 도구 동작을 보여주고, ⑤ 본 라운드 N=1,000 측정 결과(박물관 관람료 무료화 시나리오)의 발견 패턴·axis별 분포·인용 응답 카드·큐레이터용 후속 질문은 본 라운드 데이터 회수 후 4섹션 보고서로 추가된다.

---

## 빠른 시작 (5분)

### 1. 저장소 clone + Python 환경

```bash
git clone https://github.com/hoho0912/knowing-koreans-2k.git
cd knowing-koreans-2k
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경 변수

`.env.example`을 복사해 `.env.local` 만들고 키 입력:

```bash
cp .env.example .env.local
# 편집기로 열어 OPENAI_API_KEY / OPENROUTER_API_KEY 등 채움
```

| 변수 | 용도 | 비고 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI 직접 호출 | 선택 (OpenRouter만 써도 무관) |
| `OPENROUTER_API_KEY` | 다중 모델 게이트웨이 | 권장 — Anthropic·Google·xAI·Meta 등 단일 키로 |
| `HF_TOKEN` | Hugging Face | 선택 — Nemotron 데이터셋은 공개라 비필수, rate limit 회피용 |
| `OLLAMA_HOST` | 로컬 Ollama | 기본값 `http://localhost:11434` |

### 3. 페르소나 데이터셋 1회 다운로드

```bash
# 1명 샘플 추출만 시도 — 첫 호출 시 데이터셋 자동 다운로드
python -m backend.persona_sampler 1
# 약 3GB. 한 번만 받으면 backend/nvidia-personas/ 아래 캐시됨 (gitignored).
```

### 4. 첫 측정 (소규모, 5명)

```bash
python -m backend.run_scenario \
  --scenario-id exhibition_appeal \
  --context-snapshot 2026-04 \
  --models "openrouter/anthropic/claude-3.5-haiku,openrouter/openai/gpt-4o-mini" \
  --n 5 \
  --seed 42
```

결과: `backend/results/exhibition_appeal_2026-04.csv`에 5명 × 2모델 = 10건 응답 누적.

---

## 시나리오 만들기

본 저장소가 핵심으로 권하는 사용 방식입니다. 본인 분야의 시나리오를 추가해 LLM 페르소나 시뮬을 굴려 보세요.

### 디렉토리 구조

```
scenarios/<your_scenario_id>/
├── context.md            ← LLM 주입용 컨텍스트 (수치·출처 제거, 중립 톤)
├── question.md           ← 질문 + 응답 JSON 스키마
├── scenario_vars.json    ← (선택) context.md 안의 {{변수}} 치환값
└── viz.py                ← 시각화 차원 정의 (axis 배치)
```

### `context.md` 작성 원칙

- **여론조사 수치·정량 통계 제외** — LLM이 그 수치에 앵커링하지 않게.
- **중립 톤** — 정책 옹호·반대 용어 회피.
- **시점 메타데이터** — 첫 줄에 `# 시점: YYYY-MM` 기록 (같은 시나리오 시점별 비교용).
- 출처·수치는 같은 디렉토리 `*_research_notes.md` 등 별도 파일로 분리해 보존.

### `question.md` 작성 원칙

- 시뮬 질문은 단일 yes/no가 아니라 **다항목 구조화 응답**으로 — Likert 점수 + 자유서술 + 다항선택을 함께.
- 응답 JSON 스키마를 같은 파일에 명시. 본 저장소의 `scenarios/exhibition_appeal/question.md`가 7항목 응답 (`appeal_score` / `visit_intent` / `key_attraction` / `key_concern` / `reason` / `preferred_companion` / `recommend_to`) 예시입니다.
- 자유서술 항목은 권장 분량 명시 ("200~400자").

### `viz.py` 작성

- 시각화 axis 정의 (성별·연령·지역·교육·직업·가족 구성 등 페르소나 컬럼 중 어떤 축으로 분포를 볼지).
- `scenarios/exhibition_appeal/viz.py`가 골격 예시 — 그대로 복사해 본인 컬럼만 교체.

### Schema drift 방지

`backend/run_scenario.py`는 측정 launch 직전에 `validate_prompt_schema()`로 `question.md` 스키마와 런타임 prompt 템플릿이 일치하는지 zero-cost 검증합니다. drift 발견 시 0초 안에 abort하므로 25분짜리 측정을 통째로 손해 보지 않아도 됩니다.

---

## 본격 측정 — 보고서·인포그래픽까지

`run_scenario.py`는 단순 CSV 누적용입니다. 본격 보고서(통계 표 + LLM 인사이트 + PDF·PNG)까지 만들려면 `run_worker.py`를 사용합니다.

### `run_worker.py` 흐름

```
run_dir/
├── spec.json          ← 측정 사양 (어떤 시나리오·N·모델·인사이트 LLM)
├── personas.csv       ← (자동 생성) 추출된 페르소나
├── result.csv         ← (자동 생성) LLM 응답 누적
├── report.md          ← (자동 생성) 본문
├── report.pdf         ← (자동 생성) 큐레이터용 보고서
├── report.png         ← (자동 생성) 1페이지 미리보기
├── insight.json       ← (자동 생성) 분석 LLM 산출 인사이트
├── status.json        ← (자동 생성) 진행률
└── sources.zip        ← (자동 생성) spec + personas + result + report 묶음
```

### `spec.json` 양식

```json
{
  "scenario_id": "exhibition_appeal",
  "context_snapshot": "2026-04",
  "topic": "전시 제목 또는 측정 주제",
  "ctx": "(선택) context.md 외 추가 맥락",
  "questions": "(선택) question.md 외 추가 질문",
  "n_personas": 100,
  "models": [
    "openrouter/anthropic/claude-3.5-haiku",
    "openrouter/openai/gpt-4o-mini",
    "openrouter/x-ai/grok-4-fast"
  ],
  "report_model": "openrouter/anthropic/claude-opus-4-7",
  "seed": 42
}
```

### 실행

```bash
mkdir -p backend/results/run_2026-05-01_my_scenario
# 위 양식대로 spec.json 작성 후
python -m backend.run_worker backend/results/run_2026-05-01_my_scenario
```

진행률은 `status.json`을 폴링해 확인 (gateway.py가 그 역할을 담당).

### 보고서 산출물 구조

`report.md` / `report.pdf` 4섹션:

1. **개요** — 시나리오 헤더 + 페르소나 인구통계 인포그래픽 (D 차트: 성별·연령 분포 / E 차트: 지역·교육·직업 / F 차트: 핵심 응답 axis 분포)
2. **핵심 발견** — 분석 LLM이 추출한 패턴 3~5개 (응답 항목 간 ambivalence 포함)
3. **axis별 분포** — 페르소나 axis × 응답 항목의 결정론 통계 표
4. **곱씹을 만한 응답 + 다음 던져볼 질문** — 큐레이터가 후속 시나리오를 짜는 데 쓰도록 의도된 자유서술

---

## 분석용 LLM 선택

응답을 받은 뒤 패턴 추출에 쓰는 "분석 LLM"은 측정용과 분리되어 있습니다 (`spec.json`의 `report_model` 필드).

- 본 저장소 default 권장: 1M context · 강한 추론을 가진 하이엔드 모델 (예: Anthropic Claude Opus 4.7 1M, Google Gemini 2.5 Pro 1M, xAI Grok 4 등). 페르소나 narrative 전수 + 응답 raw 전수를 한 번에 시야에 둘 수 있어, 응답 항목 간 ambivalence·자유서술 의미·페르소나↔응답 정합성을 모두 봅니다.
- 응답 ≤ 600건 영역에서는 단일 호출 가능. 응답 > 900건 영역에서는 `run_worker.py`가 자동으로 cluster 분할 + cross-cluster diff + synthesis의 다단 호출 모드(B)로 분기합니다.
- 비용 절감 우선이면 `report_model`을 더 가벼운 모델로 교체 가능 — 다만 ambivalence 해석 품질이 떨어질 수 있다는 점은 감안하세요.

---

## Streamlit 게이트웨이 (`gateway.py`)

`gateway.py`는 측정 의뢰·진행률·산출물 다운로드를 위한 Streamlit UI입니다. **현재 비밀번호 인증이 켜져 있어 외부 연구자는 곧바로 동작하지 않습니다** — 본인 환경에서 쓰려면:

1. 사용자 본인의 `.creds-kk.json`을 만들거나 (양식: `{"users": {"id": "password_hash"}}`)
2. `gateway.py`의 인증 블록을 주석 처리해 비활성화

다른 연구자에게는 `run_worker.py`를 직접 CLI로 실행하시기를 권합니다.

---

## 메인 진입점

| 스크립트 | 용도 |
|---|---|
| `backend/run_scenario.py` | 소규모 측정 (CSV 누적만) |
| `backend/run_worker.py` | 본격 측정 (보고서·인사이트·PDF까지) |
| `backend/run_validate.py` | spec.json schema drift 사전 검증 |
| `backend/analyze_b3_v2.py` | 결정론 통계만 (LLM 호출 없이 보조 분석용) |

---

## 알려진 한계

- **LLM 균질화·고정관념** — 페르소나 narrative가 같아도 모델은 평균치로 수렴하는 경향. 다중 모델 비교로 모델별 편향 패턴 노출.
- **Social desirability bias** — LLM은 사회적으로 적절한 답을 선호. 자유서술이 모델별로 비슷해질 위험.
- **Nemotron 페르소나의 도메인 깊이 부족** — 박물관·문화 영역 prefer 컬럼은 합성에 한계. 본 저장소는 시나리오 `context.md`에 도메인 1차 자료를 grounding해 보완.
- **시간·문화 일반화 한계** — 시점 컨텍스트(`context_snapshot`)로 한정.
- **여론 예측 도구 아님** — 이 점을 보고서 본문에서도 명시 (`disclaimer` 섹션).

---

## 기여

- 이슈는 GitHub Issues로 — 버그 리포트는 가능하면 `spec.json` + `status.json` 동봉.

---

## 인용

본 저장소나 산출물을 학술·실무에 인용할 때:

```
Hosan Kim(2026). knowing-koreans: a synthetic-persona × multi-LLM
hypothesis generator for Korean curators.
https://github.com/hoho0912/knowing-koreans-2k
```

Nemotron-Personas-Korea 데이터셋 인용은 NVIDIA 측 안내를 따라 별도로 표기하세요.

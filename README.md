# knowing-koreans · 한국인 페르소나 시뮬레이터

> **합성 페르소나로 가설을 점검하는 도구.**

NVIDIA Nemotron-Personas-Korea 700만 합성 페르소나에 박물관·문화·정책 시나리오를 던져, 여러 LLM이 어떻게 응답하는지 비교·시각화합니다.

이 도구는 **여론 예측기가 아닙니다**. "이 모델·이 표본에서는 ~한 신호가 보인다" 정도의 약한 시사점을 큐레이터·연구자가 다음 질문을 만드는 데 쓰도록 설계된 **가설 점검용 도구**입니다.

---

## 버전 / 변경 이력


### v0.3.1 · 2026-05-04 — 보고서 구조 ①~⑧ 재정렬 + 분석 표 LLM 자율 결정

- 보고서 합성 LLM 산출물을 5섹션 JSON으로 재설계 (`analysis_tables` / `key_findings` / `curator_hypotheses` / `responses_to_chew_on` / `next_questions`)
- 분석 표(③ 섹션)는 보고서 합성 LLM이 응답 schema(질문 type)와 raw 응답을 직접 보고 표 종류·축·집계 방식을 자율 결정 — type 분기 하드코딩 제거
- frontend-obs 보고서 페이지 구조를 ①~⑧로 재정렬 (① 핵심 분포 / ② 교차분석 / ③ 분석 표 / ④ 발견 패턴 / ⑤ 곱씹을 만한 응답 / ⑥ 응답 카드 / ⑦ 큐레이터 가설 / ⑧ 다음에 던져볼 질문)
- 다크 모드 H2 청색 밑줄 fix — Framework `--theme-foreground-alt` CSS 변수 override
- footer/sidebar/toc/pager/search Framework 기본값 비활성화로 보고서 본문에 집중
- schema 타입 분기를 `likert_5` / `likert_7` / `single_choice` / `free_text` 4종으로 일반화 — 신규 시나리오 추가 시 코드 수정 불필요

### v0.3.0 · 2026-05-03 — Observable Framework 도입 + 차트 정렬

- 시각화 stack을 streamlit + stlite에서 Observable Framework v1.13.4로 전환 (`frontend-obs/`)
- Q1·Q2·Q3 100% 누적 막대(통합) + Q4·Q5 lollipop + 페르소나 속성 × Q1 crosstab 9종으로 차트 다양화
- 막대 안 비율(%) 텍스트를 각 세그먼트 stack midpoint에 정렬 (`x_mid` 사전 계산)
- Likert 1~5 한국어 라벨을 색상 범례 + x축에 표기
- GitHub Pages 자동 빌드 도입 (`.github/workflows/deploy.yaml`)
- 이전 `frontend/streamlit_app.py` + `frontend/index.html` 폐기

### v0.2.0 · 2026-05-01 — 본 라운드 N=1,000 보고서 공개

- 박물관 관람료 유료화 시나리오 본 측정 결과 공개 (`hermes-4-405b` 단일, 998 응답 / valid 937)
- 첫 GitHub 공개 (`hoho0912/knowing-koreans-2k`)
- 5단계 모델 필터링 표를 README 본문에 정리

### v0.1.0 · 2026-04-28~30 — 사전 측정 ①~④ + 골격

- 4축 골격 정립 — 인프라+시나리오 플러그인 / 컨텍스트 grounding / 페르소나 깊이 단계화 / 시계열 누적
- 모델 5단계 필터링(prototype 25건 → N=100 본 측정 A+B → 모델 후보 보완 → 본 측정 7항목) 수행
- 페르소나/모델 변동 폭 비교 지표 도입

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
- **컨텍스트 grounding**: 시나리오마다 1차 자료(전시 기획서·정책 문헌·인터뷰)를 컨텍스트로 LLM에 주입합니다.
- **시나리오 모듈화**: `scenarios/<name>/` 디렉토리 4파일(`context.md` / `question.md` / `scenario_vars.json` / `viz.py`)만 채우면 새 주제를 추가할 수 있습니다.
- **다중 LLM 동시 비교**: OpenAI · OpenRouter (Anthropic / Google / xAI / Meta 등) · Ollama 로컬을 단일 인터페이스로 호출합니다.
- **시점 메타데이터**: 각 응답에 `context_snapshot_id` + `timestamp`를 기록해, 같은 시나리오를 시점별 컨텍스트로 반복 측정하면 시계열 분석이 가능합니다.

---

## 본 저장소가 검증해 본 것

본 저장소는 단순히 합성 페르소나에 LLM을 호출해 결과를 보여주는 데 그치지 않고, 페르소나 시뮬이 의미 있게 작동하기 위한 사전 단계와 한국 박물관 도메인의 첫 공개 사례를 함께 수행했습니다. 핵심은 다음 세 가지입니다.

### 1. 페르소나 신호를 통과시키는 모델만 본 측정에 사용합니다

다중 LLM 시뮬에서 가장 흔히 나타나는 실패는 RLHF로 정렬된 모델이 페르소나 narrative를 무시하고 평균 응답에 회귀하는 패턴입니다. 같은 페르소나에 여러 모델을 던졌을 때의 모델 간 응답 격차(모델 편향)가, 여러 페르소나에 같은 모델을 던졌을 때의 페르소나 간 응답 격차(페르소나 변동)보다 크면 페르소나 시뮬은 사실상 모델 자체의 응답 패턴만 보여주는 보고서로 변질됩니다.

본 저장소는 본 라운드 N=1,000 측정에서 단일 모델(`hermes-4-405b`)을 쓰기까지 5단계의 사전 측정을 거쳤습니다. 각 단계에서 어떤 모델을 후보로 던졌고, 어떤 기준으로 통과·탈락시켰는지 표로 정리했습니다.

| 차수 | 측정 규모 | 후보 모델 (✓ 통과 / ✗ 탈락) | 다음 차수로 넘긴 결정 |
|---|---|---|---|
| ① 1차 prototype<br>(4-28 오후) | 페르소나 5명 × 모델 5종 = 응답 25건 | ✓ `claude-haiku-4.5` (2·2·4·2·2, std 0.71)<br>✗ `gpt-4o-mini` (4·4·4·4·4 — 응답이 정중한 톤 한 칸에 고정)<br>✗ `qwen-2.5-72b` (3·3·3·3·3 — 페르소나가 달라도 같은 점수)<br>✗ `gemini-2.5-flash` (3·3·3·3·3 — 페르소나가 달라도 같은 점수)<br>✗ `gpt-5-mini` (응답 토큰의 84%가 reasoning에 청구되어 비용 비효율) | 모델 편향 0.71 vs 페르소나 변동 0.29 — **2.5배 격차**. reasoning 모델의 비용 비효율 확인 → ②에서 `gpt-5-mini` 제외 후 4종으로 본 측정 |
| ② N=100 본 측정 A+B<br>(4-28 밤) | 페르소나 100명 × 모델 4종 = 응답 397건 | ✓ `claude-haiku-4.5` (std 0.75, no 67%)<br>△ `gemini-2.5-flash` (std 0.43, yes 0%·maybe 82%)<br>△ `qwen-2.5-72b` (std 0.25)<br>✗ `gpt-4o-mini` (std 0.17, yes 97% — 응답이 정중한 톤 한 칸에 고정되는 패턴 재확인) | 비율 **1.88배**. 기준 모델 4종 중 페르소나 신호를 충분히 통과시킨 모델은 claude-haiku 한 종뿐 — 페르소나에 민감하게 반응하는 연구소 후보를 추가로 조사할 필요 → ③에서 7종 보완 측정 |
| ③ 3차 모델 후보 보완 측정<br>(4-29 오전) | 페르소나 5명 × 모델 7종 = 응답 35건 | ✓ `qwen3-max` (std 0.89 — 응답 변동 폭 공동 1위)<br>✓ `hermes-4-405b` (std 0.89 — 응답 변동 폭 공동 1위)<br>△ `mistral-large-2512` (std 0.55)<br>△ `deepseek-v4-flash` (std 0.55)<br>△ `claude-sonnet-4.6` (std 0.45)<br>△ `deepseek-v4-pro` (std 0.45, 응답 한 건 63초 — 본 측정에 적용하기 어려움)<br>✗ `deepseek-v3.2` (std 0.00 — 모든 응답이 동일, mode collapse) | qwen3-max·hermes-4-405b가 ②의 기준 모델 1위(claude-haiku 0.75)를 응답 변동 폭에서 넘어섰음. 본 측정 3종으로 좁히면서 hermes는 비용 부담을 줄이려고 `4-70b` 변종으로 시험 → ④에서 RLHF 결이 다른 3종 비교 구도 |
| ④ 본 측정 7항목<br>(4-29 저녁) | 페르소나 100명 × 모델 3종 = 응답 300건 | ✓ `qwen3-max` (std 0.89 — 응답이 가장 다양한 차수)<br>✓ `hermes-4-70b` (std 0.69 — 응답이 가장 합의된 차수)<br>✓ `claude-haiku-4.5` (mean 2.58 — 응답이 가장 부정적인 차수) | 3종 모두 RLHF 결이 다른 축(다양성·합의·부정성)을 그대로 통과. 본 라운드 N=1,000 영역에서는 단일 모델 단면으로 페르소나 변동 폭을 깨끗하게 보기로 결정 → ⑤에서 ③의 공동 1위 중 hermes 큰 모델(`4-405b`) 단일 |
| ⑤ 본 라운드 N=1,000<br>(5-01 새벽) | 페르소나 1,000명 × `hermes-4-405b` 단일 = 응답 1,000건 | ✓ `hermes-4-405b` (③에서 std 0.89 — qwen3-max와 함께 공동 1위, Nous Research가 RLHF 균질화 압력을 의도적으로 약화한 연구소 라인업) | **박물관 관람료 유료화 도입 논쟁 시나리오**. 5질문(Likert 3 + 카테고리 1 + 자유서술 1)을 단일 모델 N=1,000으로 던져 페르소나 변동 폭만 본다. 본 저장소가 외부 공개로 진행한 첫 사례 |

본 라운드(⑤)에서 `hermes-4-405b` 단일 모델을 선택한 사유:

- ③에서 qwen3-max와 std 0.89로 공동 1위였으나 ④에서는 비용 부담 차원에서 `4-70b` 변종으로 시험했고, ⑤ 본 라운드는 405b의 큰 모델 크기에서 나오는 추론 깊이와 페르소나 변동 폭을 함께 보기 위해 큰 모델(`4-405b`)로 다시 돌아왔습니다.
- Nous Research의 Hermes 라인업은 RLHF 균질화 압력을 의도적으로 약화한 설계 — 친절·중립 압력을 낮춰 페르소나 서술을 평탄하게 만들지 않으려는 연구소 철학이 본 저장소의 페르소나 시뮬 목적과 정합합니다.
- 단일 모델로 던지는 것은 N=1,000 단면에서 페르소나 변동 폭을 깨끗하게 보기 위함이며, ④의 3종 다중 비교 형식은 후속 라운드에 다시 합류할 예정입니다.

사전 측정 없이 모델 1~2개로 곧바로 본 측정에 들어가면 모델 편향이 결과를 지배해 페르소나 시뮬의 의미가 사라집니다. 본 저장소는 ①~⑤ 차수의 후보·결정 흐름을 공개해 후속 연구·도메인 응용이 같은 함정에 빠지지 않도록 했습니다.

### 2. 한국 박물관·문화 도메인 첫 시도

본 저장소는 한국의 박물관·문화 분야에서 합성 페르소나 시뮬을 적용한 첫 공개 시도입니다. NVIDIA Nemotron-Personas-Korea의 한국 인구통계 분포(약 700만 페르소나 × 7개 narrative 컬럼)를 기반으로, 박물관·전시·문화재 시나리오에 대한 응답을 큐레이터의 가설 발생 도구로 변환합니다.

**외부 공개로 진행한 첫 사례는 박물관 관람료 유료화 도입 논쟁입니다** — 국립중앙박물관 관람료 유료화 논쟁이 격렬한 상황에서, 한국 인구통계 분포의 시민이 찬반 입장·지불 의향·취약계층 면제 조건·자유서술을 어떻게 응답하는지 ⑤단계 N=1,000 측정으로 살펴봅니다.

후속 시나리오 후보:

- 문화재 환수 의제(해외 한국 문화재 반환 우선순위)
- 전통 vs 현대 전시 콘셉트(같은 주제를 어느 어조로 풀어야 시민이 응답하는가)
- 야간개장·동행자별 관람 패턴(`preferred_companion` 차원 활용)

### 3. 결과 소개 페이지

원시 데이터(CSV·JSON)와 분석 코드는 본 저장소에 그대로 두고, 큐레이터·기획자가 결과를 빠르게 훑을 수 있도록 결과 소개 페이지를 GitHub Pages에 별도 배포합니다.

→ https://hoho0912.github.io/knowing-koreans-2k/

페이지는 Observable Framework 기반의 정적 사이트로, Python loader가 빌드 시점에 측정 산출물을 JSON으로 변환하고 브라우저에서는 D3 + Plot으로 차트를 렌더링합니다. 현재 페이지에서는 **본 라운드 N=1,000 단면**(박물관 관람료 유료화 도입 논쟁 시나리오, 응답 성공 998건) 한 건을 ①~⑧ 섹션 구조로 공개합니다. 1차 prototype 25건(전시 콘셉트 호감도 시나리오)은 도구 동작 확인용 사전 측정이라 본 저장소의 측정 라운드 표(아래)에 이력만 남겨 두고, 결과 소개 페이지에는 노출하지 않습니다.

| 영역 | 내용 |
|---|---|
| ① 핵심 분포 | 질문별 응답 빈도 — Likert는 100% 누적 막대 + 한국어 라벨, 옵션 선택형은 lollipop, 자유서술은 키워드 매칭 빈도 lollipop |
| ② 교차분석 | 페르소나 demographic 축(연령·성별·수도권·학력·17개 시도·직업 top 12)별 핵심 응답 분포 — 그룹 내 비율 100% 누적 막대 |
| ③ 분석 표 | 보고서 합성 LLM이 응답 schema와 raw 응답을 보고 표 종류·축·집계 방식을 자율 결정한 분석 표 (측정마다 표 구성이 달라짐) |
| ④ 발견 패턴 | 보고서 합성 LLM이 valid 응답 + cluster 분석 + cross-cluster diff + synthesis 단계로 도출한 패턴 (전체 분포 / ambivalence / 대안 우선 합의 / 연령·학력·지역 nuance / narrative 부정합 / 약신호 등) |
| ⑤ 곱씹을 만한 응답 | valid 응답 중 큐레이터에게 의미 있는 인용 3건 + 큐레이션 활용 노트 |
| ⑥ 응답 카드 | 핵심 응답 1~5 각 구간에서 valid 응답 최대 6건씩 시드 고정 샘플 (Q 응답 필터 인터랙션 포함, 자유서술은 240자 컷) |
| ⑦ 큐레이터 가설 | 발견 패턴을 큐레이터 도메인 어조로 옮긴 가설 후보 (타깃 그룹·전달 형식·메시지 본문 3차원) |
| ⑧ 다음에 던져볼 질문 | 본 라운드 약신호와 모델 편향 의심 패턴을 후속 시나리오 질문으로 옮긴 큐레이터용 work item |

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
| `HF_TOKEN` | Hugging Face | 선택 — Nemotron 데이터셋은 공개라 필수가 아니지만, rate limit 회피용으로 권장합니다 |
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

본 저장소는 두 가지 시나리오 운영 방식을 제공합니다. 도메인을 새로 만들 때는 둘 중 어느 path로 갈지 먼저 결정하세요.

| Path | 진입점 | 시나리오 정의 위치 | 새 도메인 추가 비용 |
|---|---|---|---|
| **A. spec.json 기반 (권장)** | `run_worker.py` (또는 `gateway.py`) | `spec.json`의 `ctx` / `questions` / `schema_block` 필드 | 코드 수정 없음 — JSON만 작성 |
| **B. scenarios/ 디렉토리 기반 (prototype)** | `run_scenario.py` | `scenarios/<id>/context.md` + `question.md` + `viz.py` | `prompt_builder.py` `USER_TEMPLATE` 수정 동반 — exhibition 5질문 형식에 고정 |

**Path A가 권장**입니다. `spec.json`에 응답 컨텍스트·질문·스키마를 직접 작성하면 LLM 호출·결과 누적·보고서 합성까지 자동 진행되며 신규 도메인은 코드 수정 없이 추가됩니다. 본 README의 "본격 측정" 섹션이 path A 흐름입니다.

**Path B**는 본 저장소 첫 prototype인 `exhibition_appeal` 시나리오의 흐름을 보존한 것으로, [prompt_builder.py:71](backend/prompt_builder.py:71) `USER_TEMPLATE`이 `appeal_score`/`visit_intent`/`key_attraction`/`key_concern`/`reason` 5개 응답 키에 고정되어 있어 새 도메인을 추가하려면 코드도 함께 수정해야 합니다. `validate_prompt_schema()`는 path B에서 `question.md` ↔ `USER_TEMPLATE` drift만 검증하며, path A에는 적용되지 않습니다.

아래 디렉토리 구조와 `context.md`·`question.md` 작성 원칙은 **path B (scenarios/) 한정**입니다. path A를 쓰는 분은 ["본격 측정"](#본격-측정--보고서인포그래픽까지) 섹션의 `spec.json` 양식만 따라가시면 됩니다.

### 디렉토리 구조 (path B)

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
- 응답 JSON 스키마를 같은 파일에 명시. 본 저장소의 `scenarios/exhibition_appeal/question.md`가 5항목 응답 (`appeal_score` / `visit_intent` / `key_attraction` / `key_concern` / `reason`) 예시입니다.
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
  "run_id": "20260501-002643-8c5981",
  "owner": "kk1",
  "created_at": "2026-05-01T00:26:43.510592",
  "topic": "측정 주제 (한 줄 요약)",
  "ctx": "응답자에게 제공할 배경 컨텍스트 본문",
  "questions": "1) 첫 질문\n2) 두 번째 질문\n3) ...",
  "schema_block": "{\n  \"q1_key\": {\"type\": \"integer\", \"scale\": \"1~5 Likert\", \"description\": \"...\"},\n  \"q2_key\": {\"type\": \"string\", \"options\": [\"...\"], \"description\": \"...\"}\n}",
  "qgen_model": "openrouter/anthropic/claude-sonnet-4.6",
  "report_model": "openrouter/anthropic/claude-opus-4.7",
  "n": 100,
  "seed": 42,
  "filters": {},
  "models": [
    "openrouter/anthropic/claude-3.5-haiku",
    "openrouter/openai/gpt-4o-mini",
    "openrouter/x-ai/grok-4-fast"
  ]
}
```

필수 키는 `run_id`, `n`, `models`입니다. 나머지는 선택이지만 `topic`·`ctx`·`questions`·`schema_block`이 비어 있으면 응답 LLM에 전달할 컨텍스트와 형식 검증이 부실해집니다. `created_at`은 ISO 8601 형식, `seed`는 양의 정수, `filters`는 페르소나 demographic 필터 dict입니다 (예: `{"province": "서울"}`).

### 실행

```bash
mkdir -p backend/results/run_2026-05-01_my_scenario
# 위 양식대로 spec.json 작성 후
python -m backend.run_worker backend/results/run_2026-05-01_my_scenario
```

진행률은 `status.json`을 폴링해 확인합니다 (gateway.py가 그 역할을 담당합니다).

### 보고서 산출물 구조

`report.md` / `report.pdf`의 기본 양식은 다음 4섹션입니다.

1. **개요** — 시나리오 헤더 + 페르소나 인구통계 인포그래픽 (D 차트: 성별·연령 분포 / E 차트: 지역·교육·직업 / F 차트: 핵심 응답 axis 분포)
2. **핵심 발견** — 분석 LLM이 추출한 패턴 3~5개 (응답 항목 간 ambivalence 포함)
3. **axis별 분포** — 페르소나 axis × 응답 항목의 결정론 통계 표
4. **곱씹을 만한 응답 + 다음 던져볼 질문** — 큐레이터가 후속 시나리오를 짜는 데 쓰도록 의도된 자유서술

응답 ≥ 약 900건이 되면 `run_worker.py`가 cluster 분할 + cross-cluster diff + synthesis의 다단 합성 모드(B)로 자동 분기하므로, 본문은 이보다 풍부한 구조(측정 개요·한눈에 보기 차트·핵심 발견·큐레이터 관점·축별 분포 세부·곱씹을 만한 응답·다음 질문·부록 등)로 합성됩니다. 본 저장소가 공개한 ⑤단계 N=1,000 보고서가 이 모드 B 산출물입니다.

---

## 분석용 LLM 선택

응답을 받은 뒤 패턴 추출에 쓰는 "분석 LLM"은 측정용과 분리되어 있습니다 (`spec.json`의 `report_model` 필드).

- 본 저장소 default 권장: 1M context · 강한 추론을 가진 하이엔드 모델 (예: Anthropic Claude Opus 4.7 1M, Google Gemini 2.5 Pro 1M, xAI Grok 4 등). 페르소나 narrative 전수 + 응답 raw 전수를 한 번에 시야에 둘 수 있어, 응답 항목 간 ambivalence·자유서술 의미·페르소나↔응답 정합성을 모두 봅니다.
- 응답 ≤ 600건 영역에서는 단일 호출이 가능합니다. 응답 > 900건 영역에서는 `run_worker.py`가 자동으로 cluster 분할 + cross-cluster diff + synthesis의 다단 호출 모드(B)로 분기합니다.
- 비용 절감이 우선이면 `report_model`을 더 가벼운 모델로 교체할 수 있습니다 — 다만 ambivalence 해석 품질이 떨어질 수 있다는 점은 감안해 주세요.

---

## Streamlit 게이트웨이 (`gateway.py`)

`gateway.py`는 측정 의뢰·진행률·산출물 다운로드를 위한 Streamlit UI입니다. **현재 비밀번호 인증이 켜져 있어 외부 연구자는 곧바로 동작하지 않습니다** — 본인 환경에서 쓰려면:

1. 사용자 본인의 `.creds-kk.json`을 만들거나 (양식: `{"<id>": "<bcrypt_hash>"}` — 최상위 dict, `id` 키로 직접 조회. 해시 생성: `python -c "import bcrypt; print(bcrypt.hashpw(b'<pw>', bcrypt.gensalt()).decode())"`)
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

- **LLM 균질화·고정관념** — 페르소나 narrative가 같아도 모델은 평균치로 수렴하는 경향이 있습니다. 다중 모델 비교로 모델별 편향 패턴을 노출합니다.
- **Social desirability bias** — LLM은 사회적으로 적절한 답을 선호합니다. 자유서술이 모델별로 비슷해질 위험이 있습니다.
- **Nemotron 페르소나의 도메인 깊이 부족** — 박물관·문화 영역의 prefer 컬럼은 합성에 한계가 있습니다. 본 저장소는 시나리오 `context.md`에 도메인 1차 자료를 grounding해 이를 보완합니다.
- **시간·문화 일반화 한계** — 시점 컨텍스트(`context_snapshot`)로 한정합니다.
- **여론 예측 도구가 아님** — 이 점은 보고서 본문에서도 명시합니다 (`disclaimer` 섹션).

---

## 기여

- 이슈는 GitHub Issues로 받습니다 — 버그 리포트에는 가능하면 `spec.json` + `status.json`을 함께 첨부해 주세요.

---

## 인용

본 저장소나 산출물을 학술·실무에 인용하실 때 다음 양식을 사용해 주세요.

```
Hosan Kim(2026). knowing-koreans: a synthetic-persona × multi-LLM
hypothesis generator for Korean curators.
https://github.com/hoho0912/knowing-koreans-2k
```

Nemotron-Personas-Korea 데이터셋 인용은 NVIDIA 측 안내를 따라 별도로 표기해 주세요.

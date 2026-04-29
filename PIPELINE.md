# knowing-koreans — PIPELINE

## 파이프라인 흐름 (도메인 무관 인프라)

```
[1] 페르소나 샘플링      [2] 컨텍스트 합성        [3] LLM 호출         [4] 결과 저장        [5] 시각화
─────────────────       ──────────────         ────────────         ────────────         ────────
Nemotron-Personas-      scenario/context.md    OpenAI / Ollama /    backend/results/      stlite +
Korea (parquet 9샤드)   + scenario/question    OpenRouter            *.csv (누적)         Plotly
       ↓                       ↓                     ↓                    ↓                  ↓
   N명 샘플링          페르소나 + 시나리오        JSON 응답            CSV 1행 +          정적 site
  (시드 고정)          → 단일 프롬프트         (vote/reason 등)      raw JSON 1파일       (frontend/)
```

## 단계별 상세

### [1] 페르소나 샘플링 — `backend/persona_sampler.py`

| 항목 | 값 |
|------|---|
| 입력 | Nemotron-Personas-Korea 데이터셋 (parquet 9샤드, ~3GB), N (샘플 수), seed |
| 출력 | List[PersonaRecord] — Nemotron 26 필드 + persona_uuid |
| 도구 | huggingface_hub, pyarrow, pandas |
| 비용 | 0 (1회 다운로드 후 로컬 캐시) |
| 검증 | 샘플 수 = N, persona_uuid 중복 없음, demographic 분포가 모집단과 χ² 비교 |

### [2] 컨텍스트 합성 — `backend/prompt_builder.py`

| 항목 | 값 |
|------|---|
| 입력 | 페르소나 1건, 시나리오 폴더(`scenarios/<scenario_id>/`) |
| 출력 | LLM에 보낼 단일 프롬프트(system + user) + 응답 JSON 스키마 |
| 구성 | (a) 페르소나 narrative들을 system 메시지로, (b) `context.md` 본문, (c) `question.md`의 질문, (d) JSON 스키마 |
| 규칙 | context.md는 수치·출처 제거된 중립 톤 (vuski 패턴 차용) |
| 검증 | 프롬프트 길이 < 모델 컨텍스트 윈도우, 모든 placeholder 치환 완료 |

### [3] LLM 호출 — `backend/llm_runner.py`

| 항목 | 값 |
|------|---|
| 입력 | 프롬프트, 모델 식별자 (예: `openai/gpt-5.5`, `openrouter/anthropic/claude-sonnet-4-6`, `ollama/exaone4.0:32b`) |
| 출력 | 응답 raw JSON + elapsed_sec |
| 라우팅 | `openai/*` → OpenAI SDK / `openrouter/*` → OpenRouter HTTPS / `ollama/*` → 로컬 Ollama |
| 파라미터 | temperature=0.7 (vuski 기본값 차용), JSON 모드 |
| 비용 추적 | 모델·토큰·달러 환산 → API_COSTS.md 갱신 |
| 검증 | JSON 파싱 성공, 필수 필드 존재 (vote/reason 등 — 시나리오별 스키마) |

### [4] 결과 저장 — `backend/results_writer.py`

| 항목 | 값 |
|------|---|
| 입력 | 페르소나 + 모델 + 응답 + elapsed_sec |
| 출력 | `backend/results/<scenario_id>_<context_snapshot>.csv` 한 행 추가 + `backend/response/<persona_uuid>_<model>_<timestamp>.json` raw 1건 |
| 스키마 | persona_uuid, model, scenario_id, context_snapshot_id, response_field_1, response_field_2, ..., reason, elapsed_sec, timestamp + 페르소나 26 필드 |
| 검증 | CSV 행이 추가되었는지, raw JSON 파일이 저장되었는지, persona_uuid 중복 시 별도 row로 누적 (시드별 반복 시뮬 허용) |

### [5] 시각화 — `frontend/index.html` (stlite + Plotly)

| 항목 | 값 |
|------|---|
| 입력 | `frontend/data/<scenario_id>_*.csv` (backend에서 복사) + `frontend/scenarios/<scenario_id>/context.md` |
| 출력 | 정적 웹페이지 (vuski 패턴: 메트릭 4개 + 모델 비교 + 인구통계 교차분석 + 응답 카드) |
| 박물관 추가 | 시나리오 셀렉터, 다양성 지표(같은 demographic 내 응답 분산), 시계열 비교(M4부터) |
| 호스팅 | GitHub Pages |
| 검증 | 브라우저에서 직접 열어 차트 렌더링·필터 동작 확인 (research-verify #5) |

## 시나리오 플러그인 구조

`scenarios/<scenario_id>/` 아래에 3파일:

| 파일 | 역할 |
|------|------|
| `context.md` | LLM 주입용 컨텍스트 (수치·출처 제거, 중립) |
| `question.md` | 질문 + 응답 JSON 스키마 |
| `viz.py` | 시각화 차원 정의 (어떤 컬럼으로 쪼갤지, 색상 매핑 등) |

선택적으로:
- `research_notes.md` (출처·수치 보존, LLM에 안 보냄)
- `assets/` (도록 PDF·이미지 등 1차 자료)

## 비용 사전 추정 (M1)

전시 콘셉트 호감도 첫 시나리오 100명 시뮬 기준 (모델 4종 가정):

| 모델 | 단위 비용 | 100명 × 1회 추정 |
|------|----------|----------------|
| OpenAI GPT-5.5 | (확인 필요) | ~$1~3 |
| OpenAI GPT-5.4-mini | (확인 필요) | ~$0.1~0.3 |
| OpenRouter Sonnet 4.6 | (확인 필요) | ~$1~5 |
| Ollama EXAONE 4.0 32B | 0 (로컬) | 0 |

→ 정확한 단위 비용은 API_COSTS.md에서 갱신. 처음에는 모델 1~2개로 시작해 비용 통제.

## 범위 대조 점검 (이 PIPELINE이 빠뜨린 것)

- 캐싱 / 재시도 / rate limit 처리는 M1 골격 단계에서 최소화. M2~M3에서 보강.
- 페르소나 sampling의 demographic 가중치(층화 표집)는 M3 Stage 2에서 도입.

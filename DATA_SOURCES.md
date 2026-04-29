# knowing-koreans — DATA_SOURCES

## 데이터 소스

| 출처 | 수집 방법 | 라이선스 | 검증 상태 | 비고 |
|------|----------|---------|----------|------|
| NVIDIA Nemotron-Personas-Korea | huggingface_hub.snapshot_download | CC BY 4.0 (상업 OK, 출처 표기 필요) | 데이터셋 공식 페이지 확인 (HTTP 200) | 1M demographic × 7 narrative = 7M, parquet 9샤드 ~3GB |
| OpenAI API | openai SDK | 유료 (사용량 기반) | API_COSTS.md 참조 | gpt-5.5 / gpt-5.4 / gpt-5.4-mini 등 |
| OpenRouter API | https://openrouter.ai/api/v1 | 유료 (모델별 단가) | API_COSTS.md 참조 | 다중 모델 fallback |
| Ollama 로컬 | Ollama daemon | 모델별 라이선스 (EXAONE NC 비상업, Qwen Apache 2.0, Gemma 자체 약관) | 로컬에서만 사용 | 사용자 PC GPU/RAM 의존 |

## Nemotron-Personas-Korea 스키마 (실제 26 필드, 2026-04-28 다운본 기준 검증)

> 데이터 규모: parquet 9샤드, **1,000,000행** (= 1M demographic records). 한 행당 페르소나 1명. CLAUDE.md/vuski의 "7M"는 행 수가 아니라 **7개 narrative 컬럼 × 1M = 개념적 곱셈**. 실제 시뮬은 행 단위.
> 라이선스: CC BY 4.0. HF 다운 시 토큰 미필요(공개).

### 식별자 (1)
- `uuid` — 페르소나 식별자 (Hex 32자, 고유). 우리 sampler는 추가로 `persona_uuid` 컬럼을 결정론적으로 생성·부여해 시드 간 충돌 방지.

### 인구통계 (12)
- `sex` — 성별 (예: "여자", "남자")
- `age` — 나이 (정수)
- `marital_status` — 혼인 상태 (예: "미혼", "배우자있음")
- `military_status` — 병역 상태 (예: "비현역", "현역") **★ 한국 특화, vuski에 없음**
- `family_type` — 가구 형태 (예: "1인 가구", "부모와 동거", "자녀와 거주 (배우자 별거)")
- `housing_type` — 주거 형태 (예: "아파트", "원룸", "다세대주택")
- `education_level` — 학력 (예: "중학교", "4년제 대학교")
- `bachelors_field` — 전공 (예: "사회학", "해당없음")
- `occupation` — 직업 (예: "건물 경비원", "유원시설 및 테마파크 서비스원")
- `province` — 시도 (예: "서울", "전라남", "경기")
- `district` — 시군구 (예: "서울-마포구", "전라남-여수시", "경기-안양시 만안구")
- `country` — 국가 (전부 "대한민국") **★ 추가 발견**

### 페르소나 narrative (13)
- `persona` — 한 문장 요약 (※ 우리 문서가 `persona_summary`로 적었던 필드의 실제 이름)
- `professional_persona` — 직업적 면모
- `family_persona` — 가족 면모
- `cultural_background` — 문화적 배경
- `sports_persona` — 스포츠
- `arts_persona` — 예술 ★ (박물관·문화 시나리오에서 핵심 grounding 필드)
- `travel_persona` — 여행
- `culinary_persona` — 음식
- `hobbies_and_interests` — 관심사 (서술형)
- `hobbies_and_interests_list` — 관심사 리스트 (Python list, 4~5 항목) **★ 추가 발견**
- `skills_and_expertise` — 숙련·전문성 (서술형)
- `skills_and_expertise_list` — 숙련 리스트 (Python list, 4~5 항목) **★ 추가 발견**
- `career_goals_and_ambitions` — 목표·포부

> 출처: 실제 다운본의 `df.columns` 직접 확인 (2026-04-28). 이전 문서(vuski README + index.html DOM 추정)에는 일부 필드 누락·이름 차이가 있었으며 본 절은 실제 데이터셋 기준으로 정정됨.

## 시뮬 결과 DB 스키마 (CSV)

`backend/results/<scenario_id>_<context_snapshot>.csv` — 시나리오별·시점별로 분리.

### 공통 필드
- `persona_uuid` — 페르소나 식별자
- `model` — LLM 식별자 (예: `openai/gpt-5.5`)
- `scenario_id` — 시나리오 식별자 (예: `exhibition_appeal`)
- `context_snapshot_id` — 시점 컨텍스트 ID (예: `2026-04`)
- `seed` — 페르소나 샘플링 시드 (재현성)
- `elapsed_sec` — 응답 시간
- `timestamp` — 시뮬 실행 시각 (ISO 8601)
- `response_file` — raw JSON 파일명

### 페르소나 26 필드 (사본)
- 위 Nemotron 26필드를 그대로 복사 — 시각화에서 페르소나 정보를 별도 join 없이 바로 쓰기 위함 (vuski 패턴 차용)

### 시나리오별 응답 필드
- 시나리오마다 `question.md`의 응답 스키마에 따라 컬럼이 추가됨
- 첫 시나리오 `exhibition_appeal`의 경우 (예정):
  - `appeal_score` (1~5 호감도)
  - `visit_intent` (관람 의향, yes/maybe/no)
  - `key_attraction` (가장 끌리는 요소, free text)
  - `key_concern` (걱정·이유, free text)
  - `reason` (전체 사유, free text)

## 시나리오별 1차 자료 (사용자가 가진 것)

### exhibition_appeal (전시 콘셉트 호감도)
- 필요: 가상 전시 기획안 또는 기존 전시 도록 1~2건
- 위치: `scenarios/exhibition_appeal/assets/` (사용자 제공 후 추가)
- 가공: 도록 → context.md 본문으로 요약·중립화 (수치·평가 표현 제거)

### (M3 이후 추가될 시나리오 — placeholder)
- 관람료 정책 → 박물관·문체부 보도자료
- 문화재 환수 → 환수 관련 보도·박물관 입장문·학계 논의
- 전통 vs 현대 → 전시 평론·비평지·SNS 반응 모음
- 지역 박물관 인지도 → 지역별 관람률 통계 + 박물관 명단

## 검증 기준 (research-verify 적용)

- 페르소나 샘플링: seed 고정 + N건 정확히 추출 (랜덤 패딩 금지)
- 응답 저장: raw JSON 1건당 별도 파일 + CSV 1행 매칭 (1:1)
- 결과 검증: appeal_score 등 응답 필드의 값이 스키마 범위 내인지 (1~5 외 값 거부)
- 균질성 체크: 같은 demographic 그룹의 응답 분산 — 0에 가까우면 stereotyping 경고

## 수집 이력 (작업일지에 기록, 여기서는 요약)

- 2026-04-28: 프로젝트 시작, 데이터셋 미다운로드 상태
- (다운로드 후 일자·샘플 수·시드 기록 예정)

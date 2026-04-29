# knowing-koreans — CLAUDE.md

## 프로젝트 개요

한국 인구통계 분포를 반영한 합성 페르소나(NVIDIA Nemotron-Personas-Korea, 700만)에 박물관·문화 시나리오를 던져 다중 LLM이 어떻게 응답하는지 시각화하는 정적 웹 시뮬레이터.

**포지셔닝**: 정확도 예측 도구가 아니라 **큐레이터를 위한 관점·가설 발생기**. "Models aren't polls" 비판을 우회하기 위해 처음부터 "perspective-taking 도구"로 정의한다.

**참고 프로젝트**: vuski/persona-million (정치 분야 시연). 동일 방법론을 박물관·문화 분야로 옮기되, 컨텍스트 설계와 시나리오 모듈화에서 차별점.

## 아키텍처 (4축)

### 축 1 — 도메인 무관 인프라 + 시나리오 플러그인

```
인프라 (도메인 무관)
페르소나 샘플러 → LLM 호출기 → 결과 DB → 시각화 엔진
     ↑              ↑           ↑          ↑
[Nemotron]    [OpenRouter+    [DuckDB    [stlite +
[+ Stage2/3   OpenAI+Ollama]  /SQLite]   Plotly]
 grounding]
                ↑
       시나리오 플러그인 (각각 context.md / question.md / viz.py 3파일)
       └── exhibition_appeal/  ← 첫 시나리오
       └── (관람료 정책 / 문화재 환수 / 전통vs현대 등 — 추후 추가)
```

### 축 2 — 컨텍스트 설계 (차별점)

vuski는 voter_context.md를 "Claude Code 웹 리서치 초안 수준"이라고 자기 한계로 인정. 우리는 큐레이터(Hosan)의 1차 자료를 컨텍스트 grounding으로 사용한다. 각 시나리오마다 두 파일 분리:

- `*_context.md` — LLM 주입용 (수치·출처 제거, 중립 톤)
- `*_research_notes.md` — 출처·수치 보존 (큐레이터 자료용)

### 축 3 — 페르소나 깊이 단계화 (Stanford 1052 흐름 일부 차용)

- **Stage 1**: Nemotron narrative 7종 그대로 (vuski 수준, 즉시 시작)
- **Stage 2**: 박물관 도메인 prefer 추가 (관람 빈도·선호 장르 등 합성)
- **Stage 3**: 실제 관람객 인터뷰·후기 grounding (옵션, 야심 단계)

### 축 4 — 시계열 누적

각 응답에 `context_snapshot_id` + `timestamp` 메타. 같은 시나리오를 시점별 컨텍스트로 반복 시뮬해 "전시 개막 전·후 반응 차이" 같은 분석. 야심 단계: 페르소나가 자기 이전 응답을 컨텍스트로 참조하면 에이전트 기반 시뮬로 확장 (vuski 본인 제안).

## 폴더 구조

```
projects/knowing-koreans/
├── CLAUDE.md                  ← 본 문서
├── 작업일지.md                  ← 진행 기록
├── ROADMAP.md                  ← 마일스톤 M1~M5
├── PIPELINE.md                 ← 단계별 입출력
├── DATA_SOURCES.md             ← 페르소나 + 시나리오 1차 자료 + DB 스키마
├── API_COSTS.md                ← OpenAI/OpenRouter 비용 추적
├── .env.example                ← 환경변수 템플릿
├── .server-logs/
│   └── knowing-koreans-server.md   ← GitHub 정보·PAT 일지 (server-deploy 패턴)
├── backend/                    ← Python 파이프라인 (페르소나 샘플 → LLM → CSV)
├── frontend/                   ← stlite 정적 사이트 (index.html + 차트)
└── scenarios/
    └── exhibition_appeal/      ← 첫 시나리오: 전시 콘셉트 호감도
        ├── context.md          ← LLM에 주입할 박물관/전시 컨텍스트
        ├── question.md         ← 질문 + 응답 JSON 스키마
        └── viz.py              ← 시각화 차원 정의 (skeleton)
```

## 작업 규칙

### 데이터 수집·시뮬 (research-verify 적용)
- 페르소나 샘플링은 매번 시드 고정 + 시드값을 결과 CSV에 기록
- LLM 응답은 raw JSON으로 1건당 별도 파일 보존 (vuski 패턴)
- 누적 CSV는 `backend/results/` 아래에 시나리오별로 분리
- 추측·창작으로 페르소나 필드를 채우지 않음 — Nemotron 원본 필드 그대로

### 컨텍스트 작성 규칙
- LLM 주입용 `*_context.md`에는 여론조사·통계 수치 제외 (앵커링 방지)
- 출처·수치는 `*_research_notes.md`에만 보존
- 중립 톤 — 정책 옹호·반대 표현 회피
- 시점 메타데이터 헤더 필수 (`# 시점: YYYY-MM`)

### 코드 수정·배포 규칙 (server-deploy 패턴 일부 차용)
- 배포는 GitHub Pages 정적 호스팅. server-deploy 스킬의 원격 Ubuntu 절차는 적용 안 함
- GitHub PAT 관리는 `.server-logs/knowing-koreans-server.md` 패턴 따름
- Cowork VM의 FUSE git 제약 발생 시 server-deploy 스킬의 `/tmp` GIT_DIR 우회법 사용

## 비용 / 외부 서비스
- 유료 API: OpenAI(직접) + OpenRouter(다중 모델)
- 무료: Ollama 로컬 (사용자 PC GPU/RAM 사용)
- 데이터셋: NVIDIA Nemotron-Personas-Korea (CC BY 4.0, 무료, ~3GB)
→ 상세는 API_COSTS.md

## 배포 (GitHub Pages)

- 리포: hoho0912/knowing-koreans (예정, 새 리포 생성 필요)
- URL: https://hoho0912.github.io/knowing-koreans/
- 빌드: `frontend/index.html` + `frontend/data/*.csv` + `frontend/scenarios/*/context.md` 정적 호스팅
- 데이터 갱신: 로컬에서 backend 실행 → 결과 CSV를 frontend/data/로 복사 → git push
- (선택) GitHub Actions로 정기 갱신 자동화 — M3~M4에서 검토

## 알려진 한계 (설계 단계 인지)
- LLM 균질화·고정관념 — 시각화에서 "다양성 지표" 별도 노출로 우회
- Social desirability bias — 다중 모델 비교로 모델별 편향 패턴 노출
- Nemotron 페르소나의 박물관 도메인 깊이 부족 — Stage 2/3에서 보강
- 시간·문화 일반화 한계 — 시점 컨텍스트 명시로 한정

## 관련 문서
- 작업일지.md — 진행 기록
- ROADMAP.md — M1~M5 마일스톤
- PIPELINE.md — 단계별 입출력
- DATA_SOURCES.md — 데이터 출처 + DB 스키마
- API_COSTS.md — 외부 API 비용
- .server-logs/knowing-koreans-server.md — GitHub·PAT·배포 일지

## 사전 리서치 자료 (Work 루트)
- `research_persona_simulation_trends_2026-04-28.md` — vuski 분석 + 트렌드 보고서

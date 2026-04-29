# knowing-koreans — ROADMAP

## 마일스톤

| # | 목표 | 예상 기간 | 상태 |
|---|------|----------|------|
| M1 | 인프라 골격 + 첫 시나리오 시뮬 | 1~2주 | 미시작 |
| M2 | stlite 정적 사이트 배포 | 1~2주 | 미시작 |
| M3 | 시나리오 2~3개 추가 + 모듈화 정리 + Stage 2 페르소나 | 2~4주 | 미시작 |
| M4 | 시계열 누적 + Stage 3 페르소나 grounding | 1~2개월 | 미시작 |
| M5 | 에이전트 기반 시뮬 (페르소나 본인 시계열 응답 참조) | 야심 단계 | 미시작 |

## M1 — 인프라 골격 + 첫 시나리오

**산출물**
- backend/persona_sampler.py — Nemotron parquet 9샤드 로드 + 시드 고정 샘플링
- backend/llm_runner.py — OpenAI / OpenRouter / Ollama 통합 호출
- backend/run_scenario.py — 시나리오 디렉토리 받아 N명 시뮬 실행
- scenarios/exhibition_appeal/{context,question}.md 1차 작성 완료
- backend/results/exhibition_appeal_2026-04.csv — 30~100건 시뮬 결과

**선행 필요 (사용자)**
- HF Token (선택, 모델 자체는 공개라 미필요할 수 있음)
- OpenAI API Key
- OpenRouter API Key
- 첫 시나리오 1차 자료 (가상 전시 기획안 또는 기존 도록 1~2건)

## M2 — stlite 정적 사이트

**산출물**
- frontend/index.html — vuski 패턴 (stlite 0.85.x + Plotly)
- frontend/data/exhibition_appeal_2026-04.csv 게시
- frontend/scenarios/exhibition_appeal/context.md 노출용 사본
- 시나리오 셀렉터 UI (드롭다운 또는 탭, 단일 시나리오라도 미리 구조 잡음)
- GitHub Pages 활성화 + 첫 배포

## M3 — 시나리오 2~3개 추가 + 페르소나 깊이 Stage 2

**시나리오 후보**
- 관람료·휴관일·디지털화 정책 수용성
- 특정 문화재 환수·반환 이슈 인식
- 한국 전통 vs 현대미술 선호 분포
- 지역 박물관 인지도·접근성

**Stage 2 페르소나**
- Nemotron 원본 + 박물관 관련 합성 필드 추가 (관람 빈도, 선호 장르, 지난 1년 관람 경험 등)
- 합성 규칙은 한국 통계청 문화예술관람률 통계와 정합성 유지

**모듈화 정리**
- 시나리오 추가가 코드 수정 없이 가능하도록 구조 정착
- 외부 큐레이터·기관이 자기 시나리오 끼워 쓸 수 있는 README 작성

## M4 — 시계열 누적 + Stage 3 grounding

**시계열**
- context_snapshot_id 도입, 시점별 컨텍스트 archive
- 같은 시나리오·같은 페르소나를 여러 snapshot으로 반복 시뮬
- 시점 비교 차트 추가

**Stage 3 (옵션, 큐레이터 자료 있을 때)**
- 실제 관람객 인터뷰·후기를 페르소나에 grounding으로 주입
- Stanford 1052 흐름 차용

## M5 — 에이전트 기반 시뮬 (야심)

- 페르소나가 자기 이전 응답을 컨텍스트로 참조하는 구조
- 시뮬 결과가 다음 시뮬의 입력이 되는 시계열 체인
- vuski 본인이 Threads에서 제안한 방향

## 우선순위 메모

- M1·M2는 "vuski 수준 + 박물관 도메인" 시연. 외부에 보여줄 수 있는 수준.
- M3가 진짜 차별점 발화 — 시나리오 모듈화 + Stage 2 페르소나가 vuski에 없는 부분.
- M4·M5는 학술 논문 가능성도 있는 야심. M1~M3 완료 후 결정.

## 범위 대조 점검 (이 ROADMAP가 빠뜨린 것 / 우회한 것)

- (현 시점 빠진 것 없음 — 사용자와 합의된 4축이 모두 마일스톤에 매핑됨)
- M1~M3까지 완료되어야 "knowing-koreans는 외부 공유 가능"이라고 보고 가능

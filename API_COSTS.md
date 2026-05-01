# knowing-koreans — API 비용 / 외부 서비스

## 외부 API 목록

| 서비스 | 용도 | 과금 방식 | 현재 잔액/한도 | 키 발급 위치 |
|--------|------|----------|--------------|-------------|
| OpenAI | gpt-5.5 / gpt-5.4 / gpt-5.4-mini 호출 | 토큰당 (input/output 분리) | 확인 필요 | https://platform.openai.com/api-keys |
| OpenRouter | 다중 모델 fallback (Anthropic / Google / Mistral 등) | 모델별 단가 | 확인 필요 | https://openrouter.ai/keys |
| Hugging Face | Nemotron 데이터셋 다운로드 (선택, 공개 dataset이라 비필수) | 무료 (Token 선택) | — | https://huggingface.co/settings/tokens |
| Ollama | 로컬 모델 실행 | 무료 (로컬 GPU/RAM 사용) | — | 로컬 설치 |

## 비용 통제 원칙

1. **드라이런 먼저** — 프롬프트가 정상 빌드되는지 1건만 실제 호출, 나머지는 mock으로 검증
2. **모델 1~2개로 시작** — M1 첫 시뮬은 gpt-5.4-mini + Ollama EXAONE 정도로 시작. 여러 모델 비교는 M2~M3에서
3. **temperature=0.7** 기본. 결정적 결과 필요하면 0
4. **응답 길이 제한** — 사유(reason)는 200~400자 정도로 제한해 토큰 통제
5. **batch는 작게 시작** — 5명 → 결과 확인 → 30명 → 100명 단계적 확장

## 모델별 단가 (확인 필요 — 사용 직전 공식 페이지 재확인)

| 모델 | input ($/1M tok) | output ($/1M tok) | 출처 |
|------|----------------|------------------|------|
| OpenAI gpt-5.5 | 확인 필요 | 확인 필요 | OpenAI Pricing |
| OpenAI gpt-5.4 | 확인 필요 | 확인 필요 | OpenAI Pricing |
| OpenAI gpt-5.4-mini | 확인 필요 | 확인 필요 | OpenAI Pricing |
| OpenRouter Anthropic claude-sonnet-4-6 | 확인 필요 | 확인 필요 | OpenRouter |
| OpenRouter Google gemini-3 | 확인 필요 | 확인 필요 | OpenRouter |
| Ollama (전부) | 0 | 0 | 로컬 |

> 단가는 모델 페이지에서 직접 확인 후 갱신. 추정값으로 채우지 않음.

## M1 첫 시뮬 비용 사전 견적 (대략)

가정: 시나리오 1개, 페르소나 100명, 모델 2종(OpenAI gpt-5.4-mini + Ollama EXAONE 4.0)

| 항목 | 추정 |
|------|------|
| OpenAI gpt-5.4-mini × 100건 | $0.1~0.5 (응답 길이 따라) |
| Ollama EXAONE × 100건 | $0 (로컬) |
| **소계** | **$0.5 미만** |

## 비용 추적 방식

- backend/llm_runner.py가 매 호출 후 token usage 로그를 남김
- 일자별·모델별 토큰·달러 합계를 backend/logs/cost_YYYY-MM.csv에 누적
- 본 문서의 "현재 잔액" 섹션을 주 1회 갱신 (수동)

## 비용 로그 (예정)

| 일자 | 시나리오 | 모델 | 호출 수 | input tok | output tok | 비용 ($) |
|------|---------|------|--------|-----------|-----------|---------|
| 2026-04-28 | (시작 전) | — | 0 | 0 | 0 | 0 |

> 첫 시뮬 실행 후 행 추가.

## 비용 알림 임계값

- 일 단위 $5 초과 시 대시보드에 경고
- 월 단위 $50 초과 시 사용자에게 보고 + 다음 단계 결정
- (M3 이후) 시나리오·모델별 cap 도입 검토

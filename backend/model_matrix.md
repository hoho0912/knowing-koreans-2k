# Model Matrix — 페르소나 신호 통과 검증용 후보 (2026-04-29 카탈로그 스캔)

> OpenRouter 카탈로그 371개 모델 + OpenAI 직접 호출 후보를 lab당 변종으로 정리. 슬롯 결정용 1차 자료.

## 슬롯 평가 4축

| 축 | 의미 |
|---|---|
| **Capacity** | flagship vs 경량 변종 페어가 같은 lab 안에서 capacity 효과 분리 가능한가 |
| **RLHF 전통** | 페르소나 신호 통과 가설 4개(정중성 약함·system 권위·mode collapse 약함·demographic 추론) 검증에 기여 |
| **비용** | 본 측정 N=100 × M개 모델 예산 안에 들어오는가 |
| **신선도** | 출시 시점이 가설 검증 효과를 흐리지 않게 최신인가 |

비용 추정 기준: 단가 ~ in 2,500 token + out 200 token 가정 (smoke 측정 평균값 기반).

---

## Anthropic (RLHF 정중성·강한 default voice 가설)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 / smoke 결과 |
|---|---|---|---|---|
| anthropic/claude-sonnet-4.6 | 3 / 15 | 1M | ~5,700원 | **smoke std=0.45** (Haiku 못 넘음) |
| anthropic/claude-haiku-4.5 | 1 / 5 | 200K | ~1,900원 | **baseline std=0.75 (A+B 100명)** |

**측정된 결과(오전 smoke + 본 측정)**: haiku-4.5 std=0.75가 sonnet-4.6 std=0.45보다 높음. "같은 lab에서 capacity 올려도 페르소나 sensitivity 안 따라옴" 가설이 부분 시사됐으나 N=5 noise 가능성.

**미결정 (사용자 결정 필요)**: opus 변종(4.5/4.6/4.7)을 capacity 천장 검증용으로 추가할지. 오전 smoke에 미포함 — 추가하려면 별도 합의 + 비용 추가.

---

## DeepSeek (신생 lab·RLHF 전통 다름 — 신선도 우위)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 / smoke 결과 |
|---|---|---|---|---|
| deepseek/deepseek-v4-pro | 0.435 / 0.87 | 1M | ~600원 | smoke std=0.45, **응답 max 137.9초 속도 함정** |
| deepseek/deepseek-v4-flash | 0.14 / 0.28 | 1M | ~190원 | smoke std=0.55 |
| deepseek/deepseek-v3.2 | 0.252 / 0.378 | 131K | ~310원 | smoke std=0.00 **mode collapse — 무용** |
| deepseek/deepseek-v3.2-speciale | 0.4 / 1.2 | 163K | ~580원 | "speciale" — 변종, RLHF 다를 가능성 |
| deepseek/deepseek-v3.2-exp | 0.27 / 0.41 | 163K | ~330원 | exp 변종 |
| deepseek/deepseek-r1-0528 | 0.5 / 2.15 | 163K | ~720원 | r1 reasoning |
| deepseek/deepseek-r1 | 0.7 / 2.5 | 64K | ~1,000원 | reasoning |

**슬롯 추천**: deepseek-v4-flash (smoke std=0.55, 본 측정도 통과 가능 + 가장 저렴). v4-pro는 속도 함정으로 N=100에서 비효율(137초 × 100건 = ~4시간). v3.2 mode collapse는 본 측정 무용 → **드롭**.

---

## Qwen (한자권 RLHF 전통 — 변종 풍부, smoke 1순위지만 한 세대 전 모델 사용 의혹)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 / smoke 결과 |
|---|---|---|---|---|
| **qwen/qwen3-max** | 0.78 / 3.9 | 262K | ~1,650원 | **smoke std=0.89 (한 세대 전)** |
| qwen/qwen3-max-thinking | 0.78 / 3.9 | 262K | ~1,650원 | reasoning 변종 — 빌링 함정 가능 |
| **qwen/qwen3.6-max-preview** | 1.04 / 6.24 | 262K | ~2,500원 | **최신 flagship — Qwen 라인 천장** |
| qwen/qwen3.6-plus | 0.325 / 1.95 | 1M | ~750원 | mid tier |
| qwen/qwen3.6-flash | 0.25 / 1.5 | 1M | ~600원 | flash |
| qwen/qwen3.6-35b-a3b | 0.16 / 0.97 | 262K | ~370원 | MoE 35B |
| qwen/qwen3.6-27b | 0.325 / 3.25 | 256K | ~640원 | dense 27B |
| qwen/qwen3.5-plus-20260420 | 0.4 / 2.4 | 1M | ~900원 | 2026-04 출시 |
| qwen/qwen3.5-397b-a17b | 0.39 / 2.34 | 262K | ~880원 | MoE 397B |
| qwen/qwen3.5-122b-a10b | 0.26 / 2.08 | 262K | ~660원 | MoE 122B |
| qwen/qwen3.5-flash-02-23 | 0.065 / 0.26 | 1M | ~120원 | 2026-02 flash |

**슬롯 추천**: 사용자 지적 그대로 **qwen3-max → qwen3.6-max-preview로 교체** + qwen3.6-plus (capacity 비교) 또는 qwen3-max 재측정(N=100으로 noise 제거). 두 변종 동시 측정해서 "Qwen RLHF 전통 안에서 세대 효과" 분리 가능.

---

## Hermes / Nous Research (steerability 가설 — capacity 축 비교 가능)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 / smoke 결과 |
|---|---|---|---|---|
| **nousresearch/hermes-4-405b** | 1 / 3 | 131K | ~1,950원 | **smoke std=0.89 (capacity 효과 미분리)** |
| **nousresearch/hermes-4-70b** | 0.13 / 0.4 | 131K | ~250원 | **70B 경량 변종 — smoke 미측정** |
| nousresearch/hermes-3-llama-3.1-405b:free | 0 / 0 | 131K | 0원 | **무료** (구세대) |
| nousresearch/hermes-3-llama-3.1-405b | 1 / 1 | 131K | ~1,500원 | 구세대 |
| nousresearch/hermes-3-llama-3.1-70b | 0.3 / 0.3 | 131K | ~450원 | 구세대 70B |

**슬롯 추천**: hermes-4-405b 재측정 + **hermes-4-70b 추가** = "같은 RLHF 전통 안에서 capacity 효과 분리" 가능. 비용 차 약 7배인데 70B 측정값이 405B와 비슷하면 capacity가 std에 미치는 영향 작다는 신호.

---

## Mistral (유럽 RLHF 전통)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 / smoke 결과 |
|---|---|---|---|---|
| mistralai/mistral-large-2512 | 0.5 / 1.5 | 262K | ~720원 | smoke std=0.55 (2025-12 최신) |
| mistralai/mistral-large-2411 | 2 / 6 | 131K | ~3,000원 | 2024-11 |
| mistralai/mistral-large-2407 | 2 / 6 | 131K | ~3,000원 | 2024-07 |

**슬롯 추천**: mistral-large-2512 유지 (smoke std=0.55 통과 + 가장 저렴 + 최신). 구세대 비교는 capacity 외 RLHF 변화도 섞여 깔끔하지 않음 → 단일 변종.

---

## xAI Grok (smoke 미측정 — 슬롯 결정 필요)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 |
|---|---|---|---|---|
| x-ai/grok-4.20 | 2 / 6 | 2M | ~3,000원 | 최신 flagship |
| x-ai/grok-4.20-multi-agent | 2 / 6 | 2M | ~3,000원 | multi-agent 변종 |
| x-ai/grok-4-fast | 0.2 / 0.5 | 2M | ~280원 | fast |
| x-ai/grok-4.1-fast | 0.2 / 0.5 | 2M | ~280원 | fast 변종 |
| x-ai/grok-4 | 3 / 15 | 256K | ~5,700원 | base |
| x-ai/grok-3 | 3 / 15 | 131K | ~5,700원 | 구세대 |
| x-ai/grok-3-mini | 0.3 / 0.5 | 131K | ~330원 | mini |

**슬롯 결정 사유 후보**:
- (채택) Grok은 RLHF 전통이 다른 lab들과 또 달라 (xAI default voice "edgy"), 페르소나 신호 통과 가설에 새 변종을 추가하는 효과 — grok-4-fast 한 슬롯 추천 (저렴 + 최신)
- (드롭) capacity 7개 슬롯에서 Grok이 다른 카테고리(Hermes·Qwen)와 신호 통과 메커니즘 중복이라 차별성 약함

---

## Cohere (RAG 특화·기업 RLHF — smoke 미측정)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 |
|---|---|---|---|---|
| cohere/command-a | 2.5 / 10 | 256K | ~3,800원 | 최신 flagship |
| cohere/command-r-plus-08-2024 | 2.5 / 10 | 128K | ~3,800원 | r-plus |
| cohere/command-r-08-2024 | 0.15 / 0.6 | 128K | ~210원 | r 기본 |
| cohere/command-r7b-12-2024 | 0.0375 / 0.15 | 128K | ~55원 | 7B 경량 |

**슬롯 결정 사유 후보**:
- (채택) Cohere는 RAG/agent 특화 RLHF로 다른 lab과 또 다른 default voice — capacity 효과까지 함께 보려면 command-a + command-r 페어
- (드롭) 페르소나 시뮬은 RAG 미사용 컨텍스트라 Cohere 강점이 안 살고, default voice는 다른 lab과 비슷한 정중성으로 mode collapse 위험 큼

---

## EXAONE (LG AI — 한국어 RLHF)

OpenRouter 카탈로그에 미수록. Ollama 로컬 또는 Together AI 등 별도 게이트웨이 필요. 비상업 라이선스 제약(CLAUDE.md 명시) → **본 측정 제외 권장**.

---

## OpenAI (직접 호출 — RLHF 정중성 가설 baseline)

| 모델 ID | in/out ($/M) | ctx | 비용/100건 (KRW≈) | 비고 / smoke 결과 |
|---|---|---|---|---|
| openai/gpt-4o-mini | 0.15 / 0.6 (실측) | 128K | ~660원 | **baseline std=0.17 (A+B 100명)** |
| openai/gpt-5-mini | 1.1 / 4.4 | 128K | ~5,000원 | reasoning 빌링 84% — 비효율 |

**슬롯 추천**: gpt-4o-mini 유지(baseline 재측정 — 파이프라인 정합성). gpt-5-mini는 04-28 측정에서 빌링 함정 확인 → 드롭.

---

## 측정된 결과 요약 (오전 실측, 슬롯 결정 1차 자료)

### Baseline 4 모델 — N=100 본 측정 (`exhibition_appeal_2026-04-where-things-linger.csv`)

| # | 모델 | std | mean | elapsed mean | 비고 |
|---|---|---:|---:|---:|---|
| 1 | openai/gpt-4o-mini | **0.17** | 3.97 | 3.8s | mode collapse 근접 — 정중성 천장 |
| 2 | qwen/qwen-2.5-72b-instruct | **0.25** | 3.02 | 15.5s | mode collapse 근접 |
| 3 | google/gemini-2.5-flash | **0.43** | 2.80 | 2.5s | 중간 |
| 4 | anthropic/claude-haiku-4.5 | **0.75** | 2.48 | 5.1s | **페르소나 신호 통과 baseline** |

### Smoke 7 모델 — N=5 (`exhibition_appeal_2026-04-where-things-linger-smoke-models.csv`)

| # | 모델 | std | mean | elapsed mean | elapsed max | 신호 |
|---|---|---:|---:|---:|---:|---|
| 1 | nousresearch/hermes-4-405b | **0.89** | 2.6 | 5.9s | 7.2s | smoke 1위 |
| 2 | qwen/qwen3-max | **0.89** | 2.4 | 6.0s | 6.6s | smoke 1위, 한 세대 전 |
| 3 | mistralai/mistral-large-2512 | 0.55 | 2.6 | 8.5s | 12.0s | 통과 |
| 4 | deepseek/deepseek-v4-flash | 0.55 | 2.4 | 12.1s | 18.1s | 통과 |
| 5 | anthropic/claude-sonnet-4.6 | 0.45 | 2.2 | 10.4s | 13.0s | Haiku(0.75) 못 넘음 |
| 6 | deepseek/deepseek-v4-pro | 0.45 | 2.2 | 63.1s | **137.8s** | 속도 함정 |
| 7 | deepseek/deepseek-v3.2 | **0.00** | 2.0 | 14.3s | 37.1s | **mode collapse — 무용** |

---

## 오전 결론 (사용자 합의된 미결정 항목)

오전 사용자 옵션 B 채택: smoke 자체 신뢰도 낮음 → lab당 변종 매트릭스부터 다시 짠 뒤 N=100 진입.

**신뢰도 낮은 사유**:
1. **qwen3-max 한 세대 전** — qwen3.6 라인업 검토 안 됨
2. **hermes-4-405b만 측정, 4-70b 미측정** — capacity 비교 안 됨
3. **Cohere/Grok smoke 미측정** — 침묵 드롭됨

## 결정 필요 (사용자 합의 사항)

오전 결론 그대로 사용자 결정만 남은 항목:

1. **Qwen** — qwen3-max 재측정(N=100)? OR qwen3.6-max-preview/qwen3.6-plus로 교체? OR 둘 다 측정해서 세대 비교?
2. **Hermes** — hermes-4-405b 재측정만? OR hermes-4-70b 추가해서 capacity 비교?
3. **Cohere** — 채택(어느 변종)? OR 드롭(사유 명시)?
4. **Grok** — 채택(어느 변종)? OR 드롭(사유 명시)?
5. **Anthropic capacity 천장** — claude-sonnet-4.6은 smoke에서 Haiku 못 넘었음. opus 변종을 추가해서 "한 lab의 capacity 천장" 검증할지? (오전 미논의 — 사용자 결정 필요)
6. **context_snapshot_id** — `2026-04-where-things-linger-models-v2` 진행 OK?

자동 드롭(measurement-driven, 추가 합의 불요):
- deepseek-v3.2: std=0.00 mode collapse 확정 → 무용
- deepseek-v4-pro: 137초 속도 함정 → N=100 운영 부담

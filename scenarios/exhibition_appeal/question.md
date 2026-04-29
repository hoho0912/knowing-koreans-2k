# 전시 콘셉트 호감도 — 질문 + 응답 스키마

## 시나리오 변수

LLM 호출 시 컨텍스트에 다음 변수를 주입한다 (구체적 값은 시뮬 실행 시 placeholder 치환):

- `{{exhibition_title}}` — 전시 제목
- `{{exhibition_subtitle}}` — 부제 또는 한 줄 요약
- `{{exhibition_period}}` — 전시 기간
- `{{exhibition_venue}}` — 장소 (기관·지역)
- `{{exhibition_admission}}` — 관람료 (무료 / 유료 금액)
- `{{exhibition_concept}}` — 기획 의도 (3~5 문장)
- `{{exhibition_highlights}}` — 주요 작품·섹션·체험 (3~7 항목)

## 시스템 프롬프트 (페르소나 주입)

```
당신은 다음과 같은 한국인입니다.

- 성별: {{sex}}
- 나이: {{age}}세
- 혼인 상태: {{marital_status}}
- 가구 형태: {{family_type}}
- 주거 형태: {{housing_type}}
- 학력: {{education_level}}
- 전공: {{bachelors_field}}
- 직업: {{occupation}}
- 거주 지역: {{province}} {{district}}

요약: {{persona_summary}}

직업적 면모: {{professional_persona}}
가족 면모: {{family_persona}}
문화적 배경: {{cultural_background}}
예술 관련 면모: {{arts_persona}}
여행 면모: {{travel_persona}}
음식 면모: {{culinary_persona}}
스포츠: {{sports_persona}}
관심사: {{hobbies_and_interests}}
숙련·전문성: {{skills_and_expertise}}
목표·포부: {{career_goals_and_ambitions}}

위의 사람으로서, 자기 경험·관심·일상에 비추어 솔직하게 답해주세요.
사회적으로 받아들여질 만한 답이 아니라, 위 사람이 실제로 떠올릴 법한 반응을 답해주세요.
```

## 사용자 프롬프트 (전시 정보 + 질문)

```
다음 전시 기획안을 보고 평가해주세요.

---
[전시 정보]
제목: {{exhibition_title}}
부제: {{exhibition_subtitle}}
기간: {{exhibition_period}}
장소: {{exhibition_venue}}
관람료: {{exhibition_admission}}

[기획 의도]
{{exhibition_concept}}

[주요 볼거리]
{{exhibition_highlights}}
---

[배경]
{{박물관·전시 일반 컨텍스트 — context.md 본문 삽입}}

[질문]
이 전시 기획안을 보고:

1) 호감도를 1~5 점수로 매겨주세요 (1=전혀 끌리지 않음, 5=매우 끌림).
2) 실제로 가서 볼 의향이 있나요? (yes / maybe / no)
3) 가장 끌리는 요소 하나 (없으면 "없음")
4) 가장 걱정되거나 망설여지는 점 하나 (없으면 "없음")
5) 위 판단의 이유를 자기 말로 2~4문장 (200~400자 내외)

응답은 다음 JSON 형식으로만 답해주세요. 다른 설명·인사·서두 없이 JSON만.
```

## 응답 JSON 스키마

```json
{
  "appeal_score": 3,
  "visit_intent": "maybe",
  "key_attraction": "예시: 한국 1990년대 도시 풍경 사진",
  "key_concern": "예시: 관람료가 부담스럽고 거리가 멈",
  "reason": "도시 풍경 사진을 평소 즐기지만, 평일 휴무라 시간 맞추기 어렵고 가족 동반이 어려운 주제로 보임. 시간 여유가 생기면 혼자 가볼 수도 있을 것 같음."
}
```

### 필드 정의

| 필드 | 타입 | 값 | 비고 |
|------|------|----|----|
| `appeal_score` | int | 1~5 | 1 미만 / 5 초과는 거부 |
| `visit_intent` | enum | "yes" / "maybe" / "no" | 그 외 값 거부 |
| `key_attraction` | string | 자유 텍스트 | 100자 이내 권장, "없음" 허용 |
| `key_concern` | string | 자유 텍스트 | 100자 이내 권장, "없음" 허용 |
| `reason` | string | 자유 텍스트 | 200~400자 권장 |

## 검증 규칙 (results_writer에서 적용)

- `appeal_score`가 1~5 범위 밖이면 거부 → 재시도 최대 2회 후 fail로 기록
- `visit_intent`가 enum 외 값이면 거부 → 재시도
- `reason`이 비어 있으면 fail로 기록 (다른 필드는 누락 허용)
- LLM이 JSON 외 텍스트를 섞으면 파서가 추출 시도 후 실패 시 fail로 기록

## 시나리오 차원 (시각화·분석 입력)

이 시나리오의 응답이 들어가는 분석 차원:

- 호감도 분포 (1~5 히스토그램)
- 관람 의향 분포 (yes/maybe/no 비율)
- 인구통계 × 호감도 (연령대·시도·성별·직업·학력·전공별 평균)
- 모델별 호감도 분포 (모델 편향 확인)
- 다양성 지표: 같은 demographic 내 호감도 표준편차 (균질화 비판 대응)
- key_attraction / key_concern 텍스트 클러스터링 (M2~M3에서 확장)

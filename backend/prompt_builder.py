"""
프롬프트 빌더 — 페르소나 + 시나리오 → {system, user} 프롬프트 두 개

placeholder 형식: {{var_name}}
- 페르소나 필드는 system 프롬프트로 주입
- 시나리오 변수는 user 프롬프트로 주입
- context.md 본문은 user 프롬프트의 [배경] 섹션에 그대로 삽입
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Union

import pandas as pd

PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def render_template(template: str, values: Dict[str, Any]) -> str:
    """{{var}} placeholder를 values dict로 치환. 없는 키는 빈 문자열."""

    def replace(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key not in values:
            return ""
        v = values[key]
        return "" if v is None else str(v)

    return PLACEHOLDER_RE.sub(replace, template)


def persona_to_dict(persona: Union[pd.Series, Dict]) -> Dict[str, Any]:
    if isinstance(persona, pd.Series):
        return persona.to_dict()
    return dict(persona)


SYSTEM_TEMPLATE = """당신은 다음과 같은 한국인입니다.

- 성별: {{sex}}
- 나이: {{age}}세
- 혼인 상태: {{marital_status}}
- 병역 상태: {{military_status}}
- 가구 형태: {{family_type}}
- 주거 형태: {{housing_type}}
- 학력: {{education_level}}
- 전공: {{bachelors_field}}
- 직업: {{occupation}}
- 거주 지역: {{province}} {{district}}

요약: {{persona}}

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

위 사람으로서, 자기 경험·관심·일상에 비추어 솔직하게 답해주세요.
사회적으로 받아들여질 만한 답이 아니라, 위 사람이 실제로 떠올릴 법한 반응을 답해주세요.
"""


USER_TEMPLATE = """다음 전시 기획안을 보고 평가해주세요.

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
{{context_body}}

[질문]
이 전시 기획안을 보고:

1) 호감도를 1~5 점수로 매겨주세요 (1=전혀 끌리지 않음, 5=매우 끌림).
2) 실제로 가서 볼 의향이 있나요? (yes / maybe / no)
3) 가장 끌리는 요소 하나 (없으면 "없음")
4) 가장 걱정되거나 망설여지는 점 하나 (없으면 "없음")
5) 위 판단의 이유를 자기 말로 2~4문장 (200~400자 내외)

응답은 다음 JSON 형식으로만 답해주세요. 다른 설명·인사·서두 없이 JSON만.

{
  "appeal_score": 3,
  "visit_intent": "maybe",
  "key_attraction": "...",
  "key_concern": "...",
  "reason": "..."
}
"""


def build_prompt(
    persona: Union[pd.Series, Dict],
    scenario_dir: Path,
    scenario_vars: Dict[str, Any],
) -> Dict[str, str]:
    """페르소나 + 시나리오 → {system, user} 프롬프트 dict."""
    scenario_dir = Path(scenario_dir)
    context_path = scenario_dir / "context.md"
    if not context_path.exists():
        raise FileNotFoundError(f"context.md 없음: {context_path}")

    persona_dict = persona_to_dict(persona)
    system = render_template(SYSTEM_TEMPLATE, persona_dict)

    user_vars = {
        **scenario_vars,
        "context_body": context_path.read_text(encoding="utf-8"),
    }
    user = render_template(USER_TEMPLATE, user_vars)

    return {"system": system, "user": user}


if __name__ == "__main__":
    mock_persona = {
        "sex": "여자",
        "age": 34,
        "marital_status": "미혼",
        "military_status": "비현역",
        "family_type": "1인 가구",
        "housing_type": "원룸",
        "education_level": "4년제 대학교",
        "bachelors_field": "사회학",
        "occupation": "기획자",
        "province": "서울",
        "district": "서울-마포구",
        "persona": "(mock) 도시 생활을 즐기는 사회학 전공 기획자",
        "professional_persona": "(mock) 콘텐츠 기획",
        "family_persona": "(mock) 부모와 떨어져 살며 가끔 통화",
        "cultural_background": "(mock) 한국 도시문화에 친숙",
        "arts_persona": "(mock) 가끔 미술관 방문",
        "travel_persona": "(mock) 국내 여행 좋아함",
        "culinary_persona": "(mock) 카페 자주 감",
        "sports_persona": "(mock) 요가 1년차",
        "hobbies_and_interests": "(mock) 사진, 독서",
        "skills_and_expertise": "(mock) 행사 기획",
        "career_goals_and_ambitions": "(mock) 독립 기획자",
    }
    mock_vars = {
        "exhibition_title": "도시의 결",
        "exhibition_subtitle": "1990s 서울의 기록",
        "exhibition_period": "2026.05.01 ~ 2026.07.31",
        "exhibition_venue": "서울시립미술관 본관",
        "exhibition_admission": "5,000원",
        "exhibition_concept": "1990년대 서울의 도시 풍경과 일상을 사진·영상·인터뷰로 엮어 보여줍니다.",
        "exhibition_highlights": "- 보도사진 100점\n- 시민 인터뷰 영상 12편\n- 당시 일기·편지 모음",
    }

    scenario_dir = Path(__file__).parent.parent / "scenarios" / "exhibition_appeal"
    prompt = build_prompt(mock_persona, scenario_dir, mock_vars)

    print("=" * 60)
    print("SYSTEM PROMPT")
    print("=" * 60)
    print(prompt["system"])
    print()
    print("=" * 60)
    print("USER PROMPT (앞 800자만)")
    print("=" * 60)
    print(prompt["user"][:800])
    print(f"\n... (전체 {len(prompt['user'])}자)")

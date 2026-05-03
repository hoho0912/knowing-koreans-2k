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
6) 만약 가본다면 누구와 함께 가고 싶나요? 다음 중 하나만:
   - alone (혼자)
   - spouse (배우자/연인)
   - family_with_kids (자녀 동반 가족)
   - friends (친구)
   - parents (부모님)
   - colleagues (직장 동료)
   - nobody (가지 않음)
7) 이 전시를 누구에게 추천하고 싶나요? 다음 중 하나만:
   - spouse (배우자/연인)
   - family (가족 전반)
   - friends (친구)
   - colleagues (직장 동료)
   - general_public (불특정 일반)
   - no_one (추천하지 않음)

응답은 다음 JSON 형식으로만 답해주세요. 다른 설명·인사·서두 없이 JSON만.

{
  "appeal_score": 3,
  "visit_intent": "maybe",
  "key_attraction": "...",
  "key_concern": "...",
  "reason": "...",
  "preferred_companion": "alone",
  "recommend_to": "friends"
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


_QUESTION_NUM_RE = re.compile(r"^(\d+)\)\s", re.MULTILINE)
_JSON_KEY_RE = re.compile(r'"(\w+)"\s*:')


def _extract_question_numbers(text: str) -> set:
    return set(_QUESTION_NUM_RE.findall(text))


def _extract_json_example_keys(text: str) -> set:
    """질문 블록 뒤에 오는 JSON 예시(`{ ... }`)에서 최상위 키만 추출."""
    after_q = re.split(r"응답은 다음 JSON 형식", text, maxsplit=1)
    if len(after_q) < 2:
        return set()
    block = after_q[1]
    brace = re.search(r"\{[^{}]+\}", block, re.DOTALL)
    if not brace:
        return set()
    return set(_JSON_KEY_RE.findall(brace.group(0)))


def validate_prompt_schema(scenario_dir: Path) -> None:
    """question.md ↔ USER_TEMPLATE 정합성 검증.

    질문 번호 집합 + JSON 예시 키 집합이 일치해야 한다.
    측정 launch 전 호출. 불일치 시 ValueError → 한 건도 LLM 호출 안 함.

    plan B3.2 결함(question.md만 수정·prompt_builder.py 미수정 → v1 25분/3500원 낭비)
    재발 방지용 사전 훅.
    """
    qmd_path = Path(scenario_dir) / "question.md"
    if not qmd_path.exists():
        return  # question.md 없는 시나리오는 검증 스킵

    qmd = qmd_path.read_text(encoding="utf-8")

    qmd_q = _extract_question_numbers(qmd)
    tpl_q = _extract_question_numbers(USER_TEMPLATE)
    if qmd_q != tpl_q:
        raise ValueError(
            f"[schema drift] question.md 질문 번호 {sorted(qmd_q)} != "
            f"USER_TEMPLATE 질문 번호 {sorted(tpl_q)}. "
            f"prompt_builder.py USER_TEMPLATE 갱신 필요."
        )

    qmd_keys = _extract_json_example_keys(qmd)
    tpl_keys = _extract_json_example_keys(USER_TEMPLATE)
    if qmd_keys and tpl_keys and qmd_keys != tpl_keys:
        raise ValueError(
            f"[schema drift] question.md JSON 키 {sorted(qmd_keys)} != "
            f"USER_TEMPLATE JSON 키 {sorted(tpl_keys)}. "
            f"prompt_builder.py USER_TEMPLATE 갱신 필요."
        )


def validate_model_ids(model_ids: list) -> None:
    """call_llm 디스패치 가능한 prefix를 갖는지 검증.

    llm_runner.py 소스에서 `model_id.startswith("...")` 분기를 추출해
    요청된 model_id 모두가 그 중 하나에 매칭되는지 확인. 불일치 시 ValueError.

    KVM/Mac 환경 prefix 지원 차이(예: anthropic/ 미지원) 같은 engine drift를
    측정 시작 전에 잡는다.
    """
    runner_path = Path(__file__).parent / "llm_runner.py"
    if not runner_path.exists():
        return
    src = runner_path.read_text(encoding="utf-8")
    supported = set(re.findall(r'model_id\.startswith\(["\'](.+?)["\']\)', src))
    if not supported:
        return
    bad = [m for m in model_ids if not any(m.startswith(p) for p in supported)]
    if bad:
        raise ValueError(
            f"[engine drift] llm_runner.py가 처리할 수 없는 model_id: {bad}. "
            f"지원 prefix: {sorted(supported)}"
        )


# ─────────────────────────────────────────────────────────
# v6.2 인사이트 단계 — 자동 분기 5단계 파이프라인용 템플릿 (5종)
#
# 시뮬용 SYSTEM_TEMPLATE/USER_TEMPLATE과 별개. 인사이트 LLM 호출 단계에서만 사용.
#
# 모드 A — 단일 호출 (입력 ≤ 50만 토큰):
#   INSIGHT_SINGLE_SYSTEM + INSIGHT_SINGLE_USER_TEMPLATE
#
# 모드 B — 다회 호출 5단계 파이프라인 (입력 > 50만 토큰):
#   단계 2 cluster 분석:    CLUSTER_ANALYSIS_SYSTEM   + CLUSTER_ANALYSIS_USER_TEMPLATE
#   단계 3 cross-cluster:    CROSS_CLUSTER_DIFF_SYSTEM + CROSS_CLUSTER_DIFF_USER_TEMPLATE
#   단계 4 raw retrieval:    RAW_RETRIEVAL_SYSTEM      + RAW_RETRIEVAL_USER_TEMPLATE
#   단계 5 합성:             SYNTHESIS_SYSTEM          + SYNTHESIS_USER_TEMPLATE
#
# 모든 출력은 동일한 4섹션 JSON 스키마로 끝나도록 설계. 다회 호출이라도
# 최종 산출물 형태는 단일 호출과 같음.
# ─────────────────────────────────────────────────────────


# 출력 스키마 — 모드 A 단일 호출과 모드 B 단계 5(합성)에서 공통 사용
# analysis_tables는 분석 LLM이 본 측정 schema·raw 응답을 직접 보고 자율 결정.
_INSIGHT_OUTPUT_SCHEMA = """\
다음 JSON 형식으로만 응답하세요. 다른 설명·인사·서두 없이 JSON만.

{{
  "analysis_tables": [
    {{"title": "예: 호감도 평균 — 응답자 속성 축별", "markdown": "| 응답자 속성 | 응답수 | 평균 |\\n|---|---:|---:|\\n| 전체 | 100 | 3.42 |"}}
  ],
  "key_findings": [
    {{"label": "01. 전체 응답 분포", "content": "..."}},
    {{"label": "02. (차원 이름)",   "content": "..."}}
  ],
  "curator_hypotheses": [
    {{"target_group": "30대 여성 수도권", "form": "SNS 카피 / 포스터 강조점 / 큐레이션 동선 / 도슨트 톤 / 교육 프로그램 주제어", "content": "..."}}
  ],
  "responses_to_chew_on": [
    {{"model": "Hermes 4 405B", "persona_attrs": "60대 여성 · 전라남도 · 고졸", "quote": "...", "curator_note": "..."}}
  ],
  "next_questions": [
    "...",
    "..."
  ]
}}

- analysis_tables: 본 측정에 필요한 분석 표 모음. 본 측정 schema(질문 type·옵션·범위 등)와 raw 응답을 직접 보고 어떤 분석 표가 가설 발견에 유용한지 자율 결정해 주세요. 표 갯수·종류·축은 자유. 표 markdown 규약은 아래 별도 항목 참조. (보통 3~8개 범위에서 본 측정에 맞춰 결정)
- key_findings: 5~8개. 첫 열은 중립적 차원 이름만, 분석 결론·수치는 content. analysis_tables에서 읽힌 패턴을 큐레이터 시점으로 정리.
- curator_hypotheses: 3~5개. 큐레이터가 즉시 적용 가능한 형태(SNS·포스터·동선·도슨트·교육).
- responses_to_chew_on: 2~3개. raw 인용 + 큐레이터 노트.
- next_questions: 3~5개. 본 측정이 새로 떠올리게 한 질문.

표 markdown 규약 (analysis_tables[].markdown):
- GitHub-flavored markdown 표. 첫 행 헤더, 두 번째 행 구분선(`|---|`).
- 숫자 열은 우측 정렬(`|---:|`), 텍스트 열은 좌측 기본(`|---|`).
- JSON 문자열 안에서는 줄바꿈을 `\\n` 이스케이프로, 셀 안 `|` 문자는 `\\|`로 표현.
- 표 한 개당 가로폭 최대 8~10열 권장. 더 많은 차원이 필요하면 표를 분리.
- 표본이 작은 그룹(N<10 등)은 그 사실을 표 캡션 또는 행에 함께 명시.
- 표 종류 예시(자율 선택): 응답자 속성 축별 평균·분포 / 옵션 빈도 / 키워드·테마 빈도 / 응답 항목 간 교차표 / narrative ↔ 응답 정합성 표 등. 본 측정 데이터에 맞는 표만 작성하세요."""


# 인사이트 단계 공통 어조·원칙 (큐레이터 비평가)
_INSIGHT_COMMON_PRINCIPLES = """\
다음 원칙을 지키세요:
- 합성 페르소나 응답은 여론조사가 아닙니다. 단언하지 말고 "이 모델·이 표본에서는 …" 같이 한정해 주세요.
- 영어 시스템 용어 금지 ('demographic', 'segment', 'sample', 'cohort' → '응답자 속성', '응답자 그룹', '표본'). '페르소나·모델·시뮬레이션'은 외래어로 사용 가능.
- key_findings 첫 열(label)에 분석 결론·수치를 적지 마세요. 중립적 차원 이름만 적습니다.
  · 권장: "01. 전체 응답 분포"  /  금지: "01. 호감도는 5점 만점에 평균 2.78점"
- 추상적 진술("관람객은 다양하게 반응했다") 회피. 큐레이터가 바로 사용할 수 있는 구체적 형태(SNS 카피 톤·포스터 강조점·큐레이션 동선·도슨트 톤·교육 프로그램 주제어)로 제시.
- 모델 균질화·사회적 바람직성 편향 가능성을 한 줄 언급.
- N이 작은 응답자 그룹 분석은 "N이 작아 신호로 보기 어렵다"고 명시.
- 페르소나 속성(거주지·연령대·성별·학력·혼인·직업)은 자료에 명시되어 있으니 "고령 추정·중산층 추정" 같은 짐작 표기 금지. 그대로 인용.
- 응답 직접 인용 시 모델명 + 페르소나 속성 함께. 예: "(Hermes 4 405B · 60대 여성 · 전라남도 · 고졸)".
- 리커트 응답코드(1~5)는 "점수"가 아니라 응답을 수치화한 코드. "1점/5점" 표기 회피, "Q1=2가 41건"처럼 코드 의미 함께 전달.
- 응답 항목들 사이의 ambivalence(예: 호감도/의향 같은 정량 지표가 낮은데 자유서술 reason에는 긍정 단어가 섞이는 패턴)를 적극 발견하고, 그것이 어떤 응답자 속성에 어떻게 분포하는지 해석.
"""


INSIGHT_SINGLE_SYSTEM = """당신은 박물관·문화 분야 큐레이터를 옆에서 돕는 비평가입니다.
큐레이터는 합성 페르소나·다중 LLM의 응답을 통해, 자기가 미처 떠올리지
못한 관점·가설을 발견하고 싶어합니다.

본 응답은 보고서의 "응답 분석 + 해석 + 가설 + 인사이트" 부분을 통째로
담당합니다. 측정 개요·페르소나 분포는 별도 코드에서 결정론적으로 생성되어
본 응답의 앞에, 원본 질문·스키마·명세는 부록으로 본 응답의 뒤에 자동으로
붙습니다.

본 응답에서 직접 결정해야 하는 것:
- 본 측정의 schema(질문 type·옵션·범위 등)와 raw 응답을 직접 보고, 어떤
  분석 표가 가설 발견에 유용한지 자율 결정해 주세요. 표 갯수·종류·축은
  자유 — 응답이 likert면 평균·분포 표가, 객관식이면 옵션 빈도 표가,
  주관식이면 키워드·테마 빈도 표가, 응답 항목들 사이의 상관이 흥미로우면
  교차 표가 적절할 수 있습니다. 어떤 표가 본 측정에 맞는지는 데이터를
  보고 결정해 주세요.
- 분석 표를 먼저 작성하고(analysis_tables), 그 표에서 읽히는 패턴을
  큐레이터 시점으로 풀어 key_findings·curator_hypotheses·next_questions에
  반영해 주세요.

지정된 JSON 스키마로만 답하세요.

""" + _INSIGHT_COMMON_PRINCIPLES


INSIGHT_SINGLE_USER_TEMPLATE = """이번 측정 자료입니다. 본 응답에는
**분석 표 + 해석 + 가설 + 인사이트**를 지정된 JSON 스키마로 담아 주세요.

분석 표(analysis_tables)는 본 측정의 schema와 아래 raw 응답을 직접 보고
어떤 표가 가설 발견에 유용한지 당신이 자율 결정합니다. 코드는 본 응답
위에 측정 개요·페르소나 분포를, 뒤에 원본 질문·스키마·명세 부록을
자동으로 붙이므로 그 부분은 다시 그릴 필요 없습니다.

## 측정 주제
{topic}

## 시나리오 컨텍스트 (LLM에 주입한 박물관·전시 자료)
{context}

## 질문 (페르소나에게 던진 응답 항목들 — 시나리오별 변동)
{questions}

## 표본 페르소나 응답자 속성 분포 (N={n_personas})
{persona_dist}

## 페르소나 narrative (전수 — 응답자 속성 + 11컬럼 자기소개)
_각 페르소나의 직업·가족·문화·예술·여행·음식·스포츠·관심사·숙련·목표 narrative입니다._
_응답 raw와 비교해 narrative ↔ 응답 정합성 사례를 'responses_to_chew_on'에 넣어 주세요._

{persona_narratives}

## 모델별 응답 통계
{stats}

## 응답 raw (전수 — 페르소나 속성 + 응답 항목 전수)
_각 행은 [모델, 응답자 속성] payload(시나리오 question.md에 정의된 응답 항목 전수의 JSON) 형식입니다._
_정량 지표가 낮은데 자유서술 reason에는 긍정 단어가 섞이는 식의 ambivalence — 응답 항목들 사이의 모순·정합성을 적극 해석해 주세요._

{samples_block}

---

""" + _INSIGHT_OUTPUT_SCHEMA


CLUSTER_ANALYSIS_SYSTEM = """당신은 박물관·문화 분야 큐레이터를 옆에서 돕는 비평가입니다.
큐레이터는 합성 페르소나·다중 LLM 응답을 통해 새로운 관점·가설을 찾고 있습니다.

본 응답은 **다회 호출 파이프라인의 cluster 분석 단계**입니다. 전체 응답을
페르소나 axis(연령·성별·지역·교육) 분포를 보존하며 cluster들로 나누었고,
당신은 그 중 한 cluster를 분석합니다. 후속 단계에서 다른 cluster들의 분석
결과와 종합되므로, 본 cluster에서 관측한 사실·패턴을 충실히 기록해 주세요.

다른 cluster를 추측하지 말고 **본 cluster에서 직접 관측한 것만** 보고합니다.

""" + _INSIGHT_COMMON_PRINCIPLES


CLUSTER_ANALYSIS_USER_TEMPLATE = """본 cluster의 분석 자료입니다. 본 cluster에서 관측한 사실·패턴만
JSON 구조로 보고해 주세요.

## 측정 주제
{topic}

## 시나리오 컨텍스트
{context}

## 질문 (시나리오 question.md 응답 항목 전수)
{questions}

## 본 cluster 메타
- cluster_id: {cluster_id}
- cluster 내 페르소나 수: {n_personas}
- cluster 내 응답 수: {n_responses}
- cluster axis 분포: {axis_dist}
- 전체 N 대비 비중: {cluster_share}

## 본 cluster 페르소나 narrative (전수)
{persona_narratives}

## 본 cluster 모델별 응답 통계
{stats}

## 본 cluster 응답 raw (전수)
{samples_block}

---

다음 JSON 형식으로만 응답하세요. 다른 설명·인사·서두 없이 JSON만.

{{
  "cluster_id": "{cluster_id}",
  "n_personas": {n_personas},
  "n_responses": {n_responses},
  "observed_patterns": [
    {{"label": "01. 전체 응답 분포 (본 cluster)", "content": "..."}}
  ],
  "ambivalence_findings": [
    {{"type": "appeal_score≤2 + reason 긍정 단어", "count": 12, "share": "30%", "example_persona_attrs": "...", "example_quote": "..."}}
  ],
  "narrative_response_alignment": [
    {{"persona_attrs": "...", "narrative_signal": "예: arts_persona='전시 자주 안 감'", "response_signal": "visit_intent='yes'", "interpretation": "..."}}
  ],
  "representative_quotes": [
    {{"model": "...", "persona_attrs": "...", "quote": "...", "why_representative": "..."}}
  ],
  "cluster_specific_notes": "본 cluster에서만 관측되거나 강하게 나타난 신호. 후속 cross-cluster diff 단계에서 비교용 입력."
}}

- observed_patterns: 3~6개. 본 cluster의 응답 항목 분포·교차 패턴.
- ambivalence_findings: 발견한 모순·약신호 모두 (없으면 빈 배열).
- narrative_response_alignment: 페르소나 narrative와 응답이 정합/부정합한 사례 2~5개.
- representative_quotes: 본 cluster를 대표할 만한 raw 인용 5~10건.
"""


CROSS_CLUSTER_DIFF_SYSTEM = """당신은 박물관·문화 분야 큐레이터를 옆에서 돕는 비평가입니다.
본 응답은 **다회 호출 파이프라인의 cross-cluster diff 단계**입니다. 앞 단계에서
cluster들을 병렬로 분석한 결과를 받습니다. 당신의 임무는:

1. cluster들 사이의 공통점·차이·약신호 발견
2. 단일 cluster만 보고는 잡히지 않는 cross-cluster 패턴 식별
3. 추가 raw 검증이 필요한 의심 cluster id 지정 (선택)

병렬 분석 단계에서 다른 cluster를 못 본 한계를 본 단계에서 통합 시야로
보완합니다(map-reduce에서 "전체를 보지 못할 가능성" 보완책).

""" + _INSIGHT_COMMON_PRINCIPLES


CROSS_CLUSTER_DIFF_USER_TEMPLATE = """병렬 cluster 분석 결과입니다. cluster들을 가로질러 비교·종합해 주세요.

## 측정 주제
{topic}

## cluster 메타 요약
- 총 cluster 수: {n_clusters}
- 총 페르소나: {total_personas}
- 총 응답: {total_responses}

## cluster별 분석 결과 (단계 2 출력 모음)
{cluster_summaries_block}

---

다음 JSON 형식으로만 응답하세요. 다른 설명·인사·서두 없이 JSON만.

{{
  "common_patterns": [
    {{"label": "...", "content": "...", "shared_across_clusters": ["c1", "c2", "c3"]}}
  ],
  "diverging_patterns": [
    {{"label": "...", "content": "...", "cluster_contrast": [{{"cluster_id": "c1", "signal": "..."}}, {{"cluster_id": "c2", "signal": "..."}}]}}
  ],
  "weak_signals": [
    {{"label": "...", "content": "단일 cluster만 보면 잡히지 않으나 cluster들을 가로지르면 보이는 패턴"}}
  ],
  "missing_in_clusters": [
    {{"description": "어느 cluster에서 빠진 신호이고 그게 의심스러운가"}}
  ],
  "suspect_cluster_ids": ["c2"],
  "suspect_reason": "왜 이 cluster들의 raw 재확인이 필요한가 (선택, raw retrieval 옵션 ON 시 단계 4 입력)"
}}

- common_patterns: 다수 cluster에서 동일하게 관측된 패턴 3~5개.
- diverging_patterns: cluster마다 갈리는 패턴 3~5개.
- weak_signals: cross-cluster 통합 시야에서만 보이는 약신호 2~5개.
- missing_in_clusters: 어느 cluster에서 *빠진* 신호 (예상 대비) 0~3개.
- suspect_cluster_ids / suspect_reason: 단계 4 raw retrieval 후보. 의심 없으면 빈 배열.
"""


RAW_RETRIEVAL_SYSTEM = """당신은 박물관·문화 분야 큐레이터를 옆에서 돕는 비평가입니다.
본 응답은 **다회 호출 파이프라인의 raw retrieval 단계 (옵션)**입니다. 앞
cross-cluster diff 단계에서 의심 cluster로 지정된 cluster들의 raw 응답과
페르소나 narrative를 다시 받습니다. 단계 2 cluster 분석에서 놓치거나
오해석한 부분이 있는지 raw 자료를 직접 보고 검증해 주세요.

이 단계는 BOOOOKSCORE류 평가에서 source re-injection으로 hallucination
확률을 낮추는 보완책에 해당합니다.

""" + _INSIGHT_COMMON_PRINCIPLES


RAW_RETRIEVAL_USER_TEMPLATE = """의심 cluster의 raw 자료를 다시 받습니다. 단계 2 분석을 raw에 비춰 검증해 주세요.

## cluster_id
{cluster_id}

## 단계 2 분석 (검증 대상)
{cluster_summary}

## 단계 3 cross-cluster diff 의심 사유
{suspect_reason}

## raw 페르소나 narrative (본 cluster 전수)
{persona_narratives}

## raw 응답 (본 cluster 전수)
{samples_block}

---

다음 JSON 형식으로만 응답하세요. 다른 설명·인사·서두 없이 JSON만.

{{
  "cluster_id": "{cluster_id}",
  "verification": "confirmed | partially_confirmed | refuted",
  "confirmed_findings": ["..."],
  "refuted_findings": [{{"original_claim": "...", "raw_evidence": "...", "correction": "..."}}],
  "additional_findings": ["raw에서 새로 발견한 내용"],
  "amended_cluster_summary": "단계 5 합성에서 단계 2 summary 대신 사용할 보강된 summary"
}}
"""


SYNTHESIS_SYSTEM = """당신은 박물관·문화 분야 큐레이터를 옆에서 돕는 비평가입니다.
본 응답은 **다회 호출 파이프라인의 최종 합성 단계**입니다. 단계 2 cluster
분석들 + 단계 3 cross-cluster diff + (옵션) 단계 4 raw retrieval 결과를
받아, 단일 호출 모드와 동일한 형태(4섹션 JSON)로 보고서를 작성합니다.

본 응답은 보고서의 "해석·인사이트" 부분만 담당합니다. 측정 개요·축별 분포·
부록은 별도 코드에서 자동 생성되어 본 응답 위아래에 붙습니다.

""" + _INSIGHT_COMMON_PRINCIPLES


SYNTHESIS_USER_TEMPLATE = """다회 호출 파이프라인의 모든 단계 결과입니다.
이를 통합해 4섹션 JSON 보고서를 작성해 주세요.

## 측정 주제
{topic}

## 시나리오 컨텍스트 (요약)
{context_short}

## 측정 메타
- 총 페르소나: {total_personas}
- 총 응답: {total_responses}
- cluster 수: {n_clusters}
- 단계 4 raw retrieval 사용: {retrieval_used}

## 단계 2 — cluster별 분석 (병렬 호출 결과 모음)
{cluster_summaries_block}

## 단계 3 — cross-cluster diff
{diff_block}

## 단계 4 — raw retrieval 결과 (있으면)
{retrieval_block}

---

위 모든 단계 결과를 통합해 다음 4섹션 JSON으로 답하세요. cluster들 사이의
공통·차이·약신호 모두 반영. raw retrieval 결과로 정정된 부분은 정정된 형태로.

""" + _INSIGHT_OUTPUT_SCHEMA


_INSIGHT_TOP_KEY_RE = re.compile(r'^\s{2}"(\w+)"\s*:', re.MULTILINE)


def validate_insight_prompt_schema() -> None:
    """v6.2 인사이트 단계 5종 template의 출력 JSON 키 정합성 + .format() 안전성 검증.

    INSIGHT_SINGLE_USER_TEMPLATE과 SYNTHESIS_USER_TEMPLATE 모두 동일한
    4섹션 출력(key_findings / curator_hypotheses / responses_to_chew_on /
    next_questions)을 반환해야 한다. 모드 A·B 출력이 같은 schema라야
    하류(보고서 합치기 + PDF 렌더)에서 분기 없이 같은 코드로 처리 가능.

    측정 launch 전 zero-cost 호출. drift 시 ValueError.

    검증 항목:
    1. _INSIGHT_OUTPUT_SCHEMA의 JSON 예시 블록 최상위 키 4종 존재
    2. INSIGHT_SINGLE / SYNTHESIS USER_TEMPLATE이 _INSIGHT_OUTPUT_SCHEMA로 끝남
    3. 5종 USER_TEMPLATE 모두 .format() 호출이 KeyError 없이 통과 (raw `{` `}`
       이스케이프 누락 차단 — 어제 _INSIGHT_OUTPUT_SCHEMA 미escape으로 launch
       단계에서 KeyError 났던 사고 재발 방지).
    """
    import string

    expected_top_keys = {
        "key_findings",
        "curator_hypotheses",
        "responses_to_chew_on",
        "next_questions",
    }
    schema_keys = set(_INSIGHT_TOP_KEY_RE.findall(_INSIGHT_OUTPUT_SCHEMA))
    if not expected_top_keys.issubset(schema_keys):
        missing = expected_top_keys - schema_keys
        raise ValueError(
            f"[insight schema drift] _INSIGHT_OUTPUT_SCHEMA 최상위 키 누락: "
            f"{sorted(missing)} (찾은 키: {sorted(schema_keys)})"
        )
    for name, template in (
        ("INSIGHT_SINGLE_USER_TEMPLATE", INSIGHT_SINGLE_USER_TEMPLATE),
        ("SYNTHESIS_USER_TEMPLATE", SYNTHESIS_USER_TEMPLATE),
    ):
        if not template.rstrip().endswith(_INSIGHT_OUTPUT_SCHEMA.rstrip()):
            raise ValueError(
                f"[insight schema drift] {name}이 _INSIGHT_OUTPUT_SCHEMA로 "
                f"끝나지 않음 — 모드 A·B 출력 정합성 깨짐"
            )

    formatter = string.Formatter()
    for name, template in (
        ("INSIGHT_SINGLE_USER_TEMPLATE", INSIGHT_SINGLE_USER_TEMPLATE),
        ("CLUSTER_ANALYSIS_USER_TEMPLATE", CLUSTER_ANALYSIS_USER_TEMPLATE),
        ("CROSS_CLUSTER_DIFF_USER_TEMPLATE", CROSS_CLUSTER_DIFF_USER_TEMPLATE),
        ("RAW_RETRIEVAL_USER_TEMPLATE", RAW_RETRIEVAL_USER_TEMPLATE),
        ("SYNTHESIS_USER_TEMPLATE", SYNTHESIS_USER_TEMPLATE),
    ):
        try:
            field_names = {
                fname for _, fname, _, _ in formatter.parse(template) if fname
            }
        except ValueError as e:
            raise ValueError(
                f"[insight schema drift] {name} parse 실패: {e} — raw `{{` `}}` "
                f"이스케이프 확인 (`{{{{` `}}}}` 처리 필요)"
            )
        sample = {k: f"<{k}>" for k in field_names}
        try:
            template.format(**sample)
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError(
                f"[insight schema drift] {name} .format() 실패: {type(e).__name__}: {e} "
                f"— template 안 raw `{{` `}}`가 placeholder로 오인됨. "
                f"`{{{{` `}}}}` escape 처리 필요"
            )


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

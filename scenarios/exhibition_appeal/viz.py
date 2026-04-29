"""
exhibition_appeal — 시각화 차원 정의 (skeleton)

이 파일은 시나리오의 응답 필드를 어떻게 시각화에 매핑할지 정의한다.
실제 차트 코드는 frontend/index.html (stlite) 안에서 구현되며,
이 파일은 시나리오 메타데이터만 노출한다.
"""

SCENARIO_ID = "exhibition_appeal"
SCENARIO_TITLE = "전시 콘셉트 호감도"
SCENARIO_VERSION = "0.1"


# 응답 필드 → 시각화 차원 매핑
RESPONSE_FIELDS = {
    "appeal_score": {
        "type": "ordinal",
        "range": (1, 5),
        "label": "호감도",
        "color_scale": "RdYlGn",  # 1=빨강 → 5=초록
    },
    "visit_intent": {
        "type": "categorical",
        "values": ["yes", "maybe", "no"],
        "label": "관람 의향",
        "color_map": {
            "yes": "#2E7D32",
            "maybe": "#F9A825",
            "no": "#C62828",
        },
    },
    "key_attraction": {
        "type": "text",
        "label": "가장 끌리는 요소",
        "viz": "wordcloud_or_cluster",  # M2~M3에서 구현
    },
    "key_concern": {
        "type": "text",
        "label": "걱정·망설임",
        "viz": "wordcloud_or_cluster",
    },
    "reason": {
        "type": "text",
        "label": "사유",
        "viz": "card_display",  # 응답 카드에 그대로 노출
    },
}


# 페르소나 차원 × 응답 차트 (M1에서 우선 구현)
CROSS_TAB_DIMENSIONS = [
    ("age_bucket", "appeal_score", "연령대 × 호감도"),
    ("province", "appeal_score", "지역(시도) × 호감도"),
    ("sex", "appeal_score", "성별 × 호감도"),
    ("education_level", "appeal_score", "학력 × 호감도"),
    ("occupation", "appeal_score", "직업 × 호감도"),
    ("model", "appeal_score", "모델별 호감도 분포"),
    ("model", "visit_intent", "모델별 관람 의향"),
]


# 다양성 지표 (균질화 비판 대응)
DIVERSITY_METRICS = [
    {
        "name": "demographic_homogeneity",
        "method": "std_within_group",
        "groupby": ["sex", "age_bucket", "province"],
        "field": "appeal_score",
        "label": "같은 인구집단 내 호감도 표준편차 (낮을수록 균질)",
    },
]


# 응답 카드 표시 필드 (vuski 패턴 차용)
CARD_DISPLAY = {
    "header_chip": "visit_intent",
    "score_badge": "appeal_score",
    "attraction": "key_attraction",
    "concern": "key_concern",
    "narrative": "reason",
    "persona_expander_fields": [
        "arts_persona",       # 박물관·문화 시나리오 핵심
        "cultural_background",
        "hobbies_and_interests",
        "professional_persona",
        "family_persona",
    ],
}


# (M3 시계열 단계에서 사용) 컨텍스트 snapshot 비교 차원
TIMESERIES_DIMENSIONS = [
    ("context_snapshot_id", "appeal_score", "시점별 호감도 변화"),
]

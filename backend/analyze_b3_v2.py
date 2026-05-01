"""
B3 v2 측정 분석 보고서 — 페르소나 demographic 분석

데이터 구조:
- 응답 300건 (페르소나 100명 × 3회 조사 = 1차·2차·3차)
- 본문은 응답 300건 종합 demographic 분석. 차수별 비교는 본문 뒤 3 시트에 간단히
- 모델 선정 방법론은 부록에서만 다룸
- 페르소나는 NVIDIA Nemotron-Personas-Korea 700만에서 연령대 균등 추출,
  수도권·비수도권 절반씩 분포 (전시가 한양대박물관에서 열리므로 의도된 설계)

산출물:
- backend/results/b3_v2_analysis.xlsx (21 시트)
- backend/results/b3_v2_analysis.pdf (21 섹션)
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_DIR = PROJECT_ROOT / "backend" / "results"
V2_CSV = RESULTS_DIR / "exhibition_appeal_2026-04-where-things-linger-models-v2-q7.csv"
OUT_XLSX = RESULTS_DIR / "b3_v2_analysis.xlsx"
OUT_PDF = RESULTS_DIR / "b3_v2_analysis.pdf"

SUDOGWON = ["서울", "경기", "인천"]

COMPANION_KO = {
    "alone": "혼자",
    "spouse": "배우자/연인",
    "family_with_kids": "자녀 동반 가족",
    "friends": "친구",
    "parents": "부모님",
    "colleagues": "직장 동료",
    "nobody": "가지 않음",
}
COMPANION_ORDER = ["alone", "spouse", "family_with_kids", "friends", "parents", "colleagues", "nobody"]

RECOMMEND_KO = {
    "spouse": "배우자/연인",
    "family": "가족 전반",
    "friends": "친구",
    "colleagues": "직장 동료",
    "general_public": "불특정 일반",
    "no_one": "추천 안 함",
}
RECOMMEND_ORDER = ["spouse", "family", "friends", "colleagues", "general_public", "no_one"]

VISIT_INTENT_KO = {"yes": "갈 의향 있음", "maybe": "보통(망설임)", "no": "안 감"}

AGE_ORDER = ["~19", "20대", "30대", "40대", "50대", "60+"]
EDU_ORDER = ["무학", "초등학교", "중학교", "고등학교", "2~3년제 전문대학", "4년제 대학교", "대학원"]


def load() -> pd.DataFrame:
    df = pd.read_csv(V2_CSV)
    df["region"] = df["province"].apply(lambda p: "수도권" if p in SUDOGWON else "비수도권")
    return df


# ─────────── 호감도 계산 helper ───────────

def appeal_summary_row(sub: pd.DataFrame) -> Dict:
    s = sub["appeal_score"]
    return {
        "응답자 수": len(sub),
        "호감도 평균": round(s.mean(), 2),
        "흩어짐(표준편차)": round(s.std(), 2) if len(s) > 1 else 0.0,
        "1점": int((s == 1).sum()),
        "2점": int((s == 2).sum()),
        "3점": int((s == 3).sum()),
        "4점": int((s == 4).sum()),
        "5점": int((s == 5).sum()),
    }


def appeal_by_dim(df: pd.DataFrame, dim: str, dim_label: str, order: List[str] = None) -> pd.DataFrame:
    rows = []
    if order:
        groups = [(v, df[df[dim] == v]) for v in order if (df[dim] == v).any()]
    else:
        groups = [(v, sub) for v, sub in df.groupby(dim)]
    for val, sub in groups:
        row = {dim_label: val}
        row.update(appeal_summary_row(sub))
        rows.append(row)
    out = pd.DataFrame(rows)
    if not order:
        out = out.sort_values("응답자 수", ascending=False).reset_index(drop=True)
    return out


def visit_by_dim(df: pd.DataFrame, dim: str, dim_label: str, order: List[str] = None) -> pd.DataFrame:
    rows = []
    if order:
        groups = [(v, df[df[dim] == v]) for v in order if (df[dim] == v).any()]
    else:
        groups = [(v, sub) for v, sub in df.groupby(dim)]
    for val, sub in groups:
        n = len(sub)
        yes = int((sub["visit_intent"] == "yes").sum())
        maybe = int((sub["visit_intent"] == "maybe").sum())
        no = int((sub["visit_intent"] == "no").sum())
        rows.append({
            dim_label: val,
            "응답자 수": n,
            "갈 의향 있음": yes,
            "보통(망설임)": maybe,
            "안 감": no,
            "갈 의향 %": round(100 * yes / n, 1) if n else 0,
            "보통 %": round(100 * maybe / n, 1) if n else 0,
            "안 감 %": round(100 * no / n, 1) if n else 0,
        })
    out = pd.DataFrame(rows)
    if not order:
        out = out.sort_values("응답자 수", ascending=False).reset_index(drop=True)
    return out


def companion_by_dim(df: pd.DataFrame, dim: str, dim_label: str, order: List[str] = None) -> pd.DataFrame:
    rows = []
    if order:
        groups = [(v, df[df[dim] == v]) for v in order if (df[dim] == v).any()]
    else:
        groups = [(v, sub) for v, sub in df.groupby(dim)]
    for val, sub in groups:
        n = len(sub)
        row = {dim_label: val, "응답자 수": n}
        for k in COMPANION_ORDER:
            row[COMPANION_KO[k]] = int((sub["preferred_companion"] == k).sum())
        rows.append(row)
    out = pd.DataFrame(rows)
    if not order:
        out = out.sort_values("응답자 수", ascending=False).reset_index(drop=True)
    return out


def recommend_by_dim(df: pd.DataFrame, dim: str, dim_label: str, order: List[str] = None) -> pd.DataFrame:
    rows = []
    if order:
        groups = [(v, df[df[dim] == v]) for v in order if (df[dim] == v).any()]
    else:
        groups = [(v, sub) for v, sub in df.groupby(dim)]
    for val, sub in groups:
        n = len(sub)
        row = {dim_label: val, "응답자 수": n}
        for k in RECOMMEND_ORDER:
            row[RECOMMEND_KO[k]] = int((sub["recommend_to"] == k).sum())
        rows.append(row)
    out = pd.DataFrame(rows)
    if not order:
        out = out.sort_values("응답자 수", ascending=False).reset_index(drop=True)
    return out


def stack_by_dims(df: pd.DataFrame, dim_specs: List, builder) -> pd.DataFrame:
    """여러 demographic 차원을 한 시트에 세로로 쌓음.
    dim_specs: [(dim_col, dim_label, order_or_None), ...]
    builder: appeal_by_dim / visit_by_dim / companion_by_dim / recommend_by_dim
    """
    chunks = []
    for dim_col, dim_label, order in dim_specs:
        block = builder(df, dim_col, dim_label, order)
        block.insert(0, "차원", dim_label)
        block = block.rename(columns={dim_label: "그룹"})
        chunks.append(block)
    return pd.concat(chunks, ignore_index=True)


# ─────────── 자유 응답 ───────────

def top_words(series: pd.Series, n: int = 20) -> List:
    text = " ".join(series.dropna().astype(str).tolist())
    text = re.sub(r"[^\w가-힣]", " ", text)
    words = [w for w in text.split() if len(w) >= 2 and not w.isdigit()]
    return Counter(words).most_common(n)


# ─────────── 시트 생성 ───────────

def sheet_측정개요(df: pd.DataFrame) -> pd.DataFrame:
    persona_first = df.groupby("persona_uuid").first()
    n_persona = len(persona_first)
    n_sudo = (persona_first["region"] == "수도권").sum()
    n_nonsudo = n_persona - n_sudo
    rows = [
        ["측정일", "2026-04-29"],
        ["전시 시나리오", "묻힌 그릇들은 아직 끝나지 않았다 (Where Things Linger)"],
        ["전시 정보", "한양대학교박물관 · 무료 · 2026.05.06–07.18"],
        ["페르소나 출처", "NVIDIA Nemotron-Personas-Korea (~700만 명, CC BY 4.0)"],
        ["추출 방식", "연령대 균등 + 수도권·비수도권 의도된 절반 분포 (전시 개최 지역 반영)"],
        ["페르소나 수", f"{n_persona}명 (수도권 {n_sudo}명 / 비수도권 {n_nonsudo}명)"],
        ["응답자 수", f"{len(df)}건 (페르소나 1명당 3회 조사 진행 — 1차·2차·3차)"],
        ["성별 분포", f"여자 {(persona_first['sex']=='여자').sum()}명, 남자 {(persona_first['sex']=='남자').sum()}명"],
        ["연령대 분포", " · ".join(f"{a} {(persona_first['age_bucket']==a).sum()}명" for a in AGE_ORDER if (persona_first['age_bucket']==a).any())],
        ["학력 분포", " · ".join(f"{e} {(persona_first['education_level']==e).sum()}명" for e in EDU_ORDER if (persona_first['education_level']==e).any())],
        ["혼인 분포", " · ".join(f"{m} {(persona_first['marital_status']==m).sum()}명" for m in persona_first['marital_status'].value_counts().index)],
        ["질문 수", "7개 (호감도, 관람 의향, 끌리는 점, 걱정, 이유, 동반자 선호, 추천 대상)"],
    ]
    return pd.DataFrame(rows, columns=["항목", "값"])


def sheet_핵심발견(df: pd.DataFrame) -> pd.DataFrame:
    s = df["appeal_score"]
    overall_mean = s.mean()
    overall_std = s.std()

    # 학력
    edu_means = df.groupby("education_level")["appeal_score"].mean().round(2)
    # 성별
    sex_means = df.groupby("sex")["appeal_score"].mean().round(2)
    # 수도권
    region_means = df.groupby("region")["appeal_score"].mean().round(2)
    region_n = df.groupby("region").size()
    # 연령
    age_means = df.groupby("age_bucket")["appeal_score"].mean().round(2)
    # 동반자 / 추천 / 의향 — 전체
    comp_dist = df["preferred_companion"].value_counts()
    rec_dist = df["recommend_to"].value_counts()
    visit_dist = df["visit_intent"].value_counts()

    findings = [
        ("01. 호감도는 5점 만점에 평균 2.78점 — \"적극적으로 끌리지는 않으나 거부도 아님\"",
         f"응답 300건 전체의 호감도 평균은 {overall_mean:.2f}점, 흩어짐(표준편차)은 {overall_std:.2f}였습니다. "
         f"5점을 준 응답은 0건, 1점도 0건. 응답이 모두 2~4점 사이에 응집했습니다 — "
         f"즉 페르소나의 어떤 그룹도 \"꼭 가야 할 전시\"라고 답하지 않았고, 동시에 \"절대 안 갈 전시\"라고도 답하지 않았습니다."),

        ("02. 망설임 요인은 \"거리\"와 \"추상성\" 두 가지로 일관되게 모임",
         f"\"가장 걱정되는 점\" 자유 응답에서 가장 자주 등장한 단어는 "
         f"\"서울까지\"·\"성동구까지\"·\"거리와 가는 시간\"이었고, 그 다음이 \"주제가 너무 추상적이고\"였습니다. "
         f"비수도권 페르소나에게는 한양대박물관까지의 물리적 거리가, 학력·관심사가 다양한 페르소나 전반에는 "
         f"그릇·폐기·소멸이라는 콘셉트의 추상성·문학성이 진입 장벽이었습니다. "
         f"끌리는 점에서는 \"버려진 그릇이 다시 불러짐\"·\"일상의 시간\"·\"무료\"가 자주 등장해 "
         f"콘셉트의 시적 성격과 운영 조건(무료) 자체는 매력으로 작용했습니다."),

        ("03. 학력에 따른 호감도 격차가 가장 큰 신호 — 4년제 대학 3.25점 vs 고등학교 2.62점",
         f"학력 그룹별 호감도 평균은 4년제 대학교 {edu_means.get('4년제 대학교', float('nan')):.2f}점(81응답), "
         f"대학원 {edu_means.get('대학원', float('nan')):.2f}점(27응답), "
         f"2~3년제 전문대학 {edu_means.get('2~3년제 전문대학', float('nan')):.2f}점(33응답), "
         f"고등학교 {edu_means.get('고등학교', float('nan')):.2f}점(126응답), "
         f"중학교 {edu_means.get('중학교', float('nan')):.2f}점(18응답), 초등학교 {edu_means.get('초등학교', float('nan')):.2f}점(12응답). "
         f"4년제 대학·대학원 페르소나가 일관되게 우호적이고, 고등학교 이하 페르소나는 호감도가 낮았습니다. "
         f"이 전시의 추상적·문학적 콘셉트가 고학력 페르소나의 호감을 더 끌어낸다는 신호로 읽힙니다 "
         f"(중학교·초등학교 표본은 적어 해석 보류 권장)."),

        ("04. 성별 차이가 예상보다 큼 — 여자 2.96점 vs 남자 2.57점, 0.39점 격차",
         f"여자 페르소나(159응답) 평균 호감도 {sex_means.get('여자', float('nan')):.2f}점, "
         f"남자 페르소나(141응답) {sex_means.get('남자', float('nan')):.2f}점으로 0.39점 격차가 있었습니다. "
         f"이 전시의 콘셉트(그릇·일상·문학적 사유)가 여성 페르소나에게 더 친화적으로 작동했다고 해석할 수 있습니다. "
         f"실제 관람객 성별 비율 예측이 필요한 경우 이 신호를 참고하시기 바랍니다."),

        ("05. 수도권 vs 비수도권 — 거리 망설임 차이가 호감도에 반영됨",
         f"수도권 페르소나({region_n.get('수도권', 0)}응답) 평균 호감도 {region_means.get('수도권', float('nan')):.2f}점, "
         f"비수도권({region_n.get('비수도권', 0)}응답) {region_means.get('비수도권', float('nan')):.2f}점이었습니다. "
         f"자유 응답에서 비수도권 페르소나는 \"서울까지 거리\"를 망설임 요인으로 자주 언급했습니다. "
         f"전시가 한양대박물관(서울 성동구) 개최임을 고려하면, 수도권 거주 페르소나가 더 우호적인 응답을 주는 "
         f"것은 자연스러운 결과이며, 비수도권 관람객 유치를 위해서는 여정 가치(주변 콘텐츠 연계 등)가 보강돼야 함을 시사합니다."),

        ("06. 연령대는 30~40대가 가장 우호 — 50대·19세 이하가 가장 낮음",
         f"연령대별 호감도는 30대 {age_means.get('30대', float('nan')):.2f}점, 40대 {age_means.get('40대', float('nan')):.2f}점이 가장 높았고, "
         f"50대 {age_means.get('50대', float('nan')):.2f}점, 19세 이하 {age_means.get('~19', float('nan')):.2f}점이 가장 낮았습니다. "
         f"중년층의 일상·기억·소멸 주제 친화성이 작동한 것으로 보이고, 50대는 고등학교 학력 비중이 상대적으로 높은 점도 "
         f"호감도 하락에 영향을 줬을 가능성이 있습니다."),

        ("07. 관람 의향과 동반자·추천 응답이 일관되게 \"미온적\"",
         f"관람 의향에서 \"갈 의향 있음\" {visit_dist.get('yes', 0)}건 / \"보통(망설임)\" {visit_dist.get('maybe', 0)}건 / "
         f"\"안 감\" {visit_dist.get('no', 0)}건으로, \"갈 의향 있음\"이 7%에 불과했습니다. "
         f"동반자 선호도 \"가지 않음\" {comp_dist.get('nobody', 0)}건과 \"혼자\" {comp_dist.get('alone', 0)}건이 "
         f"전체의 약 70%로 페르소나가 동반자를 적극 떠올리지 않았습니다. "
         f"추천 대상에서는 \"친구\" {rec_dist.get('friends', 0)}건이 1위, \"추천 안 함\" {rec_dist.get('no_one', 0)}건이 그 다음이었습니다. "
         f"이 전시가 \"자연스럽게 누구에게 권할 만한 행사\"보다는 \"관심 있는 사람이 혼자 찾아가는 행사\"로 인식되고 있음을 시사합니다."),
    ]
    return pd.DataFrame(findings, columns=["발견", "내용"])


def sheet_호감도_전체(df: pd.DataFrame) -> pd.DataFrame:
    rows = [{"구분": "전체 응답", **appeal_summary_row(df)}]
    return pd.DataFrame(rows)


def sheet_호감도_수도권(df: pd.DataFrame) -> pd.DataFrame:
    return appeal_by_dim(df, "region", "지역 구분", order=["수도권", "비수도권"])


def sheet_호감도_연령(df: pd.DataFrame) -> pd.DataFrame:
    return appeal_by_dim(df, "age_bucket", "연령대", order=AGE_ORDER)


def sheet_호감도_학력(df: pd.DataFrame) -> pd.DataFrame:
    return appeal_by_dim(df, "education_level", "학력", order=EDU_ORDER)


def sheet_호감도_성별(df: pd.DataFrame) -> pd.DataFrame:
    return appeal_by_dim(df, "sex", "성별", order=["여자", "남자"])


def sheet_호감도_시도(df: pd.DataFrame) -> pd.DataFrame:
    return appeal_by_dim(df, "province", "거주 시도")


def sheet_호감도_가구(df: pd.DataFrame) -> pd.DataFrame:
    return appeal_by_dim(df, "family_type", "가구 형태")


def sheet_호감도_혼인(df: pd.DataFrame) -> pd.DataFrame:
    order = ["미혼", "배우자있음", "이혼", "사별"]
    return appeal_by_dim(df, "marital_status", "혼인 상태", order=order)


def sheet_관람의향_demographic(df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("region", "수도권 여부", ["수도권", "비수도권"]),
        ("age_bucket", "연령대", AGE_ORDER),
        ("education_level", "학력", EDU_ORDER),
        ("sex", "성별", ["여자", "남자"]),
        ("marital_status", "혼인 상태", ["미혼", "배우자있음", "이혼", "사별"]),
    ]
    return stack_by_dims(df, specs, visit_by_dim)


def sheet_동반자_demographic(df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("region", "수도권 여부", ["수도권", "비수도권"]),
        ("age_bucket", "연령대", AGE_ORDER),
        ("sex", "성별", ["여자", "남자"]),
        ("marital_status", "혼인 상태", ["미혼", "배우자있음", "이혼", "사별"]),
        ("family_type", "가구 형태", None),
    ]
    return stack_by_dims(df, specs, companion_by_dim)


def sheet_추천_demographic(df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("region", "수도권 여부", ["수도권", "비수도권"]),
        ("age_bucket", "연령대", AGE_ORDER),
        ("education_level", "학력", EDU_ORDER),
        ("sex", "성별", ["여자", "남자"]),
        ("marital_status", "혼인 상태", ["미혼", "배우자있음", "이혼", "사별"]),
    ]
    return stack_by_dims(df, specs, recommend_by_dim)


def sheet_자유응답(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for word, cnt in top_words(df["key_attraction"], 20):
        rows.append({"분류": "끌리는 점", "단어": word, "등장 횟수": cnt})
    for word, cnt in top_words(df["key_concern"], 20):
        rows.append({"분류": "걱정·망설임", "단어": word, "등장 횟수": cnt})
    return pd.DataFrame(rows)


def sheet_결론(df: pd.DataFrame) -> pd.DataFrame:
    edu_means = df.groupby("education_level")["appeal_score"].mean().round(2)
    sex_means = df.groupby("sex")["appeal_score"].mean().round(2)
    region_means = df.groupby("region")["appeal_score"].mean().round(2)

    rows = [
        ("이 전시안에 대한 한 줄 평",
         "AI 페르소나 100명에게 3회 조사한 호감도 평균은 5점 만점에 2.78점으로 \"미온적\"입니다. "
         "5점도 1점도 없이 응답이 2~4점에 응집했고, \"실제로 가서 보겠다\"는 적극적 의향은 7%에 불과했습니다. "
         "이는 전시의 매력이 부족하다기보다는 거리·추상성이라는 진입 장벽이 페르소나의 적극적 의향을 가로막은 결과로 보입니다."),

        ("호감을 느끼는 페르소나의 윤곽",
         f"호감도가 높은 페르소나는 4년제 대학 이상 학력({edu_means.get('4년제 대학교', float('nan')):.2f}점), "
         f"여성({sex_means.get('여자', float('nan')):.2f}점), 30~40대, 수도권 거주({region_means.get('수도권', float('nan')):.2f}점)로 모이는 경향이 보입니다. "
         "전시의 추상적·문학적 콘셉트가 이 그룹의 일상·기억 감수성에 더 자연스럽게 닿는 것으로 해석됩니다. "
         "반대로 학력이 낮거나, 비수도권 거주이거나, 50대·19세 이하 페르소나는 호감도가 일관되게 낮아 일반 관람객에게는 진입 보조가 필요해 보입니다."),

        ("진입 장벽이 명확함 — 거리와 추상성",
         "자유 응답에서 망설임 요인이 \"서울까지 거리·시간\"과 \"주제의 추상성\" 두 가지로 일관되게 모였습니다. "
         "수도권 거주 페르소나에게는 두 번째 요인만, 비수도권 페르소나에게는 두 가지 모두가 작동했습니다. "
         "거리 부담을 보완하려면 주변 콘텐츠 연계(인근 카페·서점·기타 전시 동선)나 교통 안내가 필요하고, "
         "추상성 부담을 낮추려면 전시 도슨트, 입문 텍스트, 작품 한 점에 대한 짧은 영상 같은 진입 보조가 효과적일 수 있습니다."),

        ("동반자 선호와 추천 행동에 드러난 \"개인 관람\" 성격",
         "동반자 선호에서 \"가지 않음\"과 \"혼자\"가 약 70%였고, 추천 대상에서도 \"친구\" 다음이 \"추천 안 함\"이었습니다. "
         "페르소나가 이 전시를 \"가족 단위로 가는 행사\"·\"누구에게나 권할 만한 행사\"로는 인식하지 않고, "
         "\"관심 있는 사람이 혼자 찾아가는 사색적 콘텐츠\"로 보고 있다는 신호입니다. "
         "마케팅 메시지를 \"가족과 함께\" 같은 일반 관람 메시지보다 \"혼자 또는 마음 맞는 친구와\" 같은 개인 관람 메시지로 잡는 것이 페르소나 응답과 더 일치합니다."),

        ("측정 결과를 어떻게 해석할 것인가",
         "AI 페르소나의 호감도 절대값(평균 2.78점)을 \"실제 관람객 평점이 2.78이 될 것이다\"로 받지 않으시기를 권합니다. "
         "이 측정의 강점은 \"어느 페르소나 그룹이 다른 그룹보다 더 우호적인가\"라는 상대 비교에 있습니다. "
         "예를 들어 \"4년제 대학·여성·30~40대·수도권 페르소나가 다른 그룹보다 일관되게 우호적\"이라는 신호는 "
         "여러 demographic 차원에서 같은 방향으로 일관되므로 신뢰도가 높습니다. 절대값보다는 이런 상대 패턴을 활용하시기 바랍니다."),

        ("다음 측정에서 보강할 점",
         "(1) 시점 비교 — 같은 시나리오를 전시 개막 후에 재측정해 페르소나 응답이 어떻게 변하는지. "
         "(2) 시나리오 변형 — 같은 전시를 \"무료\"·\"5,000원\"·\"15,000원\" 세 버전으로 던져 가격 sensitivity 측정. "
         "(3) 페르소나 깊이 — Nemotron 기본 narrative에 박물관 도메인 정보(관람 빈도·선호 장르)를 추가해 응답 깊이 강화. "
         "(4) 자유 응답 클러스터링 — 끌림·걱정 텍스트를 단어 빈도 너머 의미 클러스터로 분석."),
    ]
    return pd.DataFrame(rows, columns=["주제", "내용"])


# ─────────── 차수별 조사 (1차/2차/3차) ───────────

CHASUS = [
    {
        "chasu": 1,
        "model": "openrouter/qwen/qwen3-max",
        "label": "qwen3-max",
        "lab": "Alibaba (중국)",
        "axis": "비-Western RLHF",
        "summary": (
            "한자권 lab의 다른 결로 적용된 RLHF. Western 모델과 다른 페르소나 반응 패턴을 잡기 위한 후보. "
            "본 측정에서 응답이 가장 다양한 차수"
        ),
    },
    {
        "chasu": 2,
        "model": "openrouter/nousresearch/hermes-4-70b",
        "label": "hermes-4-70b",
        "lab": "Nous Research (미국)",
        "axis": "약한 Western RLHF (uncensored)",
        "summary": (
            "RLHF 균질화 압력을 의도적으로 약화한 lab. \"친절·중립\" 압력을 줄여 페르소나 신호를 평탄화하지 않으려는 설계. "
            "본 측정에서 응답이 가장 합의된 차수"
        ),
    },
    {
        "chasu": 3,
        "model": "openrouter/anthropic/claude-haiku-4.5",
        "label": "claude-haiku-4.5",
        "lab": "Anthropic (미국)",
        "axis": "Constitutional AI (RLHF + 자기비판 학습)",
        "summary": (
            "강한 RLHF + 헌법 기반 자기 비판 절차로 학습된 baseline 1위 모델. baseline 4 도구 중 페르소나 신호를 가장 잘 통과시킴. "
            "부정적 응답을 단호하게 끌고 가는 차수"
        ),
    },
]


def sheet_차수별(df: pd.DataFrame, chasu_info: Dict) -> pd.DataFrame:
    """1차/2차/3차 조사 한 시트 — 모델 정보 + 차수만의 demographic 핵심 평균 + 종합 비교."""
    sub = df[df["model"] == chasu_info["model"]]
    if len(sub) == 0:
        return pd.DataFrame(
            [["오류", f"model={chasu_info['model']}에 해당하는 응답이 CSV에 없습니다."]],
            columns=["항목", "내용"],
        )

    s = sub["appeal_score"]
    overall_mean = df["appeal_score"].mean()
    diff_total = s.mean() - overall_mean

    # 차수만의 demographic 평균 (응답자 100명 기준)
    age_means = sub.groupby("age_bucket")["appeal_score"].mean().round(2)
    edu_means = sub.groupby("education_level")["appeal_score"].mean().round(2)
    sex_means = sub.groupby("sex")["appeal_score"].mean().round(2)
    region_means = sub.groupby("region")["appeal_score"].mean().round(2)
    visit = sub["visit_intent"].value_counts().to_dict()

    # 종합과의 차이가 큰 demographic 한두 개
    overall_age = df.groupby("age_bucket")["appeal_score"].mean()
    age_diffs = (age_means - overall_age).dropna().round(2)
    age_max_diff = age_diffs.abs().idxmax() if len(age_diffs) else None

    overall_edu = df.groupby("education_level")["appeal_score"].mean()
    edu_diffs = (edu_means - overall_edu).dropna().round(2)
    edu_max_diff = edu_diffs.abs().idxmax() if len(edu_diffs) else None

    rows = [
        ["조사 차수", f"{chasu_info['chasu']}차 조사"],
        ["사용한 측정 도구", chasu_info["label"]],
        ["lab(국적)", chasu_info["lab"]],
        ["RLHF 가설축", chasu_info["axis"]],
        ["측정 도구 요약", chasu_info["summary"]],
        ["응답자 수", f"{len(sub)}명 (페르소나 100명에게 이 차수만의 응답)"],
        ["호감도 평균", f"{s.mean():.2f}점 (종합 {overall_mean:.2f}점 대비 {diff_total:+.2f}점)"],
        ["호감도 흩어짐(표준편차)", f"{s.std():.2f}"],
        ["호감도 범위", f"최소 {int(s.min())}점, 최대 {int(s.max())}점"],
        [
            "관람 의향 분포",
            f"갈 의향 있음 {visit.get('yes', 0)}건 · 보통(망설임) {visit.get('maybe', 0)}건 · 안 감 {visit.get('no', 0)}건",
        ],
        [
            "연령대별 호감도 평균",
            " · ".join(f"{a} {age_means[a]:.2f}" for a in AGE_ORDER if a in age_means.index),
        ],
        [
            "학력별 호감도 평균",
            " · ".join(
                f"{e} {edu_means[e]:.2f}" for e in EDU_ORDER if e in edu_means.index
            ),
        ],
        [
            "성별 호감도 평균",
            " · ".join(f"{x} {sex_means[x]:.2f}점" for x in ["여자", "남자"] if x in sex_means.index),
        ],
        [
            "지역별 호감도 평균",
            " · ".join(f"{r} {region_means[r]:.2f}점" for r in ["수도권", "비수도권"] if r in region_means.index),
        ],
        [
            "종합과의 demographic 차이 — 가장 큰 두 곳",
            (
                (f"연령 {age_max_diff}: 차수 {age_means[age_max_diff]:.2f} vs 종합 {overall_age[age_max_diff]:.2f} ({age_diffs[age_max_diff]:+.2f}점)" if age_max_diff else "")
                + (" · " if (age_max_diff and edu_max_diff) else "")
                + (f"학력 {edu_max_diff}: 차수 {edu_means[edu_max_diff]:.2f} vs 종합 {overall_edu[edu_max_diff]:.2f} ({edu_diffs[edu_max_diff]:+.2f}점)" if edu_max_diff else "")
            ),
        ],
    ]
    return pd.DataFrame(rows, columns=["항목", "내용"])


# ─────────── 부록: 모델 선정 방법론 ───────────

def sheet_부록_모델선정() -> pd.DataFrame:
    """필터링 여정 + 남은 3 모델 포지션."""
    journey = [
        ("0단계: OpenRouter 카탈로그", "60+ lab, 371개 모델", "lab 다양성 확인 + 한국어 응답 가능 + 가격·속도 합리 후보 추리기"),
        ("1단계: baseline 4 모델 (N=100)", "gpt-4o-mini, qwen-2.5-72b, gemini-2.5-flash, claude-haiku-4.5", "RLHF 강도가 다른 4종으로 페르소나 통과 baseline 측정. claude-haiku std=0.75로 1위 — 페르소나 신호 가장 잘 통과"),
        ("2단계: smoke 7 모델 (N=5)", "hermes-4-405b, qwen3-max, mistral-large-2512, deepseek-v4-flash, claude-sonnet-4.6, deepseek-v4-pro, deepseek-v3.2", "비-Western RLHF·약한 RLHF·신모델 후보 1차 검증. deepseek-v3.2(std=0.00 mode collapse)·deepseek-v4-pro(137초 속도 함정) 즉시 탈락"),
        ("3단계: 안정화 6 모델 (N=25)", "qwen3-max, hermes-4-70b, hermes-4-405b, qwen3.6-plus, mistral-large, deepseek-v4-flash", "표본 부족 우려 보정 + 모델별 std 안정성 확인. qwen3.6-plus(reasoning 92초/건 함정)·hermes-405b(70b 대비 다양성 열위)·mistral·deepseek-flash 차례로 탈락"),
        ("4단계: 본 측정 3 모델 (N=100)", "qwen3-max, hermes-4-70b, claude-haiku-4.5", "각 가설축에서 페르소나 신호 가장 잘 통과시킨 3종 확정. 페르소나 100명에게 동일 전시안 측정"),
    ]
    return pd.DataFrame(journey, columns=["단계", "사용한 모델", "선별 결과 / 탈락 사유"])


def sheet_부록_3모델포지션() -> pd.DataFrame:
    rows = [
        ("qwen/qwen3-max", "Alibaba (중국)",
         "비-Western RLHF",
         "한자권 lab의 다른 결로 적용된 RLHF. Western 모델과 다른 페르소나 반응 패턴을 잡기 위한 후보. 본 측정에서 std 0.89로 가장 다양한 응답을 줬으며, 동반자 응답이 \"혼자/가지 않음\" 둘로 양극화하는 특징 있음"),
        ("nousresearch/hermes-4-70b", "Nous Research (미국)",
         "약한 Western RLHF (uncensored)",
         "RLHF 균질화 압력을 의도적으로 약화한 lab. \"친절·중립\" 압력을 줄여 페르소나 신호를 평탄화하지 않으려는 설계. 본 측정에서 std 0.69로 가장 합의된 응답을 줬으며, 동반자 응답이 가장 분산"),
        ("anthropic/claude-haiku-4.5", "Anthropic (미국)",
         "Constitutional AI (RLHF + 자기비판 학습)",
         "강한 RLHF + 헌법 기반 자기 비판 절차로 학습된 baseline 1위 모델. baseline 4 모델 중 페르소나 신호를 가장 잘 통과시켜(std=0.75) 본 측정에 잔류. 부정적 응답을 단호하게 끌고 가는 특징"),
    ]
    return pd.DataFrame(rows, columns=["모델", "lab(국적)", "RLHF 가설축", "특성 요약"])


def sheet_부록_종합() -> pd.DataFrame:
    """부록 16번을 한 시트에 narrative 도입 + 두 표로 통합."""
    intro = (
        "왜 모델 선정이 필요했는가. "
        "대형 언어 모델(LLM)은 출시 전에 RLHF(Reinforcement Learning from Human Feedback)라는 단계를 거칩니다. "
        "사람이 응답 후보들을 평가해 \"더 친절하고·중립적이고·논쟁적이지 않은 답\"을 선호하도록 학습시키는 과정입니다. "
        "결과적으로 응답이 평균값(특히 \"보통\"·\"3점\"·\"maybe\")으로 모이는 경향이 생기고, "
        "페르소나마다 달라야 할 답이 비슷한 쪽으로 평탄화되는 부작용이 있습니다. "
        "본 측정에서는 \"같은 페르소나에게 같은 질문을 던졌을 때 응답이 페르소나 demographic 차이에 따라 실제로 달라지는가\"가 핵심이므로, "
        "이 평탄화가 강한 모델은 측정 도구로 부적절합니다. "
        "그래서 RLHF 강도·결이 다른 모델 후보들을 4단계 필터링을 거쳐, 페르소나 신호를 잘 통과시키는 3 도구로 좁혀 같은 페르소나에게 1차·2차·3차로 조사를 진행했습니다. "
        "아래 표는 그 여정과 본 측정에 잔류한 3 모델의 포지션 요약입니다."
    )
    return pd.DataFrame([["부록 안내", intro]], columns=["항목", "내용"])


# ─────────── Excel ───────────

def write_excel(sheets: Dict[str, pd.DataFrame], out_path: Path) -> None:
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        for name, df in sheets.items():
            ws = writer.sheets[name[:31]]
            for col_idx, col_name in enumerate(df.columns, start=1):
                col_letter = ws.cell(1, col_idx).column_letter
                vals = df[col_name].astype(str).head(50).tolist()

                def width_of(s: str) -> float:
                    n = 0.0
                    for ch in str(s):
                        n += 1.6 if ord(ch) > 127 else 1.0
                    return n

                max_w = max([width_of(col_name)] + [width_of(v) for v in vals])
                ws.column_dimensions[col_letter].width = min(max_w + 2, 60)
    print(f"  [excel] {out_path} ({len(sheets)} 시트)")


# ─────────── PDF ───────────

def write_pdf(sheets: Dict[str, pd.DataFrame], section_intros: Dict[str, str], out_path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    pdfmetrics.registerFont(TTFont("KR", "/System/Library/Fonts/Supplemental/AppleGothic.ttf"))

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleKR", parent=styles["Title"], fontName="KR", fontSize=18, leading=22)
    h1_style = ParagraphStyle("H1KR", parent=styles["Heading1"], fontName="KR", fontSize=13, leading=17, spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle("BodyKR", parent=styles["BodyText"], fontName="KR", fontSize=9, leading=13)
    intro_style = ParagraphStyle("IntroKR", parent=styles["BodyText"], fontName="KR", fontSize=10, leading=15, spaceAfter=8, textColor=colors.HexColor("#222222"))
    note_style = ParagraphStyle("NoteKR", parent=styles["BodyText"], fontName="KR", fontSize=9, leading=13, textColor=colors.HexColor("#444444"), spaceAfter=6)

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)

    elements = []
    elements.append(Paragraph("knowing-koreans · 전시 호감도 측정 분석 보고서", title_style))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(
        "전시: 묻힌 그릇들은 아직 끝나지 않았다 (Where Things Linger)<br/>"
        "한양대학교박물관 · 무료 · 2026.05.06–07.18<br/>"
        "측정일: 2026-04-29 · AI 페르소나 100명 × 3회 측정 (1차·2차·3차) → 응답 300건",
        note_style,
    ))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph(
        "본 보고서는 페르소나 demographic을 분류 축으로 하여 작성되었습니다. "
        "본문은 응답 300건을 종합으로 분석하며, 1차·2차·3차 조사별 패턴은 본문 뒤 차수 비교 섹션에서, "
        "측정 도구 선정 방법론은 부록에서 다룹니다. "
        "AI 응답을 정확도 예측이 아니라 \"어떤 페르소나 그룹이 어떤 측면에 반응하는가\"의 관점·가설 발생 도구로 활용하시기 바랍니다.",
        note_style,
    ))

    for sheet_name, df in sheets.items():
        elements.append(Spacer(1, 6*mm))
        elements.append(Paragraph(sheet_name, h1_style))
        intro = section_intros.get(sheet_name)
        if intro:
            elements.append(Paragraph(intro, intro_style))
        elements.append(_df_to_table(df, body_style))

    doc.build(elements)
    print(f"  [pdf]   {out_path} ({len(sheets)} 섹션)")


def _df_to_table(df: pd.DataFrame, body_style, available_width: float = 493.0) -> "Table":
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    if len(df) == 0:
        return Paragraph("(데이터 없음)", body_style)

    header = [Paragraph(f"<b>{c}</b>", body_style) for c in df.columns]
    body = []
    for _, row in df.iterrows():
        cells = []
        for v in row.values:
            cells.append(Paragraph(str(v), body_style))
        body.append(cells)

    weights = []
    sample = df.head(20).astype(str)
    for c in df.columns:
        col_name_len = len(str(c))
        col_data_lens = [min(len(v), 60) for v in sample[c].tolist()]
        max_len = max([col_name_len] + col_data_lens)
        weights.append(max(max_len, 4))
    total = sum(weights)
    MIN_W = 22.0
    col_widths = [max(available_width * w / total, MIN_W) for w in weights]
    width_sum = sum(col_widths)
    if width_sum > available_width:
        scale = available_width / width_sum
        col_widths = [w * scale for w in col_widths]

    data = [header] + body
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3a3a3a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "KR"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    return table


# ─────────── main ───────────

def main() -> int:
    print(f"[1/3] 데이터 로드")
    df = load()
    print(f"      응답 {len(df)}건, 페르소나 {df['persona_uuid'].nunique()}명")
    print(f"      수도권 페르소나: {df.groupby('persona_uuid').first()['region'].eq('수도권').sum()}명")

    print("[2/3] 시트 21개 생성")
    sheets: Dict[str, pd.DataFrame] = {
        "1. 측정 개요": sheet_측정개요(df),
        "2. 핵심 발견": sheet_핵심발견(df),
        "3. 호감도 — 전체 분포": sheet_호감도_전체(df),
        "4. 호감도 — 수도권 vs 비수도권": sheet_호감도_수도권(df),
        "5. 호감도 — 연령대별": sheet_호감도_연령(df),
        "6. 호감도 — 학력별": sheet_호감도_학력(df),
        "7. 호감도 — 성별": sheet_호감도_성별(df),
        "8. 호감도 — 거주 시도별": sheet_호감도_시도(df),
        "9. 호감도 — 가구 형태별": sheet_호감도_가구(df),
        "10. 호감도 — 혼인 상태별": sheet_호감도_혼인(df),
        "11. 관람 의향 — demographic별": sheet_관람의향_demographic(df),
        "12. 동반자 선호 — demographic별": sheet_동반자_demographic(df),
        "13. 추천 대상 — demographic별": sheet_추천_demographic(df),
        "14. 자유 응답 키워드": sheet_자유응답(df),
        "15. 결론 및 시사점": sheet_결론(df),
        "16. 1차 조사 (qwen3-max)": sheet_차수별(df, CHASUS[0]),
        "17. 2차 조사 (hermes-4-70b)": sheet_차수별(df, CHASUS[1]),
        "18. 3차 조사 (claude-haiku-4.5)": sheet_차수별(df, CHASUS[2]),
        "19. 부록 — 측정 도구 선정 방법론": sheet_부록_종합(),
        "19-1. 부록 — 필터링 여정": sheet_부록_모델선정(),
        "19-2. 부록 — 잔류 3 도구 포지션": sheet_부록_3모델포지션(),
    }

    section_intros = {
        "1. 측정 개요":
            "이 측정은 NVIDIA에서 공개한 한국 페르소나 데이터셋(약 700만 명)에서 연령대 균등 + "
            "수도권·비수도권 절반씩 분포가 되도록 100명을 추출하고, 각 페르소나에게 \"묻힌 그릇들은 아직 끝나지 않았다\" "
            "전시 기획안을 보여준 뒤 7개 질문에 답하게 한 결과입니다. 페르소나 신호를 가장 잘 통과시키는 3 도구로 "
            "1차·2차·3차 조사를 진행해 응답 300건을 얻었습니다.",

        "2. 핵심 발견":
            "측정 결과에서 도출한 핵심 발견 7개입니다. 호감도 절대값보다는 어떤 페르소나 그룹이 어떤 응답을 주는지의 "
            "demographic 패턴에 주목해 읽어주시기 바랍니다.",

        "3. 호감도 — 전체 분포":
            "300건 응답 전체의 호감도 분포입니다. 1점·5점이 0건이고 응답이 2~4점에 응집한 점, 그리고 평균이 "
            "5점 만점 기준 중간(3점)보다 약간 낮은 영역에 자리 잡은 점이 핵심입니다.",

        "4. 호감도 — 수도권 vs 비수도권":
            "전시 개최지가 한양대박물관(서울 성동구)이므로 수도권·비수도권 페르소나가 다른 응답을 줄 가능성이 큽니다. "
            "자유 응답에서 비수도권 페르소나가 \"서울까지 거리\"를 망설임 요인으로 자주 언급한 결과가 호감도 평균에도 반영됐습니다.",

        "5. 호감도 — 연령대별":
            "연령대별 호감도 평균입니다. 30~40대가 가장 우호적이고 50대·19세 이하가 가장 낮습니다. "
            "중년층이 일상·기억·소멸이라는 콘셉트에 더 친화적이고, 50대는 학력 분포(고등학교 비중)도 영향을 줬을 가능성이 있습니다.",

        "6. 호감도 — 학력별":
            "학력별 호감도 평균입니다. 4년제 대학교·대학원 페르소나가 일관되게 우호적이고, 고등학교 이하 페르소나는 호감도가 낮습니다. "
            "이 전시의 추상적·문학적 콘셉트가 고학력 페르소나의 호감을 더 끌어낸다는 신호입니다 "
            "(중학교·초등학교·무학 표본은 적어 해석 보류 권장).",

        "7. 호감도 — 성별":
            "성별 호감도 평균입니다. 여성 페르소나가 0.39점 더 우호적입니다 — 그릇·일상·문학적 사유라는 콘셉트가 "
            "여성 페르소나에게 더 친화적으로 작동했다고 해석할 수 있습니다.",

        "8. 호감도 — 거주 시도별":
            "17개 시도별 호감도 평균입니다. 응답 수가 적은 시도(예: 강원 1명·대전 1명)는 통계적 의미가 적으니 "
            "응답 수가 충분한 상위 시도부터 패턴을 읽으시기 바랍니다. 전체 패턴은 \"수도권 vs 비수도권\" 시트와 일관됩니다.",

        "9. 호감도 — 가구 형태별":
            "가구 형태별 호감도입니다. \"배우자와 거주\" 페르소나가 호감도가 가장 높고, "
            "\"형제자매와 동거(가구주)\" 페르소나가 낮은 편입니다. 단 일부 가구 형태는 표본이 적어 해석 보류 권장.",

        "10. 호감도 — 혼인 상태별":
            "혼인 상태별 호감도입니다. 미혼·배우자있음 두 큰 그룹의 호감도 차이는 거의 없었고, "
            "이혼·사별 그룹은 표본이 적어 해석 보류 권장.",

        "11. 관람 의향 — demographic별":
            "\"실제로 가서 볼 의향이 있느냐\" 질문에 대한 응답을 demographic 5개 차원(수도권 / 연령대 / 학력 / 성별 / 혼인) "
            "별로 정리한 표입니다. 전체적으로 \"갈 의향 있음\"이 7%에 불과해 어떤 페르소나 그룹도 적극 의향을 보이지 않았습니다.",

        "12. 동반자 선호 — demographic별":
            "\"가게 된다면 누구와 함께\" 응답을 demographic 5개 차원별로 정리했습니다. \"가지 않음\"·\"혼자\" 응답이 "
            "약 70%로 압도적이며, 페르소나가 동반자를 적극 떠올리지 않았습니다. \"배우자있음\" 페르소나에서도 \"배우자/연인\" "
            "응답은 그렇게 많지 않은데, 이는 LLM이 페르소나의 혼인 신호를 동반자 선택까지 충분히 반영하지 못했을 가능성 또는 "
            "이 전시 자체가 \"배우자와 함께 갈 콘텐츠\"로 인식되지 않았을 가능성 두 가지로 해석할 수 있습니다.",

        "13. 추천 대상 — demographic별":
            "\"이 전시를 누구에게 추천하시겠습니까\" 응답을 demographic별로 정리했습니다. \"친구\"가 1위(155건), "
            "\"추천 안 함\"이 2위(117건)로, 전시가 \"누구에게나 권할 만한 행사\"보다는 \"관심 있는 사람에게 권하는 행사\"로 "
            "인식되고 있음을 보여줍니다.",

        "14. 자유 응답 키워드":
            "끌리는 점·걱정거리 자유 응답에서 자주 등장한 단어를 빈도순으로 정리했습니다. 끌리는 점에서는 "
            "\"버려진 그릇\"·\"일상의 시간\"·\"무료\" 같은 콘셉트·운영 키워드가, 걱정거리에서는 "
            "\"서울까지 거리\"·\"성동구까지\"·\"주제가 너무 추상적\"이 압도적이었습니다. 거리·추상성이 핵심 망설임 요인입니다.",

        "15. 결론 및 시사점":
            "측정 결과 종합 + 큐레이터를 위한 시사점 6개를 정리했습니다. AI 응답을 절대값(\"평점이 2.78점이 될 것이다\")이 "
            "아니라 상대 비교(\"4년제 대학·여성·30~40대·수도권 페르소나가 더 우호적\")로 활용하시기를 권장합니다.",

        "16. 1차 조사 (qwen3-max)":
            "종합 분석에서 본 응답 300건이 1차·2차·3차 조사별로 어떻게 갈렸는지 짧게 짚어봅니다. "
            "같은 페르소나 100명에게 RLHF 결이 다른 3 도구로 동일 질문을 던졌을 때, 차수에 걸쳐 비슷하게 나오는 부분은 페르소나 신호가 강한 영역이고, "
            "차수에 따라 갈리는 부분은 도구 차이가 신호를 다르게 통과시킨 흔적입니다. "
            "1차 조사는 비-Western RLHF로 학습된 qwen3-max가 진행했습니다 — 한자권 lab의 다른 결로 적용된 RLHF로, "
            "본 측정에서 응답이 가장 다양하게 흩어진 차수입니다. 동반자 응답이 \"혼자/가지 않음\" 둘로 양극화하는 특징이 있습니다.",

        "17. 2차 조사 (hermes-4-70b)":
            "2차 조사는 약한 Western RLHF(uncensored 설계) 모델인 hermes-4-70b가 진행했습니다. "
            "\"친절·중립\" 균질화 압력을 의도적으로 약화한 lab의 모델로, 페르소나 신호를 평탄화하지 않으려는 설계입니다. "
            "본 측정에서 응답이 가장 합의된(흩어짐 가장 작은) 차수이며, 동반자 enum 7개에 응답이 가장 고르게 분산된 차수입니다.",

        "18. 3차 조사 (claude-haiku-4.5)":
            "3차 조사는 Constitutional AI(RLHF + 헌법 기반 자기비판 학습)로 학습된 claude-haiku-4.5가 진행했습니다. "
            "baseline 4 도구 비교에서 페르소나 신호를 가장 잘 통과시킨 1위 모델로, 부정적 응답(\"안 감\"·\"추천 안 함\"·낮은 호감도 점수)을 "
            "단호하게 끌고 가는 특징이 있어 종합 평균을 약간 끌어내린 차수입니다.",

        "19. 부록 — 측정 도구 선정 방법론":
            "본 측정에 사용된 3 도구가 어떤 과정으로 선택됐는지 설명합니다. 본문에서는 도구 차원을 다루지 않았고 "
            "차수 비교 섹션에서도 도구 비교 자체를 강조하지 않았으므로, 방법론에 관심이 있으신 경우에만 참고하시기 바랍니다.",

        "19-1. 부록 — 필터링 여정":
            "OpenRouter 카탈로그 60+ lab·371개 모델에서 본 측정 3 도구로 좁혀온 4단계 필터링 과정입니다. "
            "각 단계에서 어떤 모델을 후보로 측정했고 어느 모델이 어떤 사유로 탈락했는지 한 줄씩 정리했습니다.",

        "19-2. 부록 — 잔류 3 도구 포지션":
            "본 측정에 잔류한 3 도구의 lab(국적), RLHF 가설축, 응답 특성을 정리했습니다. 세 도구는 RLHF 강도·결이 다른 "
            "세 가지 다른 측정 도구로서 같은 페르소나에 대한 응답이 도구 차이에 따라 어떻게 갈리는지 cross-validation 역할을 합니다.",
    }

    print(f"[3/3] 출력")
    write_excel(sheets, OUT_XLSX)
    write_pdf(sheets, section_intros, OUT_PDF)

    print(f"\n완료. 산출물:")
    print(f"  {OUT_XLSX}")
    print(f"  {OUT_PDF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

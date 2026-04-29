"""
페르소나 샘플러 — NVIDIA Nemotron-Personas-Korea

parquet 9샤드를 로드해 시드 고정 샘플링. 단순 random + demographic
filter + stratified 모두 지원.

재현성 위해 seed / filter / stratify 정보를 결과 DataFrame에 같이 기록.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional, Sequence, Union

import pandas as pd

DEFAULT_DATASET_DIR = Path(__file__).parent / "nvidia-personas"
DEFAULT_REPO_ID = "nvidia/Nemotron-Personas-Korea"

AGE_BUCKETS = [
    (0, 19, "~19"),
    (20, 29, "20대"),
    (30, 39, "30대"),
    (40, 49, "40대"),
    (50, 59, "50대"),
    (60, 200, "60+"),
]


def add_age_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """age 컬럼 → age_bucket 추가. 1M행에서도 메모리 압박 없이 동작."""
    if "age_bucket" in df.columns:
        return df
    bins = [b[0] for b in AGE_BUCKETS] + [AGE_BUCKETS[-1][1] + 1]
    labels = [b[2] for b in AGE_BUCKETS]
    age_bucket = pd.cut(
        df["age"], bins=bins, labels=labels, right=False, include_lowest=True
    )
    return df.assign(age_bucket=age_bucket)


def _normalize_str_list(v: Union[None, str, Sequence[str]]) -> Optional[List[str]]:
    if v is None:
        return None
    if isinstance(v, str):
        items = [s.strip() for s in v.split(",") if s.strip()]
    else:
        items = [str(s).strip() for s in v if str(s).strip()]
    return items or None


def apply_filters(
    df: pd.DataFrame,
    *,
    province: Union[None, str, Sequence[str]] = None,
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    sex: Union[None, str, Sequence[str]] = None,
    education_level: Union[None, str, Sequence[str]] = None,
    occupation: Union[None, str, Sequence[str]] = None,
) -> pd.DataFrame:
    """demographic 필터 적용. None 인자는 무시."""
    out = df
    prov_list = _normalize_str_list(province)
    if prov_list:
        out = out[out["province"].isin(prov_list)]
    if age_min is not None:
        out = out[out["age"] >= age_min]
    if age_max is not None:
        out = out[out["age"] <= age_max]
    sex_list = _normalize_str_list(sex)
    if sex_list:
        out = out[out["sex"].isin(sex_list)]
    edu_list = _normalize_str_list(education_level)
    if edu_list:
        out = out[out["education_level"].isin(edu_list)]
    occ_list = _normalize_str_list(occupation)
    if occ_list:
        out = out[out["occupation"].isin(occ_list)]
    return out


def download_dataset(
    local_dir: Path = DEFAULT_DATASET_DIR,
    repo_id: str = DEFAULT_REPO_ID,
) -> Path:
    """HF에서 데이터셋을 받는다. 이미 받은 게 있으면 캐시로 즉시 반환."""
    from huggingface_hub import snapshot_download

    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=str(local_dir),
        allow_patterns=["data/*.parquet", "README.md"],
    )
    return local_dir


def load_all_personas(local_dir: Path = DEFAULT_DATASET_DIR) -> pd.DataFrame:
    """9샤드 parquet 전체를 DataFrame으로 합쳐 반환.

    주의: 1M demographic × 7 narrative = 7M rows. 메모리 사용 큼.
    M3 이후 층화 표집·필터링 도입 시 chunk 단위 로드로 변경.
    """
    local_dir = Path(local_dir)
    data_dir = local_dir / "data"
    parquet_files = sorted(data_dir.glob("train-*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(
            f"parquet 샤드를 찾을 수 없음: {data_dir}. "
            "download_dataset()을 먼저 실행하세요."
        )
    dfs = [pd.read_parquet(p) for p in parquet_files]
    return pd.concat(dfs, ignore_index=True)


def sample_personas(
    n: int,
    seed: int,
    df: Optional[pd.DataFrame] = None,
    *,
    province: Union[None, str, Sequence[str]] = None,
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    sex: Union[None, str, Sequence[str]] = None,
    education_level: Union[None, str, Sequence[str]] = None,
    occupation: Union[None, str, Sequence[str]] = None,
    stratify_by: Optional[str] = None,
) -> pd.DataFrame:
    """시드 고정 샘플링. demographic filter + stratified 지원.

    Args:
        n: 최종 샘플 수
        seed: pandas random_state로 전달되는 정수 시드
        df: 미리 로드된 DataFrame. 없으면 load_all_personas()
        province: 시도 필터 ("서울" / ["서울", "경기"] / "서울,경기")
        age_min, age_max: 나이 범위 (둘 중 하나만 줘도 됨)
        sex: 성별 필터 ("남자" 또는 "여자")
        education_level: 학력 필터
        occupation: 직업 필터 (정확히 일치)
        stratify_by: 균등 추출 기준 컬럼 ("age_bucket", "province", "sex" 등).
                     pool을 group으로 나눠 N/group 만큼씩 추출.
                     끝수는 첫 group들이 1씩 더 가져감.

    Returns:
        샘플링된 DataFrame. _sample_seed 컬럼 추가.
        age 컬럼이 있으면 age_bucket 컬럼도 같이 추가.
        persona_uuid 없으면 결정론적으로 생성.
    """
    if df is None:
        df = load_all_personas()

    pool = apply_filters(
        df,
        province=province,
        age_min=age_min,
        age_max=age_max,
        sex=sex,
        education_level=education_level,
        occupation=occupation,
    )
    if len(pool) == 0:
        raise ValueError("필터 조건 만족하는 페르소나 0건 — 필터 완화 필요")
    if n > len(pool):
        raise ValueError(
            f"요청 샘플 수 {n}이 필터 적용 후 가용 {len(pool)}건보다 큼"
        )

    if stratify_by:
        if stratify_by == "age_bucket" and "age_bucket" not in pool.columns:
            pool = add_age_bucket(pool)
        if stratify_by not in pool.columns:
            raise ValueError(f"stratify_by 컬럼 없음: {stratify_by}")
        # groupby().indices: dict {그룹값: ndarray of integer locations} — 큰 DF에서도 O(n)에 그침
        idx_by_group = pool.groupby(stratify_by, observed=True).indices
        # 그룹 순서 결정: age_bucket는 정의된 순, 그 외는 정렬
        groups = (
            [b[2] for b in AGE_BUCKETS if b[2] in idx_by_group]
            if stratify_by == "age_bucket"
            else sorted([g for g in idx_by_group.keys() if g == g])  # NaN 제거
        )
        if not groups:
            raise ValueError(f"stratify_by={stratify_by}에 그룹이 없음")
        per = n // len(groups)
        rem = n - per * len(groups)
        import numpy as np

        chosen_locs = []
        for i, g in enumerate(groups):
            locs = idx_by_group[g]
            take = per + (1 if i < rem else 0)
            take = min(take, len(locs))
            if take > 0:
                rng = np.random.RandomState(seed + i)
                chosen_locs.extend(rng.choice(locs, size=take, replace=False))
        rng_final = np.random.RandomState(seed)
        rng_final.shuffle(chosen_locs)
        sampled = pool.iloc[chosen_locs].reset_index(drop=True)
    else:
        sampled = pool.sample(n=n, random_state=seed).reset_index(drop=True)

    if "persona_uuid" not in sampled.columns:
        sampled["persona_uuid"] = [
            str(uuid.uuid5(uuid.NAMESPACE_DNS, f"nemotron-{seed}-{i}"))
            for i in range(len(sampled))
        ]
    sampled = add_age_bucket(sampled)
    sampled["_sample_seed"] = seed
    return sampled


if __name__ == "__main__":
    import sys

    print("[1/3] 데이터셋 다운로드 (이미 있으면 캐시)...")
    local_dir = download_dataset()
    print(f"      위치: {local_dir}")

    print("[2/3] 전체 페르소나 로드...")
    df = load_all_personas()
    print(f"      전체 행: {len(df):,}")
    print(f"      컬럼 ({len(df.columns)}): {list(df.columns)}")

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    print(f"[3/3] 샘플링 (n={n}, seed={seed})...")
    sample = sample_personas(n=n, seed=seed, df=df)
    for i, row in sample.iterrows():
        print(f"\n--- 페르소나 {i+1} ---")
        for col in sample.columns:
            val = row[col]
            if isinstance(val, str) and len(val) > 120:
                val = val[:117] + "..."
            print(f"  {col}: {val}")

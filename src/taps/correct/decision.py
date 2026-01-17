"""
의사결정 레이어 (가드레일 + 임계치)

implementation_contract_v1.md 임계치 적용:
- U1: 항상 NEEDS_REVIEW
- N3: GREEN/YELLOW + margin>=0.25 + change_ratio<=0.20 → AUTO_FIX
- E2: GREEN + margin>=0.35 + change_ratio<=0.15 + no mixed-script → AUTO_FIX
- STW_CANON: GREEN + no U1 + change_ratio<=0.18 → AUTO_FIX

공통 가드레일:
- change_ratio > 0.35 → NEEDS_REVIEW (의미 변형 위험)
- 빈 출력 / 기호만 출력 → NEEDS_REVIEW
"""

import re
from typing import List

from .models import RiskTag, Bucket, Action, Candidate

# =============================================================================
# 임계치 상수 (implementation_contract_v1.md 기준)
# =============================================================================

# 공통 가드레일
MAX_CHANGE_RATIO_GLOBAL = 0.35  # 이 이상이면 무조건 검수

# N3 (숫자) 임계치
N3_ALLOWED_BUCKETS = ("GREEN", "YELLOW")
N3_MIN_MARGIN = 0.25
N3_MAX_CHANGE_RATIO = 0.20

# E2 (영문) 임계치 - 매우 보수적
E2_ALLOWED_BUCKETS = ("GREEN",)
E2_MIN_MARGIN = 0.35
E2_MAX_CHANGE_RATIO = 0.15

# STW_CANON (문장 전체) 임계치
CANON_ALLOWED_BUCKETS = ("GREEN",)
CANON_MAX_CHANGE_RATIO = 0.18


# =============================================================================
# 핵심 함수
# =============================================================================

def normalized_edit_distance(a: str, b: str) -> float:
    """
    정규화된 편집 거리 (0~1)

    rapidfuzz 사용 (속도 + 정확성)

    Args:
        a: 문자열 A
        b: 문자열 B

    Returns:
        float: 0 (동일) ~ 1 (완전히 다름)
    """
    if not a and not b:
        return 0.0

    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0

    try:
        from rapidfuzz.distance import Levenshtein
        dist = Levenshtein.distance(a, b)
    except ImportError:
        # rapidfuzz 없으면 순수 Python 구현 사용
        dist = _levenshtein_distance(a, b)

    return dist / max_len


def _levenshtein_distance(a: str, b: str) -> int:
    """순수 Python Levenshtein 거리 (rapidfuzz fallback)"""
    if len(a) < len(b):
        a, b = b, a

    if len(b) == 0:
        return len(a)

    prev_row = list(range(len(b) + 1))

    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (ca != cb)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def compute_margin(candidates: List[Candidate]) -> float:
    """
    Top-1과 Top-2 점수 차이 (margin)

    Args:
        candidates: 점수 내림차순 정렬된 후보 리스트

    Returns:
        float: margin 값 (후보가 1개면 무한대 처리로 1.0 반환)
    """
    if len(candidates) < 2:
        return 1.0  # 후보가 1개면 margin 최대

    return candidates[0].score - candidates[1].score


def has_mixed_script(text: str) -> bool:
    """
    한글-영문 혼종 여부

    Args:
        text: 검사할 텍스트

    Returns:
        bool: 한글과 영문이 모두 포함되어 있으면 True
    """
    has_hangul = bool(re.search(r"[가-힣]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    return has_hangul and has_latin


def is_empty_or_symbols_only(text: str) -> bool:
    """
    빈 문자열 또는 기호만 있는지 확인

    Args:
        text: 검사할 텍스트

    Returns:
        bool: 빈 문자열이거나 기호/공백만 있으면 True
    """
    stripped = text.strip()
    if not stripped:
        return True

    # 기호/공백만 있는 경우
    if re.fullmatch(r"[\s.,!?;:\-_\'\"()\[\]{}]+", stripped):
        return True

    return False


# =============================================================================
# 의사결정 함수
# =============================================================================

def decide_action(
    tag: RiskTag,
    bucket: Bucket,
    candidates: List[Candidate],
    raw_span_or_sentence: str,
    recommended: str,
    is_url_present_in_sentence: bool,
) -> Action:
    """
    스팬 단위 의사결정: AUTO_FIX / NEEDS_REVIEW / PASS

    Args:
        tag: 위험 태그 (N3/E2/U1/OOV)
        bucket: 트리아지 버킷 (RED/ORANGE/YELLOW/GREEN)
        candidates: BTC 후보 리스트
        raw_span_or_sentence: 원본 스팬/문장
        recommended: 추천 텍스트 (top-1 후보)
        is_url_present_in_sentence: 문장에 URL 스팬 존재 여부

    Returns:
        Action: AUTO_FIX / NEEDS_REVIEW / PASS
    """
    # 공통 메트릭 계산
    change_ratio = normalized_edit_distance(raw_span_or_sentence, recommended)
    margin = compute_margin(candidates)

    # === 공통 가드레일 ===

    # 가드레일 1: 빈 출력 / 기호만
    if is_empty_or_symbols_only(recommended):
        return "NEEDS_REVIEW"

    # 가드레일 2: change_ratio > 0.35 (의미 변형 위험)
    if change_ratio > MAX_CHANGE_RATIO_GLOBAL:
        return "NEEDS_REVIEW"

    # === 태그별 결정 ===

    # U1: 항상 NEEDS_REVIEW (자동 확정 금지)
    if tag == "U1":
        return "NEEDS_REVIEW"

    # N3: 숫자 자동 확정 조건
    if tag == "N3":
        if bucket in N3_ALLOWED_BUCKETS:
            if margin >= N3_MIN_MARGIN and change_ratio <= N3_MAX_CHANGE_RATIO:
                return "AUTO_FIX"
        return "NEEDS_REVIEW"

    # E2: 영문 자동 확정 조건 (매우 보수적)
    if tag == "E2":
        if bucket in E2_ALLOWED_BUCKETS:
            if margin >= E2_MIN_MARGIN and change_ratio <= E2_MAX_CHANGE_RATIO:
                # 혼종 스크립트 새로 생기면 거부
                raw_mixed = has_mixed_script(raw_span_or_sentence)
                rec_mixed = has_mixed_script(recommended)
                if not rec_mixed or raw_mixed:
                    return "AUTO_FIX"
        return "NEEDS_REVIEW"

    # OOV: v1에서는 자동 확정 금지
    if tag == "OOV":
        return "NEEDS_REVIEW"

    # 기본: PASS (변경 없음)
    return "PASS"


def decide_sentence_action(
    bucket: Bucket,
    text_raw: str,
    text_canonical: str,
    has_url_span: bool,
) -> Action:
    """
    문장 전체(STW_CANON) 자동 확정 여부

    Args:
        bucket: 트리아지 버킷
        text_raw: 원본 문장
        text_canonical: BTC 출력 (canonical)
        has_url_span: 문장 내 URL 스팬 존재 여부

    Returns:
        Action: AUTO_FIX / NEEDS_REVIEW
    """
    # 조건 1: GREEN만
    if bucket not in CANON_ALLOWED_BUCKETS:
        return "NEEDS_REVIEW"

    # 조건 2: U1 스팬 없을 것
    if has_url_span:
        return "NEEDS_REVIEW"

    # 조건 3: change_ratio <= 0.18
    change_ratio = normalized_edit_distance(text_raw, text_canonical)
    if change_ratio <= CANON_MAX_CHANGE_RATIO:
        return "AUTO_FIX"

    return "NEEDS_REVIEW"


# =============================================================================
# 테스트용
# =============================================================================

if __name__ == "__main__":
    print("Decision Layer 테스트")
    print("=" * 50)

    # normalized_edit_distance 테스트
    test_pairs = [
        ("hello", "hello"),  # 0.0
        ("hello", "hallo"),  # 0.2
        ("hello", "world"),  # 0.8
        ("일이삼사", "1234"),  # 높음
    ]

    print("\n1) normalized_edit_distance:")
    for a, b in test_pairs:
        dist = normalized_edit_distance(a, b)
        print(f"  '{a}' vs '{b}' = {dist:.3f}")

    # decide_action 테스트
    print("\n2) decide_action:")

    # U1은 항상 NEEDS_REVIEW
    action = decide_action(
        tag="U1",
        bucket="GREEN",
        candidates=[Candidate("www.example.com", 0.9)],
        raw_span_or_sentence="더블유더블유더블유",
        recommended="www.example.com",
        is_url_present_in_sentence=True,
    )
    print(f"  U1 + GREEN = {action} (expected: NEEDS_REVIEW)")

    # N3 + GREEN + 좋은 조건
    action = decide_action(
        tag="N3",
        bucket="GREEN",
        candidates=[Candidate("1234", 0.9), Candidate("1 2 3 4", 0.5)],
        raw_span_or_sentence="일이삼사",
        recommended="1234",
        is_url_present_in_sentence=False,
    )
    print(f"  N3 + GREEN + good margin = {action} (expected: AUTO_FIX)")

    # N3 + RED = NEEDS_REVIEW
    action = decide_action(
        tag="N3",
        bucket="RED",
        candidates=[Candidate("1234", 0.9), Candidate("1 2 3 4", 0.5)],
        raw_span_or_sentence="일이삼사",
        recommended="1234",
        is_url_present_in_sentence=False,
    )
    print(f"  N3 + RED = {action} (expected: NEEDS_REVIEW)")

"""
스팬 탐지 모듈 (규칙 기반)

태그:
- N3: 숫자 (아라비아 숫자 + 한글 숫자)
- E2: 영문/알파벳
- U1: URL/도메인
- OOV: 사전 외 단어 (v1에서는 defer)

규칙은 "탐지 전용" - 직접 교정하지 않음
"""

import re
from typing import List

from .models import Span, RiskTag

# =============================================================================
# 정규식 패턴
# =============================================================================

# N3: 숫자 패턴
# 아라비아 숫자 (1,234 / 3.14 / 010-1234-5678 등 포함)
RE_DIGIT_RUN = re.compile(
    r"\d[\d,.\-]*\d|\d"  # 최소 1자리 숫자, 콤마/점/하이픈 포함 가능
)

# 한글 숫자 (일이삼사 등) - 최소 2자 이상
RE_KR_NUMBER = re.compile(
    r"[일이삼사오육칠팔구십백천만억조영공빵]+"
)

# 숫자 문맥 단서 (뒤에 붙는 단위/조사)
NUMBER_CONTEXT_SUFFIXES = [
    "개", "명", "원", "년", "월", "일", "시", "분", "초",
    "번", "회", "차", "층", "호", "반", "등", "위",
    "살", "세", "대", "배", "퍼센트", "%",
    "킬로", "미터", "센티", "그램", "리터",
    "을", "를", "이", "가", "은", "는", "의", "에", "와", "과",
]

# 숫자 문맥 단서 (앞에 오는 키워드) - 결함 B 해결
NUMBER_CONTEXT_PREFIX_KEYWORDS = [
    "인증번호", "비밀번호", "코드", "OTP", "일회용",
    "계좌번호", "주민번호", "학번", "사번", "전화번호",
    "핀번호", "PIN", "패스워드", "암호", "번호",
    "카드번호", "주문번호", "예약번호", "등록번호",
]

# E2: 영문 패턴 (2글자 이상)
RE_ENGLISH = re.compile(r"[A-Za-z]{2,}")

# E2: 혼합 알파뉴메릭 (COVID19, KDH123 등)
RE_ALNUM_MIXED = re.compile(r"[A-Za-z]+\d+[A-Za-z\d]*|\d+[A-Za-z]+[A-Za-z\d]*")

# U1: URL/도메인 패턴
# 실제 URL
RE_URL_ACTUAL = re.compile(
    r"https?://[^\s]+|"  # http(s)://
    r"www\.[^\s]+|"  # www.
    r"[a-zA-Z0-9][-a-zA-Z0-9]*\.(com|net|org|kr|co\.kr|go\.kr|or\.kr|io|ai|xyz)"  # domain.tld
)

# 한글 음역 URL 패턴 (더블유, 닷컴 등)
RE_URL_PHONETIC_KR = re.compile(
    r"(더블유\s*){2,3}|"  # www (더블유더블유더블유)
    r"쓰리\s*더블유|"  # 3w
    r"닷\s*컴|점\s*컴|닷컴|"  # .com
    r"닷\s*넷|점\s*넷|"  # .net
    r"닷\s*오알지|닷\s*오아르지|"  # .org
    r"닷\s*케이알|닷\s*코\s*케이알|"  # .kr, .co.kr
    r"닷\s*아이오|"  # .io
    r"닷\s*에이아이|"  # .ai
    r"슬래시\s*슬래시|"  # //
    r"에이치티티피|에이치티티피에스"  # http, https
)

# 이메일 패턴 (U1로 처리)
RE_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)


# =============================================================================
# 메인 함수
# =============================================================================

def find_spans(text_raw: str, context_len: int = 40) -> List[Span]:
    """
    위험 스팬을 탐지합니다.

    Args:
        text_raw: ASR 원본 텍스트
        context_len: 좌/우 컨텍스트 길이 (기본 40자)

    Returns:
        List[Span]: 탐지된 스팬 리스트 (시작 인덱스 순 정렬)

    우선순위:
        U1 > E2 > N3 (중복 방지)
    """
    spans: List[Span] = []

    # 1) U1: URL/도메인 패턴 (최우선)
    spans.extend(_find_u1_spans(text_raw, context_len))

    # 2) E2: 영문/알파뉴메릭
    spans.extend(_find_e2_spans(text_raw, context_len, spans))

    # 3) N3: 숫자
    spans.extend(_find_n3_spans(text_raw, context_len, spans))

    # 시작 인덱스 순 정렬
    spans.sort(key=lambda s: (s.start, -s.end))

    return spans


def _find_u1_spans(text: str, ctx_len: int) -> List[Span]:
    """U1 (URL/도메인) 스팬 탐지"""
    spans = []

    # 실제 URL
    for m in RE_URL_ACTUAL.finditer(text):
        spans.append(_make_span(text, m.start(), m.end(), "U1", ctx_len))

    # 이메일
    for m in RE_EMAIL.finditer(text):
        if not _overlaps_any(spans, m.start(), m.end()):
            spans.append(_make_span(text, m.start(), m.end(), "U1", ctx_len))

    # 한글 음역 URL 패턴
    for m in RE_URL_PHONETIC_KR.finditer(text):
        if not _overlaps_any(spans, m.start(), m.end()):
            spans.append(_make_span(text, m.start(), m.end(), "U1", ctx_len))

    return spans


def _find_e2_spans(text: str, ctx_len: int, existing: List[Span]) -> List[Span]:
    """E2 (영문/알파벳) 스팬 탐지"""
    spans = []

    # 결함 C 해결: 혼합 알파뉴메릭 우선 탐지 (COVID19, KDH123 등)
    # 순서 중요: mixed alnum을 먼저 탐지해야 COVID + 19로 분리되지 않음
    for m in RE_ALNUM_MIXED.finditer(text):
        if not _overlaps_any(existing + spans, m.start(), m.end()):
            spans.append(_make_span(text, m.start(), m.end(), "E2", ctx_len))

    # 순수 영문 (2자 이상) - mixed alnum 이후 탐지
    for m in RE_ENGLISH.finditer(text):
        if not _overlaps_any(existing + spans, m.start(), m.end()):
            spans.append(_make_span(text, m.start(), m.end(), "E2", ctx_len))

    return spans


def _find_n3_spans(text: str, ctx_len: int, existing: List[Span]) -> List[Span]:
    """N3 (숫자) 스팬 탐지"""
    spans = []

    # 아라비아 숫자
    for m in RE_DIGIT_RUN.finditer(text):
        if not _overlaps_any(existing + spans, m.start(), m.end()):
            spans.append(_make_span(text, m.start(), m.end(), "N3", ctx_len))

    # 한글 숫자 (문맥 조건 충족 시)
    for m in RE_KR_NUMBER.finditer(text):
        span_text = m.group()
        # 최소 2자 이상 + 숫자 문맥 단서
        if len(span_text) >= 2:
            if not _overlaps_any(existing + spans, m.start(), m.end()):
                # 결함 B 해결: 뒤 문맥 또는 앞 키워드 문맥 확인
                if _has_number_context(text, m.end()) or _has_number_prefix_context(text, m.start()):
                    spans.append(_make_span(text, m.start(), m.end(), "N3", ctx_len))

    return spans


# =============================================================================
# 헬퍼 함수
# =============================================================================

def _make_span(text: str, start: int, end: int, tag: RiskTag, ctx_len: int) -> Span:
    """Span 객체 생성 (컨텍스트 추출 포함)"""
    left = text[max(0, start - ctx_len):start]
    right = text[end:min(len(text), end + ctx_len)]
    return Span(
        start=start,
        end=end,
        text=text[start:end],
        tag=tag,
        left=left,
        right=right,
    )


def _overlaps_any(spans: List[Span], start: int, end: int) -> bool:
    """기존 스팬과 겹치는지 확인"""
    for s in spans:
        # 겹침 조건: 두 구간이 분리되지 않음
        if not (end <= s.start or start >= s.end):
            return True
    return False


def _has_number_context(text: str, end_pos: int) -> bool:
    """숫자 문맥 단서 존재 여부 (뒤에 붙는 단위/조사)"""
    after = text[end_pos:end_pos + 5]  # 최대 5자 확인
    for suffix in NUMBER_CONTEXT_SUFFIXES:
        if after.startswith(suffix):
            return True
    return False


def _has_number_prefix_context(text: str, start_pos: int) -> bool:
    """숫자 문맥 단서 존재 여부 (앞에 오는 키워드) - 결함 B 해결"""
    # 앞쪽 20자 확인 (키워드 + 조사/공백)
    before = text[max(0, start_pos - 20):start_pos]
    for keyword in NUMBER_CONTEXT_PREFIX_KEYWORDS:
        if keyword in before:
            return True
    return False


# =============================================================================
# 테스트용
# =============================================================================

if __name__ == "__main__":
    test_cases = [
        "인증번호가 일이삼사야",
        "2024년 3월 15일",
        "www.naver.com 접속해봐",
        "더블유더블유더블유 점 네이버 점 컴",
        "COVID19 확진자 1234명",
        "KDH가 만들었습니다",
        "010-1234-5678로 전화해",
        "이메일은 test@example.com입니다",
    ]

    for text in test_cases:
        print(f"\n입력: {text}")
        spans = find_spans(text)
        for s in spans:
            print(f"  [{s.tag}] '{s.text}' @ {s.start}:{s.end}")
            print(f"       context: '{s.left}' | '{s.right}'")

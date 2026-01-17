"""
트리아지 스코어러 모듈

ASR 결과를 분석하여 A/B/C 버킷으로 분류합니다.
규칙 기반(Rule-based) 방식으로, 임계값은 설정 가능합니다.
"""

from dataclasses import dataclass
from typing import Literal
import re


# 버킷 타입 정의 (A, B, C 중 하나만 가능)
BucketType = Literal["A", "B", "C"]


@dataclass
class TriageResult:
    """
    트리아지 결과를 담는 데이터 클래스

    사용 예시:
        result = TriageResult(bucket="A", reason="high_confidence", ...)
        if result.bucket == "A":
            # 자동 확정
    """
    bucket: BucketType           # "A", "B", or "C"
    reason: str                  # 분류 사유 (디버깅/로깅용)
    avg_logprob: float          # 평균 로그 확률
    compression_ratio: float    # 압축 비율
    text_length: int            # 텍스트 길이
    has_repetition: bool        # 반복 패턴 존재 여부


@dataclass
class TriageThresholds:
    """
    트리아지 임계값 설정

    왜 dataclass로?
    - 임계값을 한 곳에서 관리
    - 나중에 튜닝할 때 여기만 바꾸면 됨
    - 설정 파일에서 로드하기도 쉬움
    """
    # Hard fail 조건 (하나라도 해당되면 무조건 C)
    compression_ratio_max: float = 4.0      # 이 이상이면 모델 붕괴
    min_text_length: int = 2                # 이 미만이면 빈 출력
    max_ngram_repeat: int = 3               # n-gram 반복 횟수 한계

    # avg_logprob 기준 (A/B/C 분류)
    logprob_high: float = -0.3              # 이 이상이면 A
    logprob_medium: float = -0.7            # 이 이상이면 B, 미만이면 C


class TriageScorer:
    """
    트리아지 스코어러

    ASR 결과를 받아서 A/B/C 버킷으로 분류합니다.

    사용법:
        scorer = TriageScorer()
        result = scorer.score(
            text="안녕하세요",
            avg_logprob=-0.15,
            compression_ratio=1.4
        )
        print(result.bucket)  # "A"
        print(result.reason)  # "high_confidence"
    """

    def __init__(self, thresholds: TriageThresholds = None):
        """
        Args:
            thresholds: 임계값 설정 (None이면 기본값 사용)
        """
        self.thresholds = thresholds or TriageThresholds()

    def score(
        self,
        text: str,
        avg_logprob: float,
        compression_ratio: float
    ) -> TriageResult:
        """
        ASR 결과를 분석하여 버킷 분류

        Args:
            text: ASR이 인식한 텍스트
            avg_logprob: 평균 로그 확률 (Whisper 제공)
            compression_ratio: 압축 비율 (Whisper 제공)

        Returns:
            TriageResult: 분류 결과

        분류 로직:
            1. Hard fail 체크 (하나라도 해당되면 C)
               - compression_ratio > 4.0 → 모델 붕괴
               - 반복 n-gram 3회+ → 텍스트 붕괴
               - len(text) < 2 → 빈 출력

            2. avg_logprob 기준으로 A/B/C
               - > -0.3 → A (높은 신뢰도)
               - > -0.7 → B (중간 신뢰도)
               - else → C (낮은 신뢰도)
        """
        th = self.thresholds
        text_stripped = text.strip()
        text_length = len(text_stripped)

        # 반복 패턴 체크
        has_repetition = self._has_repeated_ngram(text_stripped, n=2)

        # === 1. Hard fail 체크 ===

        # 1-1. 압축 비율 체크 (모델 붕괴)
        if compression_ratio > th.compression_ratio_max:
            return TriageResult(
                bucket="C",
                reason="compression_ratio_high",
                avg_logprob=avg_logprob,
                compression_ratio=compression_ratio,
                text_length=text_length,
                has_repetition=has_repetition
            )

        # 1-2. 반복 패턴 체크 (텍스트 붕괴)
        if self._has_repeated_ngram(text_stripped, n=2, min_repeats=th.max_ngram_repeat):
            return TriageResult(
                bucket="C",
                reason="repeated_ngram",
                avg_logprob=avg_logprob,
                compression_ratio=compression_ratio,
                text_length=text_length,
                has_repetition=True
            )

        # 1-3. 최소 길이 체크 (빈 출력)
        if text_length < th.min_text_length:
            return TriageResult(
                bucket="C",
                reason="too_short",
                avg_logprob=avg_logprob,
                compression_ratio=compression_ratio,
                text_length=text_length,
                has_repetition=has_repetition
            )

        # === 2. avg_logprob 기준 분류 ===

        if avg_logprob > th.logprob_high:
            bucket = "A"
            reason = "high_confidence"
        elif avg_logprob > th.logprob_medium:
            bucket = "B"
            reason = "medium_confidence"
        else:
            bucket = "C"
            reason = "low_confidence"

        return TriageResult(
            bucket=bucket,
            reason=reason,
            avg_logprob=avg_logprob,
            compression_ratio=compression_ratio,
            text_length=text_length,
            has_repetition=has_repetition
        )

    def _has_repeated_ngram(
        self,
        text: str,
        n: int = 2,
        min_repeats: int = 3
    ) -> bool:
        """
        텍스트에 반복되는 n-gram이 있는지 확인

        n-gram이란?
            연속된 n개의 단어/글자 묶음
            예: "안녕 안녕 안녕" → 2-gram "안녕"이 3번 반복

        Args:
            text: 검사할 텍스트
            n: n-gram 크기 (기본 2 = 2글자씩)
            min_repeats: 최소 반복 횟수

        Returns:
            bool: 반복 패턴 존재 여부

        예시:
            "안녕 안녕 안녕" → True (같은 단어 3번)
            "네네네네네" → True (같은 글자 연속)
            "오늘 날씨가 좋습니다" → False (정상)
        """
        if len(text) < n * min_repeats:
            return False

        # 방법 1: 같은 글자가 연속으로 반복 (예: "네네네네")
        for i in range(len(text) - n * min_repeats + 1):
            pattern = text[i:i+n]
            # pattern이 min_repeats번 연속으로 나오는지 확인
            repeated = pattern * min_repeats
            if repeated in text:
                return True

        # 방법 2: 공백으로 나눈 단어가 연속 반복 (예: "안녕 안녕 안녕")
        words = text.split()
        if len(words) >= min_repeats:
            for i in range(len(words) - min_repeats + 1):
                # 연속된 min_repeats개의 단어가 모두 같은지
                window = words[i:i+min_repeats]
                if len(set(window)) == 1:  # 모두 같으면 set 크기가 1
                    return True

        return False

    def score_batch(self, results: list) -> list:
        """
        여러 ASR 결과를 한꺼번에 분류

        Args:
            results: TranscriptionResult 리스트
                     (또는 text, avg_logprob, compression_ratio를 가진 객체)

        Returns:
            list[TriageResult]: 분류 결과 리스트
        """
        triage_results = []
        for r in results:
            triage_result = self.score(
                text=r.text,
                avg_logprob=r.avg_logprob,
                compression_ratio=r.compression_ratio
            )
            triage_results.append(triage_result)
        return triage_results

    def get_statistics(self, results: list) -> dict:
        """
        트리아지 결과 통계 계산

        Args:
            results: TriageResult 리스트

        Returns:
            dict: 버킷별 개수 및 비율

        예시 출력:
            {
                "total": 1000,
                "A": {"count": 800, "ratio": 0.80},
                "B": {"count": 150, "ratio": 0.15},
                "C": {"count": 50, "ratio": 0.05}
            }
        """
        total = len(results)
        if total == 0:
            return {"total": 0, "A": {}, "B": {}, "C": {}}

        counts = {"A": 0, "B": 0, "C": 0}
        for r in results:
            counts[r.bucket] += 1

        return {
            "total": total,
            "A": {"count": counts["A"], "ratio": counts["A"] / total},
            "B": {"count": counts["B"], "ratio": counts["B"] / total},
            "C": {"count": counts["C"], "ratio": counts["C"] / total}
        }


# 테스트용 코드
if __name__ == "__main__":
    scorer = TriageScorer()

    # 테스트 케이스들
    test_cases = [
        # (text, avg_logprob, compression_ratio, expected_bucket)
        ("안녕하세요", -0.15, 1.4, "A"),      # 높은 신뢰도
        ("오늘 날씨가", -0.5, 1.8, "B"),      # 중간 신뢰도
        ("어", -0.9, 2.0, "C"),               # 너무 짧음
        ("네네네네네네", -0.2, 1.5, "C"),     # 반복 패턴
        ("테스트 문장", -0.2, 5.0, "C"),      # 압축비 높음
        ("정상적인 문장입니다", -0.85, 1.6, "C"),  # 낮은 신뢰도
    ]

    print("=== 트리아지 테스트 ===\n")
    for text, logprob, comp_ratio, expected in test_cases:
        result = scorer.score(text, logprob, comp_ratio)
        status = "✓" if result.bucket == expected else "✗"
        print(f"{status} text='{text}'")
        print(f"  avg_logprob={logprob}, compression_ratio={comp_ratio}")
        print(f"  → bucket={result.bucket}, reason={result.reason}")
        print()

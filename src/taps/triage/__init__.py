"""
트리아지 (Triage) 모듈

ASR 결과의 신뢰도를 평가하고 A/B/C 버킷으로 분류합니다.
"""

from .scorer import TriageScorer, TriageResult

__all__ = ["TriageScorer", "TriageResult"]

"""
correct_model v1 데이터 모델

implementation_contract_v1.md 스키마 준수
"""

from dataclasses import dataclass, field
from typing import List, Optional, Literal, Dict, Any

# 타입 별칭
RiskTag = Literal["N3", "E2", "U1", "OOV", "CANON"]
Bucket = Literal["RED", "ORANGE", "YELLOW", "GREEN"]
Action = Literal["AUTO_FIX", "NEEDS_REVIEW", "PASS"]


@dataclass
class Span:
    """
    위험 스팬 (숫자/영문/URL/OOV)

    Attributes:
        start: 시작 인덱스 (inclusive)
        end: 끝 인덱스 (exclusive)
        text: 스팬 텍스트
        tag: 위험 태그 (N3/E2/U1/OOV)
        left: 왼쪽 컨텍스트
        right: 오른쪽 컨텍스트
    """
    start: int
    end: int
    text: str
    tag: RiskTag
    left: str
    right: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "tag": self.tag,
            "left": self.left,
            "right": self.right,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Span":
        return cls(
            start=d["start"],
            end=d["end"],
            text=d["text"],
            tag=d["tag"],
            left=d["left"],
            right=d["right"],
        )


@dataclass
class Candidate:
    """
    BTC 생성 후보

    Attributes:
        text: 후보 텍스트
        score: 정규화된 점수 (higher is better)
    """
    text: str
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "score": self.score}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Candidate":
        return cls(text=d["text"], score=d["score"])


@dataclass
class Issue:
    """
    검수용 이슈 (Excel 행 1개)

    implementation_contract_v1.md 스키마:
    - utt_id, speaker_id, sentence_id: 식별자
    - bucket: 트리아지 버킷 (RED/ORANGE/YELLOW/GREEN)
    - tag: 위험 태그 (N3/E2/U1/OOV/CANON)
    - span_start, span_end, raw_span: 스팬 위치/텍스트
    - context_full, context_marked: 문맥 정보
    - context_marked_safe: cp949 안전 문자 버전
    - candidates: BTC 후보 리스트
    - recommended: 추천 후보
    - user_fix: 사용자 수정 (prefill = recommended)
    - meta: 메타데이터 (avg_logprob, compression_ratio 등)
    """
    utt_id: str
    speaker_id: str
    sentence_id: str
    bucket: Bucket

    tag: RiskTag
    span_start: int
    span_end: int
    raw_span: str

    context_full: str
    context_marked: str  # LEFT + ⟦SPAN⟧ + RIGHT
    context_marked_safe: str = ""  # cp949 안전 버전 ([[ ]] 사용)

    candidates: List[Candidate] = field(default_factory=list)
    recommended: str = ""
    user_fix: str = ""  # prefill = recommended

    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "utt_id": self.utt_id,
            "speaker_id": self.speaker_id,
            "sentence_id": self.sentence_id,
            "bucket": self.bucket,
            "tag": self.tag,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "raw_span": self.raw_span,
            "context_full": self.context_full,
            "context_marked": self.context_marked,
            "context_marked_safe": self.context_marked_safe,
            "candidates": [c.to_dict() for c in self.candidates],
            "recommended": self.recommended,
            "user_fix": self.user_fix,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Issue":
        return cls(
            utt_id=d["utt_id"],
            speaker_id=d["speaker_id"],
            sentence_id=d["sentence_id"],
            bucket=d["bucket"],
            tag=d["tag"],
            span_start=d["span_start"],
            span_end=d["span_end"],
            raw_span=d["raw_span"],
            context_full=d["context_full"],
            context_marked=d["context_marked"],
            context_marked_safe=d.get("context_marked_safe", ""),
            candidates=[Candidate.from_dict(c) for c in d.get("candidates", [])],
            recommended=d.get("recommended", ""),
            user_fix=d.get("user_fix", ""),
            meta=d.get("meta", {}),
        )


@dataclass
class CorrectModelOutput:
    """
    correct_model 출력 (문장 단위)

    Attributes:
        utt_id: utterance ID
        speaker_id: 화자 ID
        sentence_id: 문장 ID
        text_raw: ASR 원본 텍스트
        bucket: 트리아지 버킷
        decision: 최종 결정 (AUTO_FIX / NEEDS_REVIEW / PASS)
        text_avail: 확정 텍스트 (NEEDS_REVIEW일 경우 None)
        issues: 검수 이슈 리스트
        audit: 감사 정보 (파이프라인 버전, 설정 등)
    """
    utt_id: str
    speaker_id: str
    sentence_id: str
    text_raw: str
    bucket: Bucket
    decision: Action
    text_avail: Optional[str]
    issues: List[Issue]
    audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "utt_id": self.utt_id,
            "speaker_id": self.speaker_id,
            "sentence_id": self.sentence_id,
            "text_raw": self.text_raw,
            "bucket": self.bucket,
            "decision": self.decision,
            "text_avail": self.text_avail,
            "issues": [iss.to_dict() for iss in self.issues],
            "audit": self.audit,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CorrectModelOutput":
        return cls(
            utt_id=d["utt_id"],
            speaker_id=d["speaker_id"],
            sentence_id=d["sentence_id"],
            text_raw=d["text_raw"],
            bucket=d["bucket"],
            decision=d["decision"],
            text_avail=d.get("text_avail"),
            issues=[Issue.from_dict(iss) for iss in d["issues"]],
            audit=d.get("audit", {}),
        )

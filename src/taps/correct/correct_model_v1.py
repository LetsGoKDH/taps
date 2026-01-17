"""
correct_model v1 메인 파이프라인

BTC(ByT5-Korean) 기반 canonicalization + 가드레일/트리아지

CLI:
    python -m taps.correct.correct_model_v1 \\
        --in_asr_jsonl asr_results.jsonl \\
        --out_issues_jsonl issues.jsonl \\
        --out_text_avail_jsonl text_avail.jsonl \\
        --btc_model_name everdoubling/byt5-Korean-base \\
        --k_candidates 5 \\
        --context_len 40
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

from .models import (
    Span,
    Candidate,
    Issue,
    CorrectModelOutput,
    RiskTag,
    Bucket,
    Action,
)
from .span_finder import find_spans
from .btc_wrapper import BTCWrapper
from .decision import decide_action, decide_sentence_action


# =============================================================================
# 결함 A 해결: cp949 콘솔 안전 출력
# =============================================================================

def safe_context_marked(text: str) -> str:
    """
    cp949 콘솔에서 안전한 문자로 대체
    
    ⟦ (U+27E6) → [[
    ⟧ (U+27E7) → ]]
    
    Windows cp949 콘솔에서 UnicodeEncodeError 방지
    """
    return text.replace("⟦", "[[").replace("⟧", "]]")


@dataclass
class TriageConfig:
    """
    트리아지 버킷 퍼센타일 설정

    implementation_contract_v1.md 기준:
    - RED: 0-3%
    - ORANGE: 3-15%
    - YELLOW: 15-40%
    - GREEN: 40-100%
    """
    red_percentile: float = 0.03
    orange_percentile: float = 0.15
    yellow_percentile: float = 0.40


class CorrectModelV1:
    """
    correct_model v1 파이프라인

    흐름:
    1. ASR 결과 로드
    2. avg_logprob 기반 버킷팅 (RED/ORANGE/YELLOW/GREEN)
    3. 스팬 탐지 (N3/E2/U1)
    4. BTC 후보 생성
    5. 의사결정 (AUTO_FIX / NEEDS_REVIEW)
    6. 출력 생성 (issues.jsonl, text_avail.jsonl)
    """

    def __init__(
        self,
        btc_model_name: Optional[str] = None,
        k_candidates: int = 5,
        context_len: int = 40,
        device: str = "auto",
    ):
        """
        Args:
            btc_model_name: BTC 모델명 (기본: everdoubling/byt5-Korean-base)
            k_candidates: 생성할 후보 수 (기본: 5)
            context_len: 좌/우 컨텍스트 길이 (기본: 40)
            device: 디바이스 (auto/cuda/cpu)
        """
        self.k_candidates = k_candidates
        self.context_len = context_len
        self.triage_config = TriageConfig()

        # BTC 모델 (lazy load)
        self._btc: Optional[BTCWrapper] = None
        self._btc_model_name = btc_model_name
        self._device = device

    @property
    def btc(self) -> BTCWrapper:
        """BTC 모델 래퍼 (lazy loading)"""
        if self._btc is None:
            self._btc = BTCWrapper(
                model_name=self._btc_model_name,
                device=self._device,
            )
        return self._btc

    def process_batch(
        self,
        asr_records: List[Dict[str, Any]],
        verbose: bool = False,
    ) -> List[CorrectModelOutput]:
        """
        배치 처리

        Args:
            asr_records: ASR 결과 레코드 리스트
                필수 필드: speaker_id, sentence_id, text (또는 text_raw)
                선택 필드: avg_logprob, compression_ratio, duration, language
            verbose: 진행 상황 출력 여부

        Returns:
            List[CorrectModelOutput]: 처리 결과
        """
        if not asr_records:
            return []

        # 1) 버킷 계산 (전체 배치 기준 퍼센타일)
        buckets = self._compute_buckets(asr_records)

        if verbose:
            bucket_counts = {}
            for b in buckets:
                bucket_counts[b] = bucket_counts.get(b, 0) + 1
            print(f"버킷 분포: {bucket_counts}")

        # 2) 각 레코드 처리
        results = []
        for i, record in enumerate(asr_records):
            bucket = buckets[i]
            output = self._process_single(record, bucket)
            results.append(output)

            if verbose and (i + 1) % 100 == 0:
                print(f"  처리 중: {i + 1}/{len(asr_records)}")

        return results

    def _compute_buckets(self, records: List[Dict[str, Any]]) -> List[Bucket]:
        """
        avg_logprob 퍼센타일 기반 버킷 계산

        avg_logprob가 없는 레코드는 위험 점수로 fallback
        """
        import numpy as np

        logprobs = []
        for r in records:
            lp = r.get("avg_logprob")
            if lp is None:
                # fallback: 위험 스팬 개수로 risk score 계산
                text = r.get("text", r.get("text_raw", ""))
                spans = find_spans(text, context_len=self.context_len)
                # U1 2점, E2 1점, N3 0.5점
                risk_score = sum(
                    2.0 if s.tag == "U1" else (1.0 if s.tag == "E2" else 0.5)
                    for s in spans
                )
                # risk_score를 가상의 낮은 logprob으로 변환
                lp = -1.0 - risk_score * 0.1
            logprobs.append(lp)

        logprobs_arr = np.array(logprobs)

        # 퍼센타일 임계값 계산 (오름차순: 낮을수록 위험)
        p_red = np.percentile(logprobs_arr, self.triage_config.red_percentile * 100)
        p_orange = np.percentile(logprobs_arr, self.triage_config.orange_percentile * 100)
        p_yellow = np.percentile(logprobs_arr, self.triage_config.yellow_percentile * 100)

        buckets: List[Bucket] = []
        for lp in logprobs:
            if lp <= p_red:
                buckets.append("RED")
            elif lp <= p_orange:
                buckets.append("ORANGE")
            elif lp <= p_yellow:
                buckets.append("YELLOW")
            else:
                buckets.append("GREEN")

        return buckets

    def _process_single(
        self,
        record: Dict[str, Any],
        bucket: Bucket,
    ) -> CorrectModelOutput:
        """단일 레코드 처리"""
        # 메타데이터 추출
        speaker_id = str(record.get("speaker_id", ""))
        sentence_id = str(record.get("sentence_id", ""))
        utt_id = record.get("utt_id", f"{speaker_id}_{sentence_id}")
        text_raw = record.get("text", record.get("text_raw", ""))

        meta = {
            "avg_logprob": record.get("avg_logprob"),
            "compression_ratio": record.get("compression_ratio"),
            "duration": record.get("duration"),
            "language": record.get("language"),
        }

        # 스팬 탐지
        spans = find_spans(text_raw, context_len=self.context_len)

        # URL 스팬 존재 여부
        has_url_span = any(s.tag == "U1" for s in spans)

        # 스팬이 없으면 문장 전체에 STW_CANON 적용
        if not spans:
            return self._process_no_spans(
                utt_id, speaker_id, sentence_id,
                text_raw, bucket, has_url_span, meta
            )

        # 스팬별 처리
        issues: List[Issue] = []
        applied_fixes: List[tuple] = []  # (start, end, new_text)

        for span in spans:
            # BTC 태스크 결정
            task = "STW_URL" if span.tag == "U1" else "STW_SPAN"

            # 후보 생성
            candidates = self.btc.generate(
                task=task,
                left=span.left,
                span=span.text,
                right=span.right,
                k=self.k_candidates,
            )

            # 추천 텍스트
            recommended = candidates[0].text if candidates else span.text

            # 의사결정
            action = decide_action(
                tag=span.tag,
                bucket=bucket,
                candidates=candidates,
                raw_span_or_sentence=span.text,
                recommended=recommended,
                is_url_present_in_sentence=has_url_span,
            )

            if action == "AUTO_FIX":
                # 자동 적용 대상
                applied_fixes.append((span.start, span.end, recommended))
            else:
                # Issue 생성
                issue = Issue(
                    utt_id=utt_id,
                    speaker_id=speaker_id,
                    sentence_id=sentence_id,
                    bucket=bucket,
                    tag=span.tag,
                    span_start=span.start,
                    span_end=span.end,
                    raw_span=span.text,
                    context_full=text_raw,
                    context_marked=f"{span.left}⟦{span.text}⟧{span.right}",
                    context_marked_safe=safe_context_marked(f"{span.left}⟦{span.text}⟧{span.right}"),
                    candidates=candidates,
                    recommended=recommended,
                    user_fix=recommended,  # prefill
                    meta=meta,
                )
                issues.append(issue)

        # text_avail 생성 (AUTO_FIX된 스팬만 적용)
        text_avail = self._apply_fixes(text_raw, applied_fixes)

        # 최종 결정
        if issues:
            # NEEDS_REVIEW인 스팬이 있으면 text_avail은 null
            decision: Action = "NEEDS_REVIEW"
            text_avail_final: Optional[str] = None
        else:
            decision = "AUTO_FIX"
            text_avail_final = text_avail

        return CorrectModelOutput(
            utt_id=utt_id,
            speaker_id=speaker_id,
            sentence_id=sentence_id,
            text_raw=text_raw,
            bucket=bucket,
            decision=decision,
            text_avail=text_avail_final,
            issues=issues,
            audit={
                "pipeline_version": "correct_model_v1",
                "k_candidates": self.k_candidates,
                "context_len": self.context_len,
                "spans_detected": len(spans),
                "auto_fixed": len(applied_fixes),
            },
        )

    def _process_no_spans(
        self,
        utt_id: str,
        speaker_id: str,
        sentence_id: str,
        text_raw: str,
        bucket: Bucket,
        has_url_span: bool,
        meta: Dict[str, Any],
    ) -> CorrectModelOutput:
        """스팬이 없는 경우: STW_CANON으로 문장 전체 처리"""
        # BTC 후보 생성
        candidates = self.btc.generate(
            task="STW_CANON",
            left="",
            span=text_raw,
            right="",
            k=self.k_candidates,
        )

        recommended = candidates[0].text if candidates else text_raw

        # 문장 전체 자동 확정 여부
        action = decide_sentence_action(
            bucket=bucket,
            text_raw=text_raw,
            text_canonical=recommended,
            has_url_span=has_url_span,
        )

        if action == "AUTO_FIX":
            return CorrectModelOutput(
                utt_id=utt_id,
                speaker_id=speaker_id,
                sentence_id=sentence_id,
                text_raw=text_raw,
                bucket=bucket,
                decision="AUTO_FIX",
                text_avail=recommended,
                issues=[],
                audit={
                    "pipeline_version": "correct_model_v1",
                    "mode": "STW_CANON",
                },
            )
        else:
            # 문장 전체를 Issue로 생성
            issue = Issue(
                utt_id=utt_id,
                speaker_id=speaker_id,
                sentence_id=sentence_id,
                bucket=bucket,
                tag="CANON",  # 결함 D 해결: 기존 "N3" (placeholder) -> "CANON"
                span_start=0,
                span_end=len(text_raw),
                raw_span=text_raw,
                context_full=text_raw,
                context_marked=f"⟦{text_raw}⟧",
                context_marked_safe=safe_context_marked(f"⟦{text_raw}⟧"),
                candidates=candidates,
                recommended=recommended,
                user_fix=recommended,
                meta=meta,
            )
            return CorrectModelOutput(
                utt_id=utt_id,
                speaker_id=speaker_id,
                sentence_id=sentence_id,
                text_raw=text_raw,
                bucket=bucket,
                decision="NEEDS_REVIEW",
                text_avail=None,
                issues=[issue],
                audit={
                    "pipeline_version": "correct_model_v1",
                    "mode": "STW_CANON",
                },
            )

    def _apply_fixes(
        self,
        text: str,
        fixes: List[tuple],
    ) -> str:
        """
        텍스트에 수정 적용

        Args:
            text: 원본 텍스트
            fixes: [(start, end, new_text), ...] 리스트

        Returns:
            수정된 텍스트

        겹침 처리: 더 긴 스팬 우선, 같으면 먼저 시작하는 스팬 우선
        """
        if not fixes:
            return text

        # 역순 정렬 (뒤에서부터 적용해야 인덱스 보존)
        sorted_fixes = sorted(fixes, key=lambda f: (f[0], -(f[1] - f[0])), reverse=True)

        result = text
        applied_ranges = []

        for start, end, new_text in sorted_fixes:
            # 겹침 체크
            overlaps = False
            for app_start, app_end in applied_ranges:
                if not (end <= app_start or start >= app_end):
                    overlaps = True
                    break

            if not overlaps:
                result = result[:start] + new_text + result[end:]
                applied_ranges.append((start, end))

        return result


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="correct_model v1: BTC 기반 canonicalization 파이프라인"
    )
    parser.add_argument(
        "--in_asr_jsonl",
        required=True,
        help="ASR 결과 JSONL 파일 경로",
    )
    parser.add_argument(
        "--out_issues_jsonl",
        required=True,
        help="Issues 출력 JSONL 파일 경로",
    )
    parser.add_argument(
        "--out_text_avail_jsonl",
        required=True,
        help="text_avail 출력 JSONL 파일 경로",
    )
    parser.add_argument(
        "--btc_model_name",
        default=None,
        help="BTC 모델명 (기본: everdoubling/byt5-Korean-base)",
    )
    parser.add_argument(
        "--k_candidates",
        type=int,
        default=5,
        help="생성할 후보 수 (기본: 5)",
    )
    parser.add_argument(
        "--context_len",
        type=int,
        default=40,
        help="좌/우 컨텍스트 길이 (기본: 40)",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="디바이스 (auto/cuda/cpu)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="진행 상황 출력",
    )

    args = parser.parse_args()

    # 모델 초기화
    model = CorrectModelV1(
        btc_model_name=args.btc_model_name,
        k_candidates=args.k_candidates,
        context_len=args.context_len,
        device=args.device,
    )

    # ASR 결과 로드
    print(f"ASR 결과 로드 중: {args.in_asr_jsonl}")
    records = []
    with open(args.in_asr_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"로드 완료: {len(records)} 레코드")

    # 처리
    print("correct_model 처리 중...")
    outputs = model.process_batch(records, verbose=args.verbose)

    # 출력 저장
    issues_count = 0
    text_avail_count = 0

    # 디렉토리 생성
    Path(args.out_issues_jsonl).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_text_avail_jsonl).parent.mkdir(parents=True, exist_ok=True)

    with open(args.out_issues_jsonl, "w", encoding="utf-8") as f_issues, \
         open(args.out_text_avail_jsonl, "w", encoding="utf-8") as f_avail:

        for out in outputs:
            # Issues
            for issue in out.issues:
                f_issues.write(json.dumps(issue.to_dict(), ensure_ascii=False) + "\n")
                issues_count += 1

            # text_avail (AUTO_FIX된 것만)
            if out.text_avail is not None:
                avail_record = {
                    "utt_id": out.utt_id,
                    "speaker_id": out.speaker_id,
                    "sentence_id": out.sentence_id,
                    "text_raw": out.text_raw,
                    "text_avail": out.text_avail,
                    "bucket": out.bucket,
                    "decision": out.decision,
                }
                f_avail.write(json.dumps(avail_record, ensure_ascii=False) + "\n")
                text_avail_count += 1

    # 통계 출력
    print()
    print("=" * 50)
    print("완료")
    print("=" * 50)
    print(f"총 레코드: {len(records)}")
    print(f"Issues: {issues_count}개 -> {args.out_issues_jsonl}")
    print(f"text_avail (AUTO_FIX): {text_avail_count}개 -> {args.out_text_avail_jsonl}")
    print(f"NEEDS_REVIEW: {len(records) - text_avail_count}개")

    # 버킷별 통계
    bucket_stats = {"RED": 0, "ORANGE": 0, "YELLOW": 0, "GREEN": 0}
    decision_stats = {"AUTO_FIX": 0, "NEEDS_REVIEW": 0, "PASS": 0}
    for out in outputs:
        bucket_stats[out.bucket] = bucket_stats.get(out.bucket, 0) + 1
        decision_stats[out.decision] = decision_stats.get(out.decision, 0) + 1

    print(f"\n버킷 분포: {bucket_stats}")
    print(f"결정 분포: {decision_stats}")


if __name__ == "__main__":
    main()

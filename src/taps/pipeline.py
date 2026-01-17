"""
TAPS 라벨링 자동화 파이프라인

ASR → 트리아지 → 검수 → 정규화 워크플로우를 통합 관리합니다.

사용 예시:
    from taps.pipeline import LabelingPipeline

    pipeline = LabelingPipeline()
    results = pipeline.run(audio_samples)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime


@dataclass
class PipelineResult:
    """
    파이프라인 실행 결과를 담는 데이터 클래스

    각 샘플에 대해 ASR 결과와 트리아지 결과를 함께 저장합니다.

    필드 설명:
        sample_id: 샘플 고유 식별자
        text_raw: ASR 원본 출력
        bucket: 트리아지 결과 (A/B/C)
        reason: 트리아지 분류 사유
        metrics: Whisper 메트릭 (avg_logprob, compression_ratio 등)
        text_verified: 검수 완료된 텍스트 (초기값 None)
        text_normalized: 정규화 완료된 텍스트 (초기값 None)
    """
    sample_id: str
    text_raw: str
    bucket: str  # "A", "B", or "C"
    reason: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    text_verified: Optional[str] = None
    text_normalized: Optional[str] = None

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (JSON 저장용)"""
        return {
            "sample_id": self.sample_id,
            "text_raw": self.text_raw,
            "bucket": self.bucket,
            "reason": self.reason,
            "metrics": self.metrics,
            "text_verified": self.text_verified,
            "text_normalized": self.text_normalized
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineResult":
        """딕셔너리에서 생성"""
        return cls(**data)


class LabelingPipeline:
    """
    라벨링 자동화 파이프라인

    Step 1: ASR (Whisper) - 음성 → 텍스트
    Step 2: 트리아지 - 신뢰도 평가 → A/B/C 버킷팅
    Step 3: 검수 - (선택적) 사람이 확인/수정
    Step 4: 정규화 - 텍스트 정규화

    사용법:
        # 기본 사용
        pipeline = LabelingPipeline()
        results = pipeline.run(samples)

        # 커스텀 설정
        pipeline = LabelingPipeline(
            model_size="large-v3",
            device="cuda"
        )
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
        output_dir: str = None
    ):
        """
        파이프라인 초기화

        Args:
            model_size: Whisper 모델 크기 (권장: "large-v3")
            device: 연산 장치 ("cuda", "cpu", "auto")
            compute_type: 연산 타입 ("float16", "int8", "auto")
            output_dir: 결과 저장 디렉토리 (기본: ./data/outputs)
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

        # 출력 디렉토리 설정
        if output_dir is None:
            self.output_dir = Path(__file__).parent.parent.parent / "data" / "outputs"
        else:
            self.output_dir = Path(output_dir)

        # 지연 로딩을 위해 None으로 초기화
        # (모델 로드가 오래 걸리므로, 실제 사용할 때 로드)
        self._transcriber = None
        self._scorer = None

    @property
    def transcriber(self):
        """
        ASR 모델 (지연 로딩)

        왜 지연 로딩?
        - 모델 로드에 시간이 걸림 (수 초 ~ 수십 초)
        - 파이프라인 객체 생성만으로는 로드하지 않음
        - 실제 transcribe를 호출할 때 로드
        """
        if self._transcriber is None:
            from .asr import Transcriber
            print("ASR 모델 로드 중...")
            self._transcriber = Transcriber(
                model_size=self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
        return self._transcriber

    @property
    def scorer(self):
        """트리아지 스코어러 (지연 로딩)"""
        if self._scorer is None:
            from .triage import TriageScorer
            self._scorer = TriageScorer()
        return self._scorer

    def run_asr(
        self,
        samples: List[Dict],
        audio_key: str = "audio.acoustic_microphone",
        id_key: str = "sentence_id",
        show_progress: bool = True
    ) -> List[PipelineResult]:
        """
        Step 1 + 2: ASR 실행 및 트리아지

        Args:
            samples: 오디오 샘플 리스트
                    각 샘플은 오디오 데이터와 ID를 포함
            audio_key: 오디오 데이터의 키 이름
            id_key: 샘플 ID의 키 이름
            show_progress: 진행률 표시 여부

        Returns:
            List[PipelineResult]: 처리 결과 리스트

        사용 예시:
            samples = [{"audio.acoustic_microphone": audio_data, "sentence_id": "u00"}, ...]
            results = pipeline.run_asr(samples)
        """
        results = []

        # 진행률 표시
        if show_progress:
            try:
                from tqdm import tqdm
                samples = tqdm(samples, desc="Processing")
            except ImportError:
                print("tqdm 미설치 - 진행률 표시 없이 진행")

        for sample in samples:
            try:
                # 샘플 ID 추출
                sample_id = sample.get(id_key, "unknown")

                # 오디오 데이터 추출
                audio_data = sample.get(audio_key)
                if audio_data is None:
                    print(f"경고: {sample_id}에서 오디오를 찾을 수 없음")
                    continue

                # 오디오가 dict인 경우 (HuggingFace 형식)
                if isinstance(audio_data, dict) and "array" in audio_data:
                    audio_array = audio_data["array"]
                else:
                    audio_array = audio_data

                # Step 1: ASR 실행
                asr_result = self.transcriber.transcribe(audio_array)

                # Step 2: 트리아지
                triage_result = self.scorer.score(
                    text=asr_result.text,
                    avg_logprob=asr_result.avg_logprob,
                    compression_ratio=asr_result.compression_ratio
                )

                # 결과 저장
                result = PipelineResult(
                    sample_id=sample_id,
                    text_raw=asr_result.text,
                    bucket=triage_result.bucket,
                    reason=triage_result.reason,
                    metrics={
                        "avg_logprob": asr_result.avg_logprob,
                        "compression_ratio": asr_result.compression_ratio,
                        "duration": asr_result.duration,
                        "language": asr_result.language,
                        "text_length": triage_result.text_length,
                        "has_repetition": triage_result.has_repetition
                    }
                )
                results.append(result)

            except Exception as e:
                print(f"에러 ({sample_id}): {e}")
                # 에러 발생 시 빈 결과 추가
                results.append(PipelineResult(
                    sample_id=sample_id,
                    text_raw="[ERROR]",
                    bucket="C",
                    reason="processing_error",
                    metrics={"error": str(e)}
                ))

        return results

    def normalize_results(
        self,
        results: List[PipelineResult],
        numbers: bool = True,
        alphabet: bool = True,
        compounds: bool = True,
        spacing: bool = True
    ) -> List[PipelineResult]:
        """
        Step 4: 정규화 적용

        외부 정규화 패키지 (Kornormalizer)를 사용합니다.

        패키지 경로 설정 방법 (우선순위):
            1. 환경변수 KORNORMALIZER_PATH
            2. 프로젝트 상위의 '정규화' 폴더 (../정규화)

        Args:
            results: PipelineResult 리스트
            numbers: 숫자 -> 한글 변환 (예: 2024 -> 이천이십사)
            alphabet: 영문 -> 한글 변환 (예: KDH -> 케이디에이치)
            compounds: 복합명사 분리 (예: 데이터베이스시스템 -> 데이터베이스 시스템)
            spacing: 의존명사 띄어쓰기 (예: 할수있다 -> 할 수 있다)

        Returns:
            List[PipelineResult]: 정규화된 결과 리스트
        """
        import sys
        import os

        # 정규화 패키지 경로 결정
        # 1순위: 환경변수
        # 2순위: 프로젝트 상위 폴더의 '정규화' 디렉토리
        normalizer_path = os.environ.get('KORNORMALIZER_PATH')
        if not normalizer_path:
            # 프로젝트 루트 기준 상대경로 (연참/../정규화)
            project_root = Path(__file__).parent.parent.parent
            normalizer_path = str(project_root.parent / "정규화")

        if normalizer_path not in sys.path:
            sys.path.insert(0, normalizer_path)

        from normalizer import normalize

        for result in results:
            # 검수된 텍스트가 있으면 그것을 정규화
            # 없으면 ASR 원본을 정규화
            source_text = result.text_verified or result.text_raw

            if source_text and source_text != "[ERROR]":
                result.text_normalized = normalize(
                    source_text,
                    numbers=numbers,
                    alphabet=alphabet,
                    compounds=compounds,
                    spacing=spacing
                )

        return results

    def save_results(
        self,
        results: List[PipelineResult],
        filename: str = None
    ) -> Path:
        """
        결과를 JSON 파일로 저장

        Args:
            results: 저장할 결과 리스트
            filename: 파일명 (없으면 타임스탬프 사용)

        Returns:
            Path: 저장된 파일 경로
        """
        # 출력 디렉토리 생성
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 파일명 생성
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"results_{timestamp}.json"

        filepath = self.output_dir / filename

        # JSON으로 저장
        data = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "total_count": len(results),
                "model_size": self.model_size
            },
            "results": [r.to_dict() for r in results]
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"결과 저장 완료: {filepath}")
        return filepath

    def load_results(self, filepath: str) -> List[PipelineResult]:
        """
        저장된 결과 로드

        Args:
            filepath: JSON 파일 경로

        Returns:
            List[PipelineResult]: 로드된 결과 리스트
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return [PipelineResult.from_dict(r) for r in data["results"]]

    def get_bucket_statistics(self, results: List[PipelineResult]) -> dict:
        """
        버킷별 통계 계산

        Args:
            results: PipelineResult 리스트

        Returns:
            dict: 버킷별 개수 및 비율
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

    def print_summary(self, results: List[PipelineResult]):
        """결과 요약 출력"""
        stats = self.get_bucket_statistics(results)
        print("\n=== 파이프라인 결과 요약 ===")
        print(f"총 처리 건수: {stats['total']}")
        print(f"  A (자동 확정): {stats['A'].get('count', 0)} ({stats['A'].get('ratio', 0)*100:.1f}%)")
        print(f"  B (빠른 검수): {stats['B'].get('count', 0)} ({stats['B'].get('ratio', 0)*100:.1f}%)")
        print(f"  C (집중 검수): {stats['C'].get('count', 0)} ({stats['C'].get('ratio', 0)*100:.1f}%)")


# 테스트용 코드
if __name__ == "__main__":
    print("파이프라인 모듈 테스트")
    print("=" * 40)

    # 파이프라인 생성 (모델은 아직 로드되지 않음)
    pipeline = LabelingPipeline()

    # 테스트용 가상 결과 (정규화 테스트를 위해 숫자/영문 포함)
    test_results = [
        PipelineResult(
            sample_id="test_001",
            text_raw="2024년에 KDH가 만들었습니다",
            bucket="A",
            reason="high_confidence",
            metrics={"avg_logprob": -0.15}
        ),
        PipelineResult(
            sample_id="test_002",
            text_raw="테스트 문장입니다",
            bucket="B",
            reason="medium_confidence",
            metrics={"avg_logprob": -0.5}
        ),
    ]

    # 통계 출력
    pipeline.print_summary(test_results)

    # 정규화 테스트
    test_results[0].text_verified = "2024년에 KDH가 만들었습니다"
    normalized = pipeline.normalize_results(test_results)
    print(f"\n정규화 테스트:")
    print(f"  원본: {test_results[0].text_verified}")
    print(f"  정규화: {normalized[0].text_normalized}")

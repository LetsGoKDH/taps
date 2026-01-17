"""
# Whisper ASR 래퍼 모듈

faster-whisper를 사용하여 음성을 텍스트로 변환합니다.
설정값들을 한 곳에서 관리하고, 결과를 일관된 형식으로 반환합니다.
"""

from typing import Union, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class TranscriptionResult:
    """
    ASR 결과를 담는 데이터 클래스

    dataclass란?
    - 데이터를 담는 클래스를 쉽게 만드는 Python 기능
    - __init__, __repr__ 등을 자동으로 만들어줌

    사용 예시:
        result = TranscriptionResult(text="안녕", avg_logprob=-0.2, ...)
        print(result.text)  # "안녕"
    """
    text: str                    # ASR이 인식한 텍스트
    avg_logprob: float           # 평균 로그 확률 (신뢰도)
    compression_ratio: float     # 압축 비율 (반복 탐지용)
    language: str                # 감지된 언어
    duration: float              # 오디오 길이 (초)


class Transcriber:
    """
    Whisper ASR 래퍼 클래스

    사용법:
        transcriber = Transcriber()  # 모델 로드 (시간 걸림)
        result = transcriber.transcribe("audio.wav")
        print(result.text)
    """

    # 기본 설정값들 (3.1에서 결정한 값들)
    DEFAULT_MODEL = "large-v3"
    DEFAULT_BEAM_SIZE = 5
    DEFAULT_LANGUAGE = "ko"

    def __init__(
        self,
        model_size: str = DEFAULT_MODEL,
        device: str = "auto",
        compute_type: str = "auto"
    ):
        """
        Transcriber 초기화 (모델 로드)

        Args:
            model_size: 모델 크기 ("large-v3" 권장)
            device: "cuda" (GPU) 또는 "cpu"
                    "auto"면 자동 감지
            compute_type: 연산 타입
                    "auto"면 device에 따라 자동 선택

        참고:
            모델 로드는 처음 한 번만 하면 됨 (시간 좀 걸림)
            이후 transcribe()는 빠름
        """
        # faster-whisper import (여기서 하는 이유: 설치 안 됐을 때 에러 메시지 명확하게)
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper가 설치되지 않았습니다.\n"
                "설치: pip install faster-whisper"
            )

        # device 자동 감지
        if device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Device 자동 감지: {device}")

        # compute_type 자동 선택
        if compute_type == "auto":
            # GPU면 float16 (빠름), CPU면 int8 (메모리 절약)
            compute_type = "float16" if device == "cuda" else "int8"

        print(f"모델 로드 중: {model_size} (device={device}, compute_type={compute_type})")

        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type
        )
        self.device = device

        print("모델 로드 완료!")

    def transcribe(
        self,
        audio: Union[str, np.ndarray],
        language: str = DEFAULT_LANGUAGE,
        beam_size: int = DEFAULT_BEAM_SIZE
    ) -> TranscriptionResult:
        """
        음성을 텍스트로 변환

        Args:
            audio: 오디오 파일 경로 (str) 또는 numpy array
            language: 언어 코드 ("ko" = 한국어)
            beam_size: 빔 서치 크기 (클수록 정확하지만 느림)

        Returns:
            TranscriptionResult: 변환 결과

        사용 예시:
            # 파일 경로로
            result = transcriber.transcribe("audio.wav")

            # numpy array로 (HuggingFace 데이터셋에서 가져올 때)
            result = transcriber.transcribe(sample["audio"]["array"])
        """
        # Whisper 실행
        segments, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=beam_size,
            # temperature 설정: 0으로 시작, 실패하면 올림
            temperature=[0.0, 0.2, 0.4],
            # VAD 필터: 무음 구간 자동 제거
            vad_filter=True
        )

        # segments는 제너레이터라서 리스트로 변환
        # (제너레이터: 한 번만 순회 가능, 리스트로 바꿔야 여러 번 접근 가능)
        segments = list(segments)

        # 결과 합치기
        # (짧은 오디오는 segment 1개, 긴 오디오는 여러 개)
        if len(segments) == 0:
            # 아무것도 인식 못함
            return TranscriptionResult(
                text="",
                avg_logprob=-1.0,  # 최저 신뢰도
                compression_ratio=0.0,
                language=language,
                duration=info.duration
            )

        # 모든 segment의 텍스트 합치기
        full_text = "".join(seg.text for seg in segments)

        # 메트릭은 평균값 사용
        avg_logprob = sum(seg.avg_logprob for seg in segments) / len(segments)
        compression_ratio = sum(seg.compression_ratio for seg in segments) / len(segments)

        return TranscriptionResult(
            text=full_text.strip(),
            avg_logprob=avg_logprob,
            compression_ratio=compression_ratio,
            language=info.language,
            duration=info.duration
        )

    def transcribe_batch(
        self,
        audio_list: list,
        language: str = DEFAULT_LANGUAGE,
        beam_size: int = DEFAULT_BEAM_SIZE,
        show_progress: bool = True
    ) -> list:
        """
        여러 오디오를 한꺼번에 처리 (배치 처리)

        Args:
            audio_list: 오디오 파일 경로 또는 numpy array의 리스트
            show_progress: tqdm 진행률 표시 여부

        Returns:
            list[TranscriptionResult]: 결과 리스트

        """
        results = []

        # tqdm: 진행률 표시 라이브러리
        if show_progress:
            try:
                from tqdm import tqdm
                audio_list = tqdm(audio_list, desc="Transcribing")
            except ImportError:
                print("tqdm 미설치 - 진행률 표시 없이 진행")

        for audio in audio_list:
            try:
                result = self.transcribe(audio, language, beam_size)
                results.append(result)
            except Exception as e:
                # 에러 나도 멈추지 않고 계속 진행
                print(f"에러 발생: {e}")
                # 빈 결과 추가
                results.append(TranscriptionResult(
                    text="[ERROR]",
                    avg_logprob=-1.0,
                    compression_ratio=0.0,
                    language=language,
                    duration=0.0
                ))

        return results


# CLI로 테스트할 때 사용
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("사용법: python -m taps.asr.transcriber <audio_file>")
        sys.exit(1)

    audio_path = sys.argv[1]
    transcriber = Transcriber()
    result = transcriber.transcribe(audio_path)

    print(f"\n=== 결과 ===")
    print(f"텍스트: {result.text}")
    print(f"신뢰도 (avg_logprob): {result.avg_logprob:.3f}")
    print(f"압축비 (compression_ratio): {result.compression_ratio:.2f}")
    print(f"오디오 길이: {result.duration:.1f}초")

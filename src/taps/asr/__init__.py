"""
ASR (Automatic Speech Recognition) 모듈

Whisper 모델을 래핑하여 음성→텍스트 변환 기능을 제공합니다.
"""

from .transcriber import Transcriber

__all__ = ["Transcriber"]

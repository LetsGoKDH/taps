"""
TAPS 데이터셋 관리 모듈

이 모듈은 TAPS 데이터셋의 다운로드, 로드, 저장을 관리합니다.
"""

from .loader import download_and_save, load_local, get_split

__all__ = ["download_and_save", "load_local", "get_split"]

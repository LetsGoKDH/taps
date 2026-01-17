"""
correct_model v1: BTC 기반 canonicalization 파이프라인

주요 컴포넌트:
- CorrectModelV1: 메인 파이프라인
- BTCWrapper: ByT5-Korean 모델 래퍼
- find_spans: 위험 스팬 탐지 (N3/E2/U1)
- export_issues_to_xlsx / import_xlsx_to_resolutions: Excel I/O
"""

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
from .decision import (
    normalized_edit_distance,
    compute_margin,
    decide_action,
    decide_sentence_action,
)
from .correct_model_v1 import CorrectModelV1
from .excel_io import export_issues_to_xlsx, import_xlsx_to_resolutions

__all__ = [
    # Data models
    "Span",
    "Candidate",
    "Issue",
    "CorrectModelOutput",
    "RiskTag",
    "Bucket",
    "Action",
    # Core functions
    "find_spans",
    "BTCWrapper",
    "normalized_edit_distance",
    "compute_margin",
    "decide_action",
    "decide_sentence_action",
    # Pipeline
    "CorrectModelV1",
    # Excel I/O
    "export_issues_to_xlsx",
    "import_xlsx_to_resolutions",
]

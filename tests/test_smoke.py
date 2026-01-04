import pytest
from taps import normalize_text

def test_normalize_not_implemented():
    with pytest.raises(NotImplementedError):
        normalize_text("테스트")

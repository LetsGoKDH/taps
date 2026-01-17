# correct_model v1 Defect Patch Report

**작성일**: 2026-01-18  
**작성자**: Antigravity Agent  
**버전**: v1.0

---

## 1. 변경 요약 (7개 항목)

1. **(A) cp949 콘솔 인코딩 해결**: `safe_context_marked()` 함수 추가, `⟦⟧` → `[[]]` 대체
2. **(B) 한글 숫자 N3 탐지 확장**: `NUMBER_CONTEXT_PREFIX_KEYWORDS` 상수 추가 (19개 키워드)
3. **(B) 탐지 로직 변경**: `_has_number_prefix_context()` 함수 추가, 앞 문맥 20자 검사
4. **(C) mixed alnum 우선 탐지**: `_find_e2_spans()`에서 `RE_ALNUM_MIXED` 탐지 순서를 순수 영문보다 앞으로 이동
5. **(D) STW_CANON 태그 정리**: `tag="N3"` (placeholder) → `tag="CANON"` 변경
6. **RiskTag 확장**: `Literal["N3", "E2", "U1", "OOV"]` → `Literal["N3", "E2", "U1", "OOV", "CANON"]`
7. **Issue 모델 확장**: `context_marked_safe` 필드 추가

---

## 2. Git 상태

### Commit 1 파일 리스트 (코드 + 최소 문서)

| 파일 | 상태 |
|------|------|
| `README.md` | Modified |
| `docs/progress.md` | Modified |
| `requirements.txt` | Modified |
| `src/taps/__init__.py` | Added |
| `src/taps/pipeline.py` | Added |
| `src/taps/asr/__init__.py` | Added |
| `src/taps/asr/asr_transcribe_1000.py` | Added |
| `src/taps/asr/transcriber.py` | Added |
| `src/taps/correct/__init__.py` | Added |
| `src/taps/correct/btc_wrapper.py` | Added |
| `src/taps/correct/correct_model_v1.py` | Added |
| `src/taps/correct/decision.py` | Added |
| `src/taps/correct/excel_io.py` | Added |
| `src/taps/correct/models.py` | Added |
| `src/taps/correct/span_finder.py` | Added |
| `src/taps/data/__init__.py` | Added |
| `src/taps/data/loader.py` | Added |
| `src/taps/triage/__init__.py` | Added |
| `src/taps/triage/scorer.py` | Added |

### Commit 2 파일 리스트 (문서/산출물)

```
docs/3.4_workflow_implementation.md
docs/bucket_review_workflow.ipynb
docs/correct_model_diagram.puml
docs/correct_model_spec_v1.md
docs/implementation_contract_v1.md
docs/pipeline_diagram.puml
docs/pipeline_sequence.puml
docs/update.md
notebooks/
```

---

## 3. 스모크 테스트 결과

### 테스트 환경
- **CPU Only** (GPU 없음)
- Python 3.x

### 테스트 결과

| 테스트 | 입력 | 결과 | 상태 |
|--------|------|------|------|
| C (mixed alnum) | `COVID19 1234` | `[('E2', 'COVID19'), ('N3', '1234')]` | ✅ 성공 |
| B (prefix context) | `인증번호가 일이삼사야` | `N3: '일이삼사'` | ✅ 성공 |

---

## 4. taps.correct Import 규약

```python
# 1. 메인 파이프라인 import
from taps.correct import CorrectModelV1

# 2. 스팬 탐지 import
from taps.correct.span_finder import find_spans

# 3. 데이터 모델 import
from taps.correct.models import Span, Issue, Candidate, RiskTag, Bucket, Action

# 4. BTC 래퍼 import (lazy loading)
from taps.correct.btc_wrapper import BTCWrapper

# 5. Excel I/O import
from taps.correct.excel_io import export_issues_to_xlsx, import_xlsx_to_resolutions
```

---

## 5. ASR JSONL 샘플 가이드 (CPU 친화적)

### 실행 커맨드

```bash
python -m taps.asr.asr_transcribe_1000 \
    --out_jsonl data/outputs/asr_sample_20.jsonl \
    --max_items 20 \
    --no-resume \
    --device cpu \
    --model_size small
```

### 기대 스키마

```json
{
  "utt_id": "S0001_000001",
  "speaker_id": "S0001",
  "sentence_id": "000001",
  "text_raw": "...",
  "avg_logprob": -0.312,
  "avg_no_speech_prob": 0.008,
  "compression_ratio": 1.52,
  "temperature_fallback": false,
  "language": "ko",
  "duration": 2.8,
  "triage_feat": {"has_digit": false, "latin_count": 0, "unit_like_count": 0}
}
```

---

## 6. BTC 학습 여부 결론

> **"일반 한국어 ByT5 사전학습 모델로 보이며, STW 태스크는 우리 쪽에서 SFT 필요"**

### 근거
1. 모델 카드: "pre-trained on mC4 with 70% Korean and 30% English" - 파인튜닝 언급 없음
2. STW_CANON/STW_SPAN/STW_URL 태스크 토큰 언급 없음
3. 현재 프롬프트는 zero-shot 상태

---

## 7. 커밋 메시지 제안

### Commit 1
```
feat(correct): implement correct_model v1 with defect patches A~D

- Add safe_context_marked() for cp949 console compatibility (A)
- Add NUMBER_CONTEXT_PREFIX_KEYWORDS for Korean number detection (B)
- Prioritize mixed alnum detection in span_finder (C)
- Change STW_CANON issue tag from "N3" to "CANON" (D)
- Add CANON to RiskTag type
- Add context_marked_safe field to Issue model
```

### Commit 2
```
docs: add correct_model v1 design documents and diagrams
```

# Implementation Contract v1 (correct_model + Excel loop)

## 0. 목표 (불변)

**입력**: Whisper 전사 `text_raw` (+가능하면 `avg_logprob`, `compression_ratio`, `language`, `duration`)

**출력**:
- `text_avail` (자동 확정된 canonical; kornormalizer 입력)
- `issues` (검수 필요; Excel로 내보냄)

**핵심**:
- BTC(ByT5-Korean fine-tuned)가 후보 생성/리라이트의 **주력 엔진**
- 규칙/신호는 (i) 스팬 탐지, (ii) 가드레일, (iii) 트리아지만 담당 (**직접 교정 금지**)

---

## 1. BTC 호출 포맷 (확정)

### 1.1 STW_CANON (문장 전체 canonicalization)

**입력**:
```
<STW_CANON>
{text_raw}
</STW_CANON>
```

**출력**: canonical 문장 1개 (plain text)

### 1.2 STW_SPAN (스팬 중심, 스팬만 출력)

**입력**:
```
<STW_SPAN>
LEFT: {left_context}
SPAN: ⟦{raw_span}⟧
RIGHT: {right_context}
</STW_SPAN>
```

**출력**: canonical span 1개 (plain text)

### 1.3 STW_URL (URL/도메인 전용, 자동 확정 금지)

**입력**:
```
<STW_URL>
LEFT: {left_context}
SPAN: ⟦{raw_span}⟧
RIGHT: {right_context}
</STW_URL>
```

**출력**: canonical span 후보 (plain text, Top-K는 디코딩으로 생성)

---

## 2. 임계치 (Threshold) 초안 — "보수적으로 시작"

**원칙**: v1은 자동 확정을 보수적으로. 검수량을 줄이되, 오교정 확정 사고를 막는다.
- 숫자는 일부 자동확정 허용
- URL은 자동확정 금지
- 나머지는 기본 검수

### 2.1 트리아지 버킷 (확정 비율 기반)

| Bucket | Percentile |
|--------|------------|
| RED | 0–3% |
| ORANGE | 3–15% |
| YELLOW | 15–40% |
| GREEN | 40–100% |

**버킷 점수 우선순위**:
1. `avg_logprob` 있으면 그것으로 정렬 (낮을수록 위험)
2. 없으면 텍스트 기반 위험점수로 fallback (고위험 스팬 개수, URL 여부 등)

### 2.2 자동 확정 (Apply BTC output) 허용 조건

자동 확정은 **"스팬 단위"**가 원칙. 문장 전체(STW_CANON)는 GREEN/YELLOW에서만 시도.

#### 공통 가드레일 (하나라도 걸리면 NEEDS_REVIEW)

| 조건 | 결과 |
|------|------|
| U1(URL/도메인) 스팬 | 항상 NEEDS_REVIEW |
| 관용구/고정표현 의심 | NEEDS_REVIEW |
| `change_ratio > 0.35` | NEEDS_REVIEW (의미 변형 위험) |
| 스팬 출력이 공백/빈 문자열/기호만 | NEEDS_REVIEW |

> `change_ratio` 정의: `normalized_edit_distance(raw, btc_output)`, 0~1

#### N3(숫자) 스팬 자동 확정 (초안)

| 조건 | 값 |
|------|-----|
| 버킷 | GREEN 또는 YELLOW |
| BTC 후보 신뢰도 | `margin ≥ 0.25` |
| 변화량 | `change_ratio ≤ 0.20` |

> `margin = score(top1) - score(top2)` (score는 logprob 혹은 길이정규화 점수)

위 통과 시 `AUTO_FIX` 허용

#### E2(영문/알파벳) 스팬 자동 확정 (초안)

기본은 검수(`NEEDS_REVIEW`)로 시작

예외적으로 아래를 **다 만족**하면 `AUTO_FIX` 허용:
- 버킷 GREEN
- `margin ≥ 0.35`
- `change_ratio ≤ 0.15`
- 출력에 한글-영문 혼종이 새로 생기지 않음 (원문 대비 문자군 급격 변화 방지)

#### 문장 전체(STW_CANON) 자동 확정 (초안)

| 조건 | 값 |
|------|-----|
| 버킷 | GREEN만 |
| 문장 내 U1 스팬 | 없을 것 |
| 변화량 | `change_ratio(sentence) ≤ 0.18` |

위 통과 시 `AUTO_FIX` 허용, 아니면 검수

> **주의**: 이 임계치는 "초안"이며, 1000개에서 검수량/오교정률을 보고 조정한다.

---

## 3. 함수 시그니처 (필수 인터페이스)

Python 기준 (클래스/모듈 구조는 자유). 아래 시그니처는 유지.

### 3.1 데이터 모델

```python
from dataclasses import dataclass
from typing import List, Optional, Literal, Tuple, Dict, Any

RiskTag = Literal["N3", "E2", "U1", "OOV"]
Bucket = Literal["RED", "ORANGE", "YELLOW", "GREEN"]
Action = Literal["AUTO_FIX", "NEEDS_REVIEW", "PASS"]

@dataclass
class Span:
    start: int
    end: int
    text: str
    tag: RiskTag
    left: str
    right: str

@dataclass
class Candidate:
    text: str
    score: float  # higher is better (normalize inside btc wrapper)

@dataclass
class Issue:
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

    candidates: List[Candidate]
    recommended: str
    user_fix: str  # prefilled = recommended

    meta: Dict[str, Any]  # avg_logprob, compression_ratio, duration, language, etc.
```

### 3.2 Span Finder (규칙/신호: "탐지 전용")

```python
def find_spans(text_raw: str) -> List[Span]:
    """
    Return risk spans to rewrite/review.
    Must avoid OOV explosion: use Kiwi optionally to strip particles/endings for OOV tagging.
    Do NOT modify text here.
    """
```

### 3.3 BTC Wrapper (ByT5-Korean)

```python
def btc_generate_candidates(task: Literal["STW_CANON", "STW_SPAN", "STW_URL"],
                            left: str,
                            span: str,
                            right: str,
                            k: int = 5) -> List[Candidate]:
    """
    Call BTC model with the agreed prompt format.
    Return top-k candidates with normalized scores.
    """
```

> 문장 전체 모드일 때는 `span`에 전체 문장을 넣고 `left`/`right` 빈 문자열로 처리 가능

### 3.4 Scoring / Guardrails

```python
def normalized_edit_distance(a: str, b: str) -> float:
    """Return value in [0,1]."""

def decide_action(tag: RiskTag,
                  bucket: Bucket,
                  candidates: List[Candidate],
                  raw_span_or_sentence: str,
                  recommended: str,
                  is_url_present_in_sentence: bool) -> Action:
    """
    Apply the threshold policy:
    - U1 always NEEDS_REVIEW
    - N3/E2 conditional AUTO_FIX
    - STW_CANON only GREEN and no URL and low change
    """
```

### 3.5 Issue Builder

```python
def build_issue(record_meta: Dict[str, Any],
                span: Span,
                bucket: Bucket,
                candidates: List[Candidate]) -> Issue:
    """Create Issue with context_full/marked, recommended/user_fix prefill."""
```

### 3.6 Apply Resolutions (Excel 결과 반영)

```python
def apply_resolutions(text_raw: str,
                      issues: List[Issue],
                      resolved_user_fixes: Dict[Tuple[int,int], str]) -> str:
    """
    Replace spans in text_raw using resolved_user_fixes keyed by (start,end).
    Must handle overlap: resolve by priority (longer span first), then earlier span.
    """
```

---

## 4. Excel I/O 계약 (최소 컬럼)

### Export columns (필수)

| 컬럼 | 설명 |
|------|------|
| `utt_id` | utterance ID |
| `speaker_id` | 화자 ID |
| `sentence_id` | 문장 ID |
| `bucket` | RED/ORANGE/YELLOW/GREEN |
| `tag` | N3/E2/U1/OOV |
| `span_start` | 스팬 시작 인덱스 |
| `span_end` | 스팬 끝 인덱스 |
| `raw_span` | 원본 스팬 텍스트 |
| `context_marked` | `LEFT + ⟦SPAN⟧ + RIGHT` |
| `candidates` | stringify top-k |
| `recommended` | 추천 후보 |
| `user_fix` | 사용자 수정 (prefill = recommended) |
| `avg_logprob` | (있으면) |
| `compression_ratio` | (있으면) |

### Import rules

- `user_fix`가 비어있으면 `recommended`로 간주
- 변경 여부/검수 완료 여부를 로그로 남김

---

## 5. 실행 순서 (Colab에서)

1. **Whisper 전사** → `asr_results.jsonl` 저장

2. **correct_model 실행**:
   - `find_spans` → `btc_generate_candidates` → `decide_action`
   - → `issues` / `text_avail` 저장

3. **issues** → `review.xlsx` export

4. **사용자 검수 후** `review.xlsx` import
   - → `resolutions.jsonl` + `text_avail_final.jsonl`

5. **text_avail_final** → kornormalizer → 평가/저장

---

## 6. 초기 하이퍼파라미터 (운영값)

| 파라미터 | 값 |
|----------|-----|
| Span context 길이 | left/right 각 40자 (초기) |
| Candidate k | 5 |
| STW_CANON 사용 조건 | GREEN only |
| E2 자동확정 | v1은 매우 보수적 (기본 검수) |

---

*작성일: 2026-01-17*

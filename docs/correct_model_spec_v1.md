# Correct Model Spec v1 (Design Doc)

Version: `v1.1`
Status: **Approved (per user decisions)**
Owner: (project)
Last updated: 2026-01-17

---

## 1. Goal and Scope

### 1.1 Purpose
`correct_model` sits **between ASR (Whisper)** and **kornormalizer**. Its job is to:

1) **Canonicalize** ambiguous or mixed-form ASR outputs into a stable, standardized input so that `kornormalizer` applies its existing rules reliably.
2) **Route uncertain/high-risk spans to human review** with recommended fixes (span-centric review).
3) **Minimize total human review volume over time** by logging review resolutions as training data (active learning loop).

### 1.2 Non-goals
- 100% automated correction is not a goal. Human review is assumed necessary for certain cases.
- `correct_model` does **not** replace `kornormalizer`. It prepares inputs *for* `kornormalizer`.

---

## 2. Pipeline Placement

```
Acoustic Audio
  -> ASR (Whisper-large-v3; beam/N-best enabled by policy)
  -> correct_model (this doc)
  -> kornormalizer (project-owned rules)
  -> verifier (future)
```

---

## 3. Inputs and Outputs

### 3.1 Required Input Fields (per utterance)
- `speaker_id` (string)
- `sentence_id` (string or int; stable identifier)
- `text_raw` (string): Whisper top-1 transcript
- Whisper confidence/meta (prefer segment-level; fall back to utterance-level):
  - `avg_logprob`
  - `compression_ratio`
  - `no_speech_prob`
- `segments[]` (optional but recommended): per-segment text + meta
- `n_best[]` (required in RED/ORANGE buckets; optional otherwise):
  - list of alternative hypotheses with scores

### 3.2 Output Contract
- `decision`: `AUTO_PASS | AUTO_FIX | NEEDS_REVIEW`
- `text_avail`:
  - `AUTO_PASS`: equals `text_raw`
  - `AUTO_FIX`: canonicalized string
  - `NEEDS_REVIEW`: **null** (explicitly prevents downstream use before review)
- `issues[]`: list of span-centric review items (see schema)
- `audit`: includes policy version and routing signals for reproducibility

---

## 4. Canonicalization Policies (Final)

### 4.1 Numbers: **N3 (surface + meta)**
Numbers are represented in canonical text, but their interpretation is captured in candidate metadata.

#### 4.1.1 Surface form rule (approved)
| number_type | 표면형 | 예시 |
|-------------|--------|------|
| CARDINAL | digits | "1234" |
| DIGIT_SEQUENCE | spaced digits | "1 2 3 4" |
| YEAR/DATE/TIME/PHONE/... | 추후 확장 | (초기에는 최소 YEAR 정도만) |
| UNKNOWN | 자동 확정 금지 | Issue 생성 |

#### 4.1.2 Examples
- "수량/금액/회수" 문맥: `일이삼사` -> `"1234"` with `number_type=CARDINAL`
- "인증번호/코드/ID/OTP/전화" 문맥: `일이삼사` -> `"1 2 3 4"` with `number_type=DIGIT_SEQUENCE`
- Ambiguous: create Issue with both candidates + keep-raw option.

### 4.2 English/Alphabet: **E2**
If English/Latin is present or strongly suspected:
- Generate **English candidates** and route as span Issues when uncertain.
- Auto-confirmation is conservative (especially if URL/domain-like).

### 4.3 URL/Domain: **U1**
For phonetic Korean renderings of URLs/domains (e.g., "다음 점 지지지"):
- **No automatic confirmation**.
- Always generate candidates (best-effort) and route to review via `URL_CANDIDATE` Issue.

### 4.4 OOV (Out-of-vocabulary) Handling: conditional trigger, no auto-replace
OOV is not a blanket review trigger. It is promoted to review **only if**:
- token is Hangul 2–6 chars (configurable),
- not in lexicon,
- AND one of:
  - strong near-lexicon candidates exist (edit distance / similarity),
  - included in a failed idiom/fixed-phrase match span,
  - morphological analysis suggests anomaly.

**Auto-replacement is disabled** in v1; only propose candidates.

#### 4.4.1 OOV 체크 단위
- "장난감을"처럼 조사 붙은 단어를 통째로 OOV로 보면 검수량 폭증
- OOV 체크 단위는 **"표면 토큰"이 아니라 "어간/표제 형태"**
- 형태소 분석(키위/메캅)을 OOV 트리거의 **전처리로만** 사용 (교정에 쓰지 않음)

### 4.5 관용구/고정표현 파괴 탐지
"제 도끼에 제 발등" → "제도기의 재발동" 같은 케이스는 **OOV로 못 잡음** (틀린 단어가 없음)

#### 4.5.1 퍼지 매칭 기반 탐지 (권장)
- 관용구 리스트 준비 (100~500개 MVP)
- 문장 내 n-gram을 훑으면서 "관용구와 유사하지만 정확히 다름" 탐지
- `IDIOM_SUSPECT` Issue 생성, 후보로 정상 관용구 추천

#### 4.5.2 avg_logprob 연계
- 관용구 파괴 케이스는 대부분 avg_logprob 하위에 분포
- RED/ORANGE 버킷에서 관용구 탐지를 더 공격적으로 적용

---

## 5. Triage and Buckets

### 5.1 Bucket thresholds (approved initial)
Buckets are based on `avg_logprob` percentile **within batch** (not absolute thresholds).

| Bucket | Percentile | 처리 방식 |
|--------|------------|-----------|
| **RED** | 0–3% | 거의 항상 Issue 생성 + N-best 기반 + 스팬 검수 우선 |
| **ORANGE** | 3–15% | N-best + STW 후 불확실성 기준으로 Issue |
| **YELLOW** | 15–40% | 고위험 토큰/혼종 스팬만 Issue (spot-check) |
| **GREEN** | 40–100% | 기본 자동, 단 고위험 토큰이면 최소 1개 스팟 체크 가능 |

These are **initial**; will be calibrated using the held-out 1,000 test set (bucket-wise error rate).

### 5.2 N-best policy (approved)
- `RED` and `ORANGE`: **N-best is mandatory** (beam search / multiple hypotheses).
- `YELLOW`/`GREEN`: top-1 only by default; trigger N-best if high-risk token detected.

---

## 6. Span-centric Review (Issues)

### 6.1 Why span-centric
- Faster human review: reviewer checks *only highlighted spans*.
- Supports learning: each Issue becomes a labeled training instance.

### 6.2 Required Issue Types (v1)
- `NUMBER_AMBIG`, `NUMBER_FORMAT`
- `ALPHA_CANDIDATE`
- `URL_CANDIDATE`
- `OOV_SUSPECT`
- `IDIOM_SUSPECT`
- `TOKEN_NOISE` (optional)

---

## 7. Output Schema (v1)

### 7.1 CorrectModelOutput (JSON)
```json
{
  "speaker_id": "S0001",
  "sentence_id": "000123",
  "utterance_id": "S0001_000123",

  "asr": {
    "text_raw": "인증번호가 일이삼사야",
    "avg_logprob": -1.23,
    "no_speech_prob": 0.01,
    "compression_ratio": 1.18,
    "bucket": "ORANGE",
    "n_best": [
      {"text": "인증번호가 일이삼사야", "score": -1.23},
      {"text": "인증 번호가 일이 삼사야", "score": -1.31}
    ]
  },

  "decision": "NEEDS_REVIEW",
  "text_avail": null,

  "issues": [
    {
      "issue_id": "S0001_000123_iss_01",
      "issue_type": "NUMBER_AMBIG",
      "span": {"start": 6, "end": 10},
      "raw_span": "일이삼사",
      "context": "인증번호가 일이삼사야",
      "severity": "ORANGE",

      "candidates": [
        {
          "text": "1 2 3 4",
          "score": 0.62,
          "reason": "context suggests DIGIT_SEQUENCE",
          "meta": {"number_type": "DIGIT_SEQUENCE", "format": "spaced_digits"}
        },
        {
          "text": "1234",
          "score": 0.55,
          "reason": "ITN digits candidate",
          "meta": {"number_type": "CARDINAL", "format": "digits"}
        },
        {
          "text": "일이삼사",
          "score": 0.40,
          "reason": "keep raw",
          "meta": {"number_type": "UNKNOWN"}
        }
      ],
      "recommended": 0,

      "routing": {
        "bucket": "ORANGE",
        "asr_risk_score": 0.78,
        "stw_confidence": 0.58,
        "policy_flags": ["HIGH_RISK_NUMBER"]
      }
    }
  ],

  "audit": {
    "pipeline_version": "correct_model_v1",
    "canonical_policy": {"number": "N3", "alpha": "E2", "url": "U1", "oov": "conditional"}
  }
}
```

### 7.2 Candidate meta conventions
- Numbers: `meta.number_type`, `meta.format`
- URLs: `meta.url_candidate=true/false`
- Alphabet: `meta.alpha_candidate=true/false`

---

## 8. Resolution Logging (required for learning loop)

To reduce review volume over time, every `Issue` must store a resolution.

### 8.1 Minimal Resolution Schema
```json
{
  "issue_id": "S0001_000123_iss_01",
  "resolved_by": "human",
  "resolution": {
    "chosen_candidate_index": 0,
    "final_text": "1 2 3 4",
    "final_meta": {"number_type": "DIGIT_SEQUENCE"}
  },
  "timestamp": "2026-01-17T12:34:56+09:00"
}
```

- If the reviewer types a custom string, record `chosen_candidate_index=null` and store `final_text`.

---

## 9. Review Workflow: JSON ↔ Excel

### 9.1 개요
- correct_model이 JSON 출력
- JSON → Excel 변환 (사용자 친화적 검수용)
- 사용자가 Excel에서 수정
- Excel → JSON 역변환 (학습용 + normalizer용)

### 9.2 Excel 컬럼 (행 = Issue 1개)

| 컬럼 | 설명 |
|------|------|
| `speaker_id` | 화자 ID |
| `sentence_id` | 문장 ID |
| `issue_id` | Issue ID |
| `context_marked` | 의심 스팬을 `⟦ ⟧` 마커로 표시한 문장 |
| `raw_span` | 스팬 텍스트 |
| `issue_type` | Issue 유형 |
| `severity` | RED / ORANGE / YELLOW |
| `candidates` | 후보 리스트 (추천 후보는 별도 표시) |
| `recommended` | 추천 후보 텍스트 |
| `user_fix` | 사용자 수정 (초기값 = recommended) |
| `status` | done / skip |
| `notes` | (선택) 메모 |

### 9.3 역변환 출력 2종
1. **학습용**: (input=text_raw, output=user_fix, + issue_type/metadata)
2. **normalizer용**: sentence 단위로 Issue들을 적용해서 만든 `text_avail`

---

## 10. What We Need Before Implementation

### 10.1 Whisper 출력 확장 (engineering contract)

#### 현재 TranscriptionResult
| Field | Type | 현재 상태 |
|-------|------|-----------|
| `text` | str | ✅ 있음 (= text_raw) |
| `avg_logprob` | float | ✅ 있음 (utterance-level) |
| `compression_ratio` | float | ✅ 있음 |
| `language` | str | ✅ 있음 |
| `duration` | float | ✅ 있음 |
| `no_speech_prob` | float | ❌ 없음 (추가 필요) |
| `segments[]` | list | ❌ 버려짐 (보존 필요) |
| `n_best[]` | list | ❌ 없음 (beam_size=5지만 top1만 반환) |

#### 필요한 확장
1. **`no_speech_prob` 추가**: faster-whisper `info`에서 가져올 수 있음
2. **`segments[]` 보존**: 스팬 위치 파악용 (현재 평균 내고 버림)
3. **N-best 대안**: temperature 다르게 여러 번 디코딩으로 pseudo n-best 생성

### 10.2 Lexicon resources for OOV/idiom triggers

1. **Korean lexicon set**
   - Source: mecab-ko-dic 표제어 set
   - 형태소 분석으로 어간 추출 후 사전 조회

2. **Idiom/fixed-phrase list (MVP)**
   - 100~500개 규모 관용구 리스트
   - 퍼지 매칭으로 파괴 탐지

### 10.3 kornormalizer 호환성
- kornormalizer가 처리 가능한 입력:
  - digits (`1234`)
  - spaced digits (`1 2 3 4`)
  - raw Latin tokens
- 참조: https://github.com/LetsGoKDH/Kornormalizer

### 10.4 Evaluation protocol
- **Gold**: `kornormalizer(correct_model(text_raw))` vs `text_normalized`
- **Metrics**:
  - 단어 단위 정확도 (spacing보다 중요)
  - 고위험 토큰 오류율 (numbers/alpha/url)
  - 검수량 (% NEEDS_REVIEW, # issues per utterance)
- **Bucket calibration**: bucket별 오류율 측정

---

## 11. Implementation Order (v1)

1. **TranscriptionResult 확장**: segment 보존 + `no_speech_prob` 포함
2. **Issue 생성기 v1**: 숫자/알파벳/URL + 관용구 퍼지 매칭 + 조건부 OOV
3. **JSON↔Excel 툴**: 검수 루프 구축
4. **학습형 STW/BTC**: 검수량 감소를 위한 모델 학습

---

## 12. Open Questions (intentionally deferred)
- Final model architecture (STW/WTS/BTC) selection and training regimen
- Advanced URL reverse-mapping quality improvements
- Verifier module spec (post-kornormalizer)

These are separate design docs once implementation groundwork is in place.

---

*작성일: 2026-01-17*

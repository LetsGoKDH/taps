# Korean Speech Data Normalization (TAPS)

TAPS 데이터셋(Training/Validation)을 대상으로 한국어 음성 데이터 정규화 및
라벨링 자동화 워크플로우/검증 시스템을 구축하는 프로젝트입니다.

## 목표 (Scope)
- TAPS 텍스트(라벨) 정규화 규칙 수립 및 구현
- 정규화 파이프라인을 포함한 라벨링 자동화 워크플로우 구성/구현
- 회귀 테스트(엣지케이스) 기반 안정화
- 한국어 정규화를 고려한 CER 평가 시스템 구축(기존 툴 보완)

## 작업 대상 (Dataset)
- Hugging Face: `yskim3271/Throat_and_Acoustic_Pairing_Speech_Dataset`
- 범위: Training / Validation split

> 대용량 데이터(오디오 등)는 Git에 커밋하지 않습니다.
> 데이터 버전/리비전/샤드 범위/샘플링 seed 등 "재현 정보"만 문서로 기록합니다.

---

## 파이프라인 개요 (Pipeline Overview)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    전체 라벨링 자동화 파이프라인                           │
└─────────────────────────────────────────────────────────────────────────┘

Stage A. 데이터 입력
    │  Acoustic audio (1,000개 PoC)
    │  식별자: speaker_id, sentence_id → utt_id
    ▼
Stage B. ASR (Whisper)
    │  faster-whisper-large-v3
    │  출력: text_raw, avg_logprob, compression_ratio, ...
    ▼
Stage C. correct_model ★
    │  입력: utt_id, text_raw, ASR meta
    │  출력: text_avail (자동확정) + text_check (Issue → Excel)
    ▼
Stage D. 1차 검수 (Excel)
    │  user_fix 수정/확정
    │  출력: text_avail_final
    ▼
Stage E. kornormalizer
    │  출력: text_normalized
    ▼
Stage F. verifier (2차 검증, 추후)
    │  출력: text_fin + text_check2
    ▼
Stage G. 학습 루프
    └  검수 결과 누적 → BTC 파인튜닝 → verifier 개선
```

### correct_model 구성 (3 레이어)

| 레이어 | 역할 | 설명 |
|--------|------|------|
| **Span Finder** | 신호/규칙 | 숫자/알파벳/URL/OOV 스팬 탐지 (교정 금지) |
| **BTC Rewriter** | 주력 엔진 | ByT5-Korean 백본, KsponSpeech STW/WTS 파인튜닝 |
| **Decision Layer** | 정책/가드레일 | 자동확정 vs 검수 결정 (U1/N3/E2/OOV 정책) |

### 정책 요약

| 정책 | 설명 |
|------|------|
| **U1** (URL/도메인) | 자동확정 금지, 항상 검수 |
| **N3** (숫자) | BTC 확신도 높으면 자동확정 가능 |
| **E2** (영문/알파벳) | 혼종/도메인은 검수 |
| **OOV** | 어간 기준 조건부 트리거 |

### 트리아지 버킷

| Bucket | Percentile | 처리 |
|--------|------------|------|
| RED | 0–3% | N-best + 집중 검수 |
| ORANGE | 3–15% | N-best + 불확실성 기반 검수 |
| YELLOW | 15–40% | 고위험 토큰만 spot-check |
| GREEN | 40–100% | 자동 통과 |

> 상세 설계: [docs/correct_model_spec_v1.md](docs/correct_model_spec_v1.md)

---

## 현재 진행 상황 (Current Status)

### 완료한 작업
- ✅ **3.1 라벨링 자동화 워크플로우 조사** (2026-01-06)
  - 베이스 워크플로우 확정: **하이브리드 접근** (ASR → 트리아지 → 선택적 검수 → 규칙 정규화)
  - ASR 모델 벤치마크 완료: **Whisper Large-v3 선정** (CER 6.71%)
  - 한국어 도메인 적용 방법 결정: 결정론적 규칙 기반, 모듈화, 보수적 정규화
  - 상세: [docs/3.1_labeling_workflow_survey.md](docs/3.1_labeling_workflow_survey.md)

- ✅ **3.2 한국어 도메인 조사** (2026-01-12)
  - 한국어 특성 분석: 숫자 표기, 알파벳/외래어, 복합명사, 1음절 명사
  - **Kornormalizer 모듈 구현**: [LetsGoKDH/Kornormalizer](https://github.com/LetsGoKDH/Kornormalizer)
    - NumberToKorean, AlphabetToKorean, CompoundNounSplitter
    - 사전 데이터 152,000+ 항목 (국립국어원 + 법제처)
  - 상세: [docs/3.2_korean_domain_analysis.md](docs/3.2_korean_domain_analysis.md)

- ✅ **3.3 라벨링 자동화 워크플로우 구성** (2026-01-13)
  - 폴더 구조 설계: `data/taps_dataset/`, `data/outputs/`, `data/triage/`
  - 데이터 로더 모듈 구현: `src/taps/data/loader.py`
  - 4단계 파이프라인: ASR → 트리아지 → 검수 → 정규화
  - 상세: [docs/3.3_workflow_design.md](docs/3.3_workflow_design.md)

### 사전 작업
- Normalizer v0.6.4 임시 구현 ([src/taps/normalizer.py](src/taps/normalizer.py))
- Whisper 기반 ASR + 정규화 파이프라인 테스트 ([docs/pre_test.ipynb](docs/pre_test.ipynb))

### 다음 단계
로드맵 3.4 (라벨링 자동화 워크플로우 구현)부터 진행 예정입니다. 자세한 진행 상황은 [docs/progress.md](docs/progress.md)를 참고해주세요.

---

## 기술 스택 (Tech Stack)
- Python 3.10+
- **ASR 모델**: Whisper Large-v3 (`Systran/faster-whisper-large-v3`)
  - 설정: beam_size=5, language="ko", temperature=[0.0, 0.2, 0.4]
  - TAPS Test CER: 6.71%
- **정규화 엔진**: [Kornormalizer](https://github.com/LetsGoKDH/Kornormalizer) (규칙 기반 + 사전)
- 테스트: `pytest`
- 코드 품질(선택): `ruff` / `black`
- 평가: CER/WER 계산 스크립트(한국어 정규화 반영)

---

## Quickstart (Install / Run / Test)

### 설치 (Installation)

```powershell
# 1) Create venv
python -m venv .venv

# 2) Activate venv (Windows PowerShell)
.venv\Scripts\Activate.ps1

# 3) Install dependencies
pip install -r requirements.txt

# 4) Set PYTHONPATH
$env:PYTHONPATH="src"
```

### Kornormalizer 사용 (Using Kornormalizer)

```python
from kornormalizer import Normalizer

# 기본 사용 (숫자, 알파벳 변환)
normalizer = Normalizer()
result = normalizer.normalize("2024년 KBS 방송")
# → "이천 이십 사 년 케이 비 에스 방송"

# 복합명사 분리 포함
normalizer = Normalizer(use_noun_splitter=True)
result = normalizer.normalize("데이터베이스시스템 구축")
# → "데이터베이스 시스템 구축"
```

> **Note**: Kornormalizer는 별도 저장소에서 관리됩니다: [LetsGoKDH/Kornormalizer](https://github.com/LetsGoKDH/Kornormalizer)

### 데이터셋 로드 (Loading Dataset)

```python
from taps.data import download_and_save, load_local

# 처음 한 번만 실행 (인터넷 필요, ~5분 소요)
download_and_save()
# 저장 위치: ./data/taps_dataset/

# 이후부터는 로컬에서 로드 (인터넷 불필요, 빠름)
ds = load_local()
train = ds["train"]
dev = ds["dev"]
test = ds["test"]

# 특정 split만 로드
from taps.data import get_split
train_only = get_split("train")
```

### 테스트 노트북 실행 (Running Test Notebook)

Jupyter Notebook으로 ASR + 정규화 파이프라인을 테스트할 수 있습니다:

```powershell
# Jupyter 설치 (필요시)
pip install jupyter

# 노트북 실행
jupyter notebook docs/pre_test.ipynb
```

### 테스트 실행 (Running Tests)

```powershell
pytest -q
```

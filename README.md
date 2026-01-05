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
> 데이터 버전/리비전/샤드 범위/샘플링 seed 등 “재현 정보”만 문서로 기록합니다.

---

## 현재 진행 상황 (Current Status)

### 완료한 작업
- ✅ **3.1 라벨링 자동화 워크플로우 조사** (2026-01-06)
  - 베이스 워크플로우 확정: **하이브리드 접근** (ASR → 트리아지 → 선택적 검수 → 규칙 정규화)
  - ASR 모델 벤치마크 완료: **Whisper Large-v3 선정** (CER 6.71%)
  - 한국어 도메인 적용 방법 결정: 결정론적 규칙 기반, 모듈화, 보수적 정규화
  - 상세: [docs/3.1_labeling_workflow_survey.md](docs/3.1_labeling_workflow_survey.md)

### 사전 작업
- Normalizer v0.6.4 임시 구현 ([src/taps/normalizer.py](src/taps/normalizer.py))
- Whisper 기반 ASR + 정규화 파이프라인 테스트 ([docs/pre_test.ipynb](docs/pre_test.ipynb))

### 다음 단계
로드맵 3.2부터 진행 예정입니다. 자세한 진행 상황은 [docs/progress.md](docs/progress.md)를 참고해주세요.

---

## 기술 스택 (Tech Stack)
- Python 3.10+
- **ASR 모델**: Whisper Large-v3 (`Systran/faster-whisper-large-v3`)
  - 설정: beam_size=5, language="ko", temperature=[0.0, 0.2, 0.4]
  - TAPS Test CER: 6.71%
- 정규화 엔진: 규칙 기반(Regex/룰) + 필요 시 한국어 형태소 도구(예: Kiwi) 보조
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

### Normalizer 사용 (Using Normalizer)

```python
from taps.normalizer import normalize_v064

# 기본 사용
text = "2024년 1월 5일 COVID-19 확진자 350명"
normalized = normalize_v064(text)
print(normalized)
# 출력: 이천 이십사 년 일 월 오 일 코로나 일구 확진자 삼백 오십 명

# 디버그 모드
normalized = normalize_v064(text, debug=True)
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

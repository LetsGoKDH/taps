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

## 기술 스택 (Tech Stack)
- Python 3.10+
- 정규화 엔진: 규칙 기반(Regex/룰) + 필요 시 한국어 형태소 도구(예: Kiwi) 보조
- 테스트: `pytest`
- 코드 품질(선택): `ruff` / `black`
- 평가: CER/WER 계산 스크립트(한국어 정규화 반영)

---

## Quickstart (Install / Run / Test)

```bash
# 1) Create venv
python -m venv .venv

# 2) Activate venv (Windows PowerShell)
.venv\Scripts\Activate.ps1

# 3) Install deps
pip install -r requirements.txt

# 4) Run normalization (placeholder; finalize after scripts/ are ready)
python scripts/run_normalize.py --in input.txt --out output.txt

# 5) Evaluate CER (placeholder)
python scripts/eval_cer.py --pred pred.txt --gold gold.txt

# 6) Run tests
pytest -q

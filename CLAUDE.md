# CLAUDE.md

## Purpose
Korean text normalization for ASR/dataset preparation.

## Repo structure
- `src/taps/` : library code (normalizer, helpers)
- `tests/`    : pytest tests (regression)
- `scripts/`  : helper scripts (maintenance)
- `docs/`     : design/spec/docs

## Quick commands (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH="src"
pytest -q
```

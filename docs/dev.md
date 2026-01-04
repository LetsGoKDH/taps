# Development Guide

## Environment
- Python 3.10+
- Windows PowerShell (primary)

## Quickstart
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH="src"
pytest -q
```

## Notes
- If PowerShell blocks activation, you can use:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```
- Keep `.venv/` out of Git (already ignored).

# scripts/setup_docs_safe3.ps1
# Create minimal project-level docs scaffolding for this repo.
# Safe to re-run. Use -Force to overwrite existing files.
#
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_docs_safe3.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_docs_safe3.ps1 -Force

param(
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Write-Utf8NoBomFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$Content,
    [switch]$Overwrite
  )
  $dir = Split-Path -Parent $Path
  if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

  if ((Test-Path -LiteralPath $Path) -and (-not $Overwrite)) {
    Write-Host "Skip (exists): $Path"
    return
  }

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
  Write-Host "Wrote: $Path"
}

# --- Resolve repo root ---
# Assumes this script lives at <repo_root>\scripts\
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Ensure-Dir ".\docs"

# -------------------------
# docs/index.md
# -------------------------
$indexLines = @(
  '# Docs',
  '',
  'This directory contains project-level documentation (design/spec/process notes).',
  '',
  '- [Development guide](./dev.md)',
  '- [Data & storage](./data.md)',
  '',
  'If a doc becomes large or needs diagrams, keep it here (not inside code files).'
)
$indexMd = ($indexLines -join "`n") + "`n"

# -------------------------
# docs/dev.md
# -------------------------
$devLines = @(
  '# Development Guide',
  '',
  '## Environment',
  '- Python 3.10+',
  '- Windows PowerShell (primary)',
  '',
  '## Quickstart',
  '```powershell',
  'python -m venv .venv',
  '.venv\Scripts\Activate.ps1',
  'pip install -r requirements.txt',
  '$env:PYTHONPATH="src"',
  'pytest -q',
  '```',
  '',
  '## Notes',
  '- If PowerShell blocks activation, you can use:',
  '  ```powershell',
  '  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned',
  '  ```',
  '- Keep `.venv/` out of Git (already ignored).'
)
$devMd = ($devLines -join "`n") + "`n"

# -------------------------
# docs/data.md
# -------------------------
$dataLines = @(
  '# Data & Storage',
  '',
  '## Policy',
  '- Do NOT commit large audio datasets to this repo.',
  '- Keep datasets outside the repo (e.g., `D:\datasets\taps\...`).',
  '- Version datasets by folder naming + a small metadata file (date, source, preprocessing).',
  '',
  '## Suggested local layout (example)',
  '```text',
  'D:\datasets\taps\',
  '  raw\',
  '  manifests\',
  '  normalized\',
  '  README.txt   (or metadata.json)',
  '```',
  '',
  '## Normalization artifacts',
  'When you generate text normalization outputs used for training/evaluation:',
  '- store them under the dataset folder, not in Git',
  '- but keep small *sample* cases (few lines) in `tests/` or `docs/` for regression'
)
$dataMd = ($dataLines -join "`n") + "`n"

# -------------------------
# CLAUDE.md (repo-level)
# -------------------------
$claudeLines = @(
  '# CLAUDE.md',
  '',
  '## Purpose',
  'Korean text normalization for ASR/dataset preparation.',
  '',
  '## Repo structure',
  '- `src/taps/` : library code (normalizer, helpers)',
  '- `tests/`    : pytest tests (regression)',
  '- `scripts/`  : helper scripts (maintenance)',
  '- `docs/`     : design/spec/docs',
  '',
  '## Quick commands (PowerShell)',
  '```powershell',
  'python -m venv .venv',
  '.venv\Scripts\Activate.ps1',
  'pip install -r requirements.txt',
  '$env:PYTHONPATH="src"',
  'pytest -q',
  '```'
)
$claudeMd = ($claudeLines -join "`n") + "`n"

# Write files
$overwrite = $Force.IsPresent
Write-Utf8NoBomFile -Path ".\docs\index.md" -Content $indexMd -Overwrite:$overwrite
Write-Utf8NoBomFile -Path ".\docs\dev.md"   -Content $devMd   -Overwrite:$overwrite
Write-Utf8NoBomFile -Path ".\docs\data.md"  -Content $dataMd  -Overwrite:$overwrite
Write-Utf8NoBomFile -Path ".\CLAUDE.md"     -Content $claudeMd -Overwrite:$overwrite

Write-Host ""
Write-Host "Done. Next (optional):" -ForegroundColor Cyan
Write-Host "  git status"
Write-Host "  git add docs CLAUDE.md"
Write-Host "  git commit -m ""docs: add project docs scaffold"""
Write-Host "  git push"

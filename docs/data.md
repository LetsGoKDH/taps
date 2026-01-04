# Data & Storage

## Policy
- Do NOT commit large audio datasets to this repo.
- Keep datasets outside the repo (e.g., `D:\datasets\taps\...`).
- Version datasets by folder naming + a small metadata file (date, source, preprocessing).

## Suggested local layout (example)
```text
D:\datasets\taps\
  raw\
  manifests\
  normalized\
  README.txt   (or metadata.json)
```

## Normalization artifacts
When you generate text normalization outputs used for training/evaluation:
- store them under the dataset folder, not in Git
- but keep small *sample* cases (few lines) in `tests/` or `docs/` for regression

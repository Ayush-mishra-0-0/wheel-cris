# Phase 3C Benchmark Environment

**Status:** PINNED · Phase 3C benchmark environment
**Date:** 2026-08-08
**Declared:** a **new pinned benchmark environment**. No byte-for-byte
reproducibility claim against Phase 1/2 is made (the office-PC environment is
undocumented and not accessible).

## Context

The original Phase 1/2 experiments ran on an office PC that is not currently
accessible. A repository audit (2026-08-08) found no `requirements.txt`,
`environment.yml`, `pyproject.toml`, `Pipfile`, or lockfile, and no experiment
manifest records package versions. The office environment is therefore
undocumented. Phase 3C proceeds on the personal laptop in a fresh isolated
virtual environment and is explicitly labelled as a new benchmark environment.

## Machine

| Item | Value |
| --- | --- |
| OS | Windows 11 (10.0.26200-SP0), x86-64 |
| Python | 3.14.2 (tags/v3.14.2:df79316, Dec 5 2025) [MSC v.1944 64 bit (AMD64)] |
| Interpreter | `ayush/Scripts/python.exe` |
| CPU | recorded at first Phase 3C run (add below) |
| GPU | none detected (CPU-only) |
| Git commit | `82543defcda5d0d4dc21aaf523582886930786f6` (master, 2026-08-08) |

## Package versions (pip freeze)

See `environment/requirements-lock.txt` (24 packages).

Core stack:

| Package | Version |
| --- | --- |
| pandas | 3.0.5 |
| numpy | 2.5.1 |
| scipy | 1.18.0 |
| scikit-learn | 1.9.0 |
| pyarrow | 25.0.0 |
| xgboost | 3.4.0 |
| catboost | 1.2.10 |
| lightgbm | 4.7.0 |
| matplotlib | 3.11.1 |

## Reproducibility rules

1. Every Phase 3C run records: Python version, OS, CPU/GPU, git commit
   (`git rev-parse HEAD`), and the SHA256 of every input dataset (existing
   manifest `_sha256` convention).
2. Dataset SHA256s are stored in each dataset's manifest/card, never inferred
   after the fact.
3. Reports carry the line: *"Phase 3C is a new pinned benchmark environment; no
   byte-for-byte reproducibility claim against Phase 1/2 is made."*
4. When office access returns, compare environments **retrospectively only** —
   never a prerequisite for current execution.

## Verification

```text
ayush/Scripts/python.exe -c "import pandas, numpy, scipy, sklearn, pyarrow, xgboost, catboost, lightgbm"
```
succeeds with the versions above (2026-08-08).

## Smoke test (2026-08-08)

- `model_datasets/v3b/degradation_pairs.parquet` reads OK (252,183 × 70).
- `model_datasets/v3/wheel_engineering_state_v1.0.parquet` reads OK (271,350 × 69),
  contains `operational_exposure_id` (Stage C distance join key).

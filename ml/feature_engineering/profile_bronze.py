"""Generate data dictionaries and a quality report for every Bronze Parquet file."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRONZE_DIR = PROJECT_ROOT / "data" / "bronze"
DICTIONARY_DIR = PROJECT_ROOT / "docs" / "data_dictionary"
REPORT_PATH = PROJECT_ROOT / "reports" / "bronze_quality_report.md"


def display_value(value: object) -> object:
    """Convert pandas/numpy values to JSON-safe, compact display values."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return str(value)


def sample_values(series: pd.Series, limit: int = 5) -> str:
    values = series.dropna().drop_duplicates().head(limit).tolist()
    return json.dumps([display_value(value) for value in values], ensure_ascii=False)


def column_profile(name: str, series: pd.Series, row_count: int) -> dict[str, object]:
    null_count = int(series.isna().sum())
    distinct_count = int(series.nunique(dropna=True))
    profile: dict[str, object] = {
        "column_name": name,
        "data_type": str(series.dtype),
        "null_count": null_count,
        "null_percent": round((null_count / row_count * 100) if row_count else 0, 4),
        "distinct_count": distinct_count,
        "sample_values": sample_values(series),
        "is_candidate_key": bool(null_count == 0 and distinct_count == row_count),
        "minimum": "",
        "maximum": "",
        "mean": "",
        "comments": "",
    }

    non_null = series.dropna()
    if not non_null.empty and (is_numeric_dtype(series) or is_datetime64_any_dtype(series)):
        profile["minimum"] = display_value(non_null.min())
        profile["maximum"] = display_value(non_null.max())
        if is_numeric_dtype(series) and not is_bool_dtype(series):
            profile["mean"] = round(float(non_null.mean()), 6)
    return profile


def markdown_dictionary(dataset_name: str, columns: list[dict[str, object]]) -> str:
    lines = [
        f"# Data Dictionary: {dataset_name}",
        "",
        "| Column | Type | Null count | Null % | Distinct | Candidate key | Sample values | Min | Max | Mean | Comments |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for column in columns:
        sample = str(column["sample_values"]).replace("|", "\\|")
        lines.append(
            "| {column_name} | {data_type} | {null_count:,} | {null_percent:.4f} | "
            "{distinct_count:,} | {is_candidate_key} | {sample} | {minimum} | {maximum} | {mean} | {comments} |".format(
                sample=sample, **column
            )
        )
    return "\n".join(lines) + "\n"


def profile_dataset(parquet_path: Path) -> dict[str, object]:
    dataset_name = parquet_path.stem
    print(f"Profiling {parquet_path.name} ...", flush=True)
    frame = pd.read_parquet(parquet_path)
    row_count = len(frame)
    columns = [column_profile(name, frame[name], row_count) for name in frame.columns]
    dictionary = pd.DataFrame(columns)

    DICTIONARY_DIR.mkdir(parents=True, exist_ok=True)
    dictionary.to_csv(DICTIONARY_DIR / f"{dataset_name}.csv", index=False, encoding="utf-8")
    (DICTIONARY_DIR / f"{dataset_name}.md").write_text(
        markdown_dictionary(dataset_name, columns), encoding="utf-8"
    )

    candidate_key_columns = [
        column["column_name"] for column in columns if column["is_candidate_key"]
    ]
    null_cells = int(frame.isna().sum().sum())
    total_cells = row_count * len(frame.columns)
    return {
        "dataset": dataset_name,
        "rows": row_count,
        "columns": len(frame.columns),
        "duplicate_rows": int(frame.duplicated().sum()),
        "null_cells": null_cells,
        "null_percent": round((null_cells / total_cells * 100) if total_cells else 0, 4),
        "candidate_keys": ", ".join(candidate_key_columns) or "None",
        "high_null_columns": ", ".join(
            f"{column['column_name']} ({column['null_percent']:.1f}%)"
            for column in columns
            if column["null_percent"] >= 50
        )
        or "None",
    }


def quality_report(results: list[dict[str, object]]) -> str:
    lines = [
        "# Bronze Data Quality Report",
        "",
        "Generated from every `*.parquet` file in `data/bronze`. Candidate keys are "
        "columns with no nulls and one distinct value per row; they require domain validation.",
        "",
        "| Dataset | Rows | Columns | Duplicate rows | Null cells | Null % | Candidate keys | Columns >=50% null |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for result in results:
        lines.append(
            "| {dataset} | {rows:,} | {columns:,} | {duplicate_rows:,} | {null_cells:,} | "
            "{null_percent:.4f} | {candidate_keys} | {high_null_columns} |".format(**result)
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Duplicate-row counts are exact full-row comparisons.",
            "- Null percentages include all rows and columns in each dataset.",
            "- Numeric and datetime minimum/maximum values and numeric means are recorded in each data dictionary.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parquet_files = sorted(BRONZE_DIR.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet files found in {BRONZE_DIR}")

    results = [profile_dataset(parquet_path) for parquet_path in parquet_files]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(quality_report(results), encoding="utf-8")
    print(f"Created {len(results)} data dictionaries in {DICTIONARY_DIR.relative_to(PROJECT_ROOT)}")
    print(f"Created quality report: {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

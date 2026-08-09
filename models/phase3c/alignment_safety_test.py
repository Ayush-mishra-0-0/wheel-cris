"""Phase 3C - alignment safety regression test.

Reproduces the historical v3b failure mode (features and targets built from
different row orders) and proves the guard in degradation_eval detects it.

Pytest-compatible AND independently runnable: `python models/phase3c/alignment_safety_test.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pytest
except ModuleNotFoundError:  # pragma: no cover - standalone runner fallback
    class pytest:  # type: ignore
        @staticmethod
        def raises(exc_type, match=None):
            class _Ctx:
                def __init__(self, exc_type, match):
                    self.exc_type = exc_type
                    self.match = match

                def __enter__(self):
                    return self

                def __exit__(self, et, ev, tb):
                    if et is None:
                        raise AssertionError(f"expected {self.exc_type.__name__} (match={self.match!r})")
                    if not issubclass(et, self.exc_type):
                        return False
                    if self.match is not None and self.match not in str(ev):
                        raise AssertionError(f"exception message {str(ev)!r} does not contain {self.match!r}")
                    return True
            return _Ctx(exc_type, match)

from degradation_eval import (  # noqa: E402
    ROW_ID_COL,
    assert_row_alignment,
    add_targets_and_bases,
    chronological_split,
)


def _synthetic_pairs(n: int = 6, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ids = np.arange(1, n + 1)
    wheelsets = np.repeat([100, 101], n // 2)
    times = pd.to_datetime("2020-01-01") + pd.to_timedelta(
        rng.permutation(np.arange(1, n + 1)) * 30, unit="D")
    rows = {ROW_ID_COL: ids,
            "wheelset_equipment_id": wheelsets,
            "measurement_timestamp": times}
    for base, step in (("wsmDia", 1.5), ("wsmFlangeThickness", 0.4),
                       ("wsmRoot", 0.3), ("wsmWheelGauge", 0.5)):
        vals = 1092.0 - np.arange(n) * step if base == "wsmDia" else 30.0 - np.arange(n) * step * 0.1
        for s in ("1", "2"):
            rows[f"{base}{s}"] = vals
            rows[f"{base}{s}_quality"] = "OBSERVED_VALID"
            rows[f"next_{base}{s}"] = vals - 0.8
            rows[f"next_{base}{s}_quality"] = "OBSERVED_VALID"
    rows["interval_days"] = 30.0
    return pd.DataFrame(rows)


def test_guard_detects_positional_misalignment() -> None:
    """The historical bug: Y indexed with post-sort positions, X built post-sort.
    The row-id guard MUST detect it."""
    pairs = _synthetic_pairs()
    pairs = add_targets_and_bases(pairs)

    # simulate old script: sort by time, build X from sorted order, index Y with
    # sorted positions (positional misalignment)
    sorted_df = pairs.sort_values("measurement_timestamp").reset_index(drop=True)
    x_ids_sorted = sorted_df[ROW_ID_COL].to_numpy()
    order = np.arange(len(sorted_df))
    tr_idx = order < int(0.8 * len(sorted_df))
    # y is in PRE-sort (wheelset) order; indexing it with POST-sort positions is
    # exactly the historical bug. The target row ids for the train rows are the
    # pre-sort ids at those positions.
    y_ids_misaligned = pairs[ROW_ID_COL].to_numpy()[tr_idx]  # pre-sort ids
    x_ids_tr = x_ids_sorted[tr_idx]  # post-sort ids

    with pytest.raises(ValueError, match="MISALIGNMENT"):
        assert_row_alignment(x_ids_tr, y_ids_misaligned)


def test_aligned_path_passes_guard() -> None:
    pairs = _synthetic_pairs()
    sorted_df = pairs.sort_values("measurement_timestamp").reset_index(drop=True)
    assert_row_alignment(sorted_df[ROW_ID_COL].to_numpy(), sorted_df[ROW_ID_COL].to_numpy())
    assert_row_alignment(np.asarray([1, 2, 3]), np.asarray([1, 2, 3]))


def test_chronological_split_preserves_row_ids_and_cohort() -> None:
    pairs = _synthetic_pairs(n=20)
    a, tr_a, te_a = chronological_split(pairs.copy(), test_frac=0.2)
    b, tr_b, te_b = chronological_split(pairs.copy(), test_frac=0.2)
    assert a[ROW_ID_COL].tolist() == b[ROW_ID_COL].tolist()
    assert (te_a == te_b).all()
    # test rows must be strictly later than train rows
    te_times = a.loc[te_a, "measurement_timestamp"]
    tr_times = a.loc[tr_a, "measurement_timestamp"]
    assert (te_times.min() >= tr_times.max())


def test_add_targets_uses_observed_valid_rule() -> None:
    pairs = _synthetic_pairs(n=4)
    pairs.loc[0, "wsmDia2_quality"] = "IMPLAUSIBLE"
    out = add_targets_and_bases(pairs)
    # side 2 implausible -> base = side 1 only
    assert np.isclose(out.loc[0, "base_wsmDia"], pairs.loc[0, "wsmDia1"])


def _main() -> None:
    failures = 0
    for fn in [test_guard_detects_positional_misalignment,
               test_aligned_path_passes_guard,
               test_chronological_split_preserves_row_ids_and_cohort,
               test_add_targets_uses_observed_valid_rule]:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    _main()

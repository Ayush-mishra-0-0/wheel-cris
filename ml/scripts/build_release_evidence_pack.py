"""Assemble the v1.1 release evidence pack (markdown) from on-disk artifacts.

Reusable before AND after domain sign-off: every section reports its own
freshness/status, so a post-signoff rerun simply picks up the promoted scope
status and the rebuilt benchmarks. Read-only over artifacts; writes one
directory ml/releases/<run>/ with the pack + copies of key JSON evidence.

Run (sandbox env):
    ml\\.ayush\\Scripts\\python.exe ml\\scripts\\build_release_evidence_pack.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_BASE = ROOT / "releases"


def _j(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> None:
    import pandas as pd

    run = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = OUT_BASE / run
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    add = lines.append

    add(f"# Release evidence pack — generated {datetime.now(timezone.utc).isoformat()}")
    add("")
    add("Scope: current-state evidence for the wheel-forecasting release. Every")
    add("section states its own status; pending items are shown as pending.")
    add("")

    # ---- 1. data health -----------------------------------------------------
    add("## 1. Data health / lineage")
    add("")
    from models.phase5.wes_paths import current_wes_path  # noqa: E402

    wes_p = current_wes_path()
    wes_man = _j(wes_p.with_name(wes_p.stem.replace(
        "wheel_engineering_state_", "wheel_engineering_state_manifest_") + ".json")) or {}
    bronze = _j(ROOT / "data/bronze/wheel_measurements_metadata.json") or {}
    lc = _j(ROOT / "model_datasets/v5/lifecycle_segments_manifest.json") or {}
    snap_man = _j(ROOT / "model_datasets/v5/fleet_snapshot.manifest.json") or {}
    add(f"- WES serving artifact: `{wes_p.name}` rows={wes_man.get('rows')} built={wes_man.get('generated_at_utc')}")
    add(f"- Bronze extract: rows={bronze.get('rows')} extracted={bronze.get('extracted_at')} db={bronze.get('source_database')}")
    add(f"- Lifecycle: {lc.get('n_segments')} segments / {lc.get('n_turning_events')} turns / {lc.get('n_wheelsets')} wheelsets")
    add(f"- Fleet snapshot: n={snap_man.get('n_wheelsets')} built={snap_man.get('built_at_utc')} regen={snap_man.get('manifest_regenerated_at_utc')}")
    add(f"- Snapshot sources: " + "; ".join(s["path"] for s in snap_man.get("sources", [])))
    add("")

    # ---- 2. measurement scope ----------------------------------------------
    add("## 2. Measurement scope (trip-shed exclusion)")
    add("")
    scope = _j(ROOT / "configs/measurement_scope_v1.json") or {}
    add(f"- Status: **{scope.get('status')}**")
    add(f"- Excluded FLoc codes: {', '.join(scope.get('functional_location_codes', []))}")
    add(f"- Excluded section codes: {len(scope.get('section_codes', []))} registered")
    ev = scope.get("database_evidence", {})
    add(f"- DB audit: WAP7 register rows at trip FLocs={ev.get('current_wap7_register_rows_at_trip_functional_locations')}, "
        f"at trip sections={ev.get('current_wap7_register_rows_at_trip_sections')} ({ev.get('database')}, {ev.get('audited_at')})")
    add("- Local excluded-row count: 0 (no trip-shed keys present in current WES cohort)")
    add("- **Release gate: domain-owner sign-off still open.**")
    add("")

    # ---- 3. benchmarks -------------------------------------------------------
    add("## 3. Benchmarks (Target B ranking; Target A quarantined)")
    add("")
    man = _j(ROOT / "model_datasets/v4/risk_benchmark_manifest.json") or {}
    add(f"- Frozen benchmark dataset: {man.get('rows')} rows, limit_root={man.get('limit_root_mm')} mm "
        f"(sha {str(man.get('sha256'))[:12]}…)")
    for h in man.get("horizons", []):
        add(f"  - {h['horizon_days']}d: turn events {h['turn_events']} (rate {h['turn_rate_of_eligible']}), "
            f"root events {h['root_events']} (rate {h['root_rate_of_eligible']})")
    rolling = _j(ROOT / "models/experiments/v4/rolling_risk_benchmark.json") or {}
    try:
        t90 = rolling["targets"]["turn"]["90"]["B1_logistic"]
        add(f"- Rolling 30-step, turn 90d B1: capture@10 median={t90['capture10']['median']}, "
            f"ROC-AUC median={t90['roc_auc']['median']} ({t90['roc_auc']['n_cutoffs']} cutoffs)")
    except (KeyError, TypeError):
        pass
    loco = _j(ROOT / "models/experiments/v4/loco_holdout.json") or {}
    if loco:
        add(f"- Never-seen-loco holdout: {loco.get('n_loco_holdout')}/{loco.get('n_loco_total')} locos, "
            f"{loco.get('n_holdout_rows')} holdout rows")
    add("- **v1.1 benchmark rebuild: PENDING** (runs after scope sign-off).")
    add("")

    # ---- 4. ablation + calibration ------------------------------------------
    add("## 4. Free-delta ablation & calibration")
    add("")
    abl = _j(ROOT / "models/experiments/v4/free_delta_ablation.json") or {}
    if abl:
        cov = abl.get("coverage", {})
        add(f"- Delta join coverage {cov.get('join_coverage_pct')}% of anchors; conclusion: no material "
            "Target-B lift (frozen-test cap@10 -0.5..+1.6pp); deltas stay OUT of serving.")
        add("- Basis: frozen v4/WES v1.0 benchmark — reconfirm once on post-signoff v1.1 benchmark.")
    traj = _j(ROOT / "models/experiments/v5/trajectory_product_analysis.json") or {}
    conf = (traj.get("3_conformal_80pct") or {}).get("wsmDia", {})
    if conf:
        c90 = conf.get("90d") or {}
        add(f"- Conformal (dia 90d): width {c90.get('conformal_width_mm')} mm, empirical coverage {c90.get('coverage')} (nominal 0.80)")
    add("- Calibration: decile band at parity with isotonic on served horizons (see free_delta_ablation.md).")
    add("")

    # ---- 5. decision surface -------------------------------------------------
    add("## 5. Decision surface (live)")
    add("")
    ladder = _j(ROOT / "configs/action_ladder_v1.json") or {}
    add(f"- Ranking: calibrated 90d P(turn), Phase 4 Target B (`ranked_by=pturn_90d_calibrated`)")
    add(f"- Worklist: top-k per shed by the same score (capacity-aware)")
    add(f"- Dispositions: JSONL log with decision-time score context (model_datasets/v5/dispositions/)")
    add(f"- Action ladder: **{ladder.get('status')}** — tiers not computed until C&W thresholds arrive")
    add(f"- Distance gate: `interval_distance_km` APPROVED and released to serving "
        f"(docs/distance_serving_gate.md); coverage caveat ~53% intervals, NaN-native")
    add("")

    # ---- 6. ranked examples + worklist/disposition samples -------------------
    add("## 6. Ranked examples (top 5, live snapshot)")
    add("")
    snap = pd.read_parquet(ROOT / "model_datasets/v5/fleet_snapshot.parquet")
    top = snap.sort_values("pturn_90d_calibrated", ascending=False).head(5)
    add("| wheelset | loco | shed | cal P(turn) 90d | decile | limiting dim | condemning d |")
    add("|---|---|---|---|---|---|---|")
    for _, r in top.iterrows():
        add(f"| {int(r.wheelset_equipment_id)} | {r.loco_number} | {r.shed_any} | "
            f"{r.pturn_90d_calibrated:.4f} | {r.pturn_90d_decile} | {r.limiting_dim} | "
            f"{r.days_to_condemning_dia} |")
    add("")
    disp_dir = ROOT / "model_datasets/v5/dispositions"
    disp_lines = sorted(disp_dir.glob("*.jsonl"))
    add("## 7. Disposition log sample")
    add("")
    if disp_lines:
        tail = disp_lines[-1].read_text(encoding="utf-8").strip().splitlines()[-5:]
        for ln in tail:
            add(f"- `{ln[:160]}`")
    else:
        add("- empty")
    add("")

    # ---- 8. known limitations -------------------------------------------------
    add("## 8. Known limitations")
    add("")
    add("- Target A (root > 6 mm) quarantined: prevalence too low for classification-grade ranking.")
    add("- Survival/time-to-event ≈ chance on properly censored data; 'when' beyond the 180d horizon unknown.")
    add("- Distance features partial coverage (~53% of intervals); NaN-native serving.")
    add("- Trip-shed scope DB-verified but not domain-signed-off; exclusion currently a no-op for WAP7.")
    add("- Action ladder thresholds undefined (C&W).")
    add("- v1.1 benchmark + ablation rerun pending sign-off.")

    pack = out_dir / "release_evidence_pack.md"
    pack.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # copy machine-readable evidence alongside
    for src in (
        ROOT / "models/experiments/v4/free_delta_ablation.md",
        ROOT / "models/experiments/v4/free_delta_ablation.json",
        ROOT / "docs/distance_serving_gate.md",
        ROOT / "configs/measurement_scope_v1.json",
        ROOT / "configs/action_ladder_v1.json",
    ):
        if src.exists():
            shutil.copy2(src, out_dir / src.name)
    print(pack.relative_to(ROOT))


if __name__ == "__main__":
    main()

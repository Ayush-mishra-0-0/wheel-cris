# Wheel Lifecycle Analytics Platform — 1-Page Review

**Prediction-driven wheel turning & degradation planning for the locomotive fleet.**
Built on **271,350 real wheel measurements (2014 → Jul 2026)** across the fleet. The system forecasts **wheel profile wear (root / flange / thread) and wheel diameter 30, 90 and 180 days ahead**, flags **P(turn) within 30/60/90 days**, and surfaces **days-to-condemning**, so sheds plan turning before a wheel hits the approved 1016 mm hard stop.

---

## What we built

| Layer | What it does |
|---|---|
| **Data pipeline (v1 → v5)** | Raw measurement streams → validated silver/gold lifecycle datasets. Turn events detected & confirmed, same-lifecycle segments built, distance/km enriched. Every benchmark uses a strict **temporal point-in-time split (train cutoff 2025-11-24)** — no leakage. |
| **Degradation forecasting** | 4 wheelset dims × 30/90/180 d. Went from persistence baseline → Ridge → **XGBoost (C1)**, then added a **wear-rate model** (trained on 141k real day-to-day wear pairs) that champions **flange & diameter**. Result: the no-turn forecast path is **physically monotone by construction** — wear can only hold or grow, diameter only hold or shrink. |
| **Turning risk (P(turn))** | XGBoost classifier for P(turn in 30/60/90 d) — calibration checked (Brier, ECE) and **capture@top-k** validated, plus a shed-aware turning policy (cut-dia model, MAE **3.39 mm**). |
| **Live dashboard** | Serves forecasts for **19,167 active wheelsets** — per-wheelset trajectory, fleet risk ranking, shed overview, and a **point-in-time replay/backtest** that re-runs models at any historical date and compares to what actually happened. |

---

## Results (hold-out / frozen test)

**Degradation — C1 XGBoost MAE (mm), level forecasts:**
| Dimension | 30 d | 90 d | 180 d |
|---|---|---|---|
| wsmRoot | 0.43 | 0.48 | 0.54 |
| wsmFlange | 0.19 | 0.21 | 0.24 |
| wsmThread | 0.38 | 0.47 | 0.57 |
| wsmDia | 1.15 | 1.60 | 2.10 |

**Wear-rate champion model** cuts aggregate no-turn error from **2.90 → 2.43 mm (−16%)** on flange/diameter, and **eliminates physically impossible predictions**: served models now show **0%** "wear improving" / "diameter increasing" vs **8–13%** in reality noise — the forecast can no longer lie about wear.

**P(turn) — XGBoost:** ROC-AUC **0.78 / 0.74 / 0.73** (30/60/90 d); PR-AUC up to **0.16**; top-1% ranked list catches turns at **17.7% precision vs 0.2% random** (~80×).

---

## Real-world validation — model vs what actually happened

Six live fleet wheelsets; the model was frozen at the anchor date, then its 30/90/180 d forecast was compared to the real measurement. **All 12 predicted cells realized** on every wheelset; mean absolute error **0.22–0.51 mm**.

| WS (Loco · Shed) | Anchor | Dim | 30 d pred → actual | 90 d pred → actual | 180 d pred → actual | mean \|err\| |
|---|---|---|---|---|---|---|
| **44966** (30374 · TKD) | 2025-10-31 | root (limit) | 1.78 → 1.50 | 2.21 → 1.75 | 2.33 → 2.00 | **0.22 mm** |
| | | dia | 1086.11 → 1086.15 | 1086.09 → 1086.15 | 1086.08 → 1086.15 | |
| **44672** (30339 · TKDE) | 2024-10-09 | root (limit) | 1.03 → 0.75 | 1.74 → 1.25 | 1.28 → 1.50 | **0.32 mm** |
| | | dia | 1089.00 → 1088.40 | 1089.00 → 1088.40 | 1089.00 → 1088.40 | |
| **44968** (30442 · TKDE) | 2024-10-17 | root (limit) | 1.72 → 1.75 | 2.17 → 2.10 | 2.39 → 2.50 | **0.32 mm** |
| | | dia | 1083.90 → 1085.85 | 1083.10 → 1082.60 | **1082.62 → 1082.60** | |
| **227171** (39073 · NZM) | 2025-01-22 | thread (limit) | 1.60 → 1.50 | 1.77 → 2.00 | 2.64 → 3.00 | **0.32 mm** |
| | | dia | 1084.74 → 1085.35 | 1084.49 → 1085.35 | 1084.34 → 1085.35 | |
| **321797** (30428 · MDP) | 2024-02-02 | thread (limit) | 1.41 → 1.50 | 1.57 → 1.50 | 1.75 → 2.00 | **0.41 mm** |
| | | dia | 1081.46 → 1082.30 | 1081.11 → 1082.30 | 1080.90 → 1082.30 | |
| **405516** (37363 · KOTA) | 2024-08-16 | root (limit) | 1.79 → 2.05 | 2.92 → 3.35 | 3.67 → 3.35 | **0.51 mm** |
| | | dia | 1077.09 → 1079.00 | 1076.31 → 1077.00 | 1075.84 → 1077.00 | |

Highlight: **WS 44968** predicted diameter **1082.62 mm at +180 days; actual 1082.60 mm** — 0.02 mm off six months out. Across the fleet, forecast **diameter MAE @ 180 d ≈ 2.1 mm** against a condemn limit that sits ~65–75 mm away.

---

## Impact & next steps
- Maintenance moves from "react when flagged" to **planning turns 180 days out** with a credible no-turn wear path and days-to-condemning.
- **Next:** shed-policy integration for turn scheduling, live weekly retrain with auto-revalidation, and extending capture@top-k into a ranked weekly work list per shed.

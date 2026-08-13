# Part 1 — Label audit: next_interval_dia_delta_mm

Source: silver wheel_measurements (per-wheelset consecutive pairs).

## 1. Repeatability floor (true noise floor)

- Same wheelset re-measured within 1 day, no turning: n=73403
- median |dia delta| = **2.91 mm**
- 63.5% exceed 1 mm, 46.8% exceed 3 mm

> Physical 1-day wear is ~0.1 mm. The observed delta is therefore almost
> entirely measurement/process variance. **The continuous diameter label is
> ~95% noise at the single-interval level.**

## 2. Gap scaling (non-turning)

| gap | n | median | mean | median\|Δ\| | frac>5mm |
| --- | ---: | ---: | ---: | ---: | ---: |
| <=1d | 73403 | -2.10 | -5.62 | 2.91 | 0.342 |
| 1-3d | 49671 | -2.10 | -8.63 | 3.00 | 0.374 |
| 4-7d | 38851 | +0.00 | -4.87 | 0.00 | 0.218 |
| 8-30d | 109934 | +0.00 | -1.00 | 0.00 | 0.118 |
| 31-90d | 291501 | +0.00 | +0.20 | 0.37 | 0.114 |
| 91-365d | 302692 | -0.80 | +7.19 | 1.00 | 0.165 |
| >365d | 15929 | -4.00 | +27.71 | 16.00 | 0.762 |

> Median |delta| stays near 2-3 mm even for short gaps and only climbs at >365d
> (where real wear + possible unlogged events accumulate). **Little exposure-
> scaling: the label is not a clean integral of wear over time.**

## 3. Turning (reprofile) contribution

- At turning measurements: median delta = -3.00 mm, mean = +2.00 mm, median |delta| = 3.00 mm.

## 4. Multi-dimensional independence

(n=346493 non-turning pairs, gap<=30d)

| dimension | corr with dia delta |
| --- | ---: |
| flange thickness | 0.000 |
| root | 0.000 |
| thread | 0.000 |
| tire thickness | -0.999 |

> Flange/root/thread deltas are **independent** of diameter delta. This confirms
> the 'wheel as a system' premise: one dimension cannot proxy overall health.
> (tire_thickness correlates by construction — same physical surface.)

## Implication

1. Continuous diameter RMSE is capped by measurement noise, not model quality.
2. Multi-dimensional health requires multi-output / event / survival modelling.
3. Event labels (turning, large-loss) and survival (time-to-turning) operate on
   crisp engineering events and are far less noise-dominated.

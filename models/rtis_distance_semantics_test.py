"""RTIS RlkdTotalDistance semantics test — which interpretation fits the data?

Hypotheses to disambiguate:
  1. cumulative odometer  (one per loco, near-monotonic, huge magnitude)
  2. trip distance        (per-division leg, small magnitude, resets each trip)
  3. daily total          (per loco/day, sum across divisions is THE number)
  4. corrected total      (cumulative with periodic corrections / reloads)

The magnitude + monotonicity + reset + cross-division structure each vote.
"""
import pandas as pd
import numpy as np

m = pd.read_parquet(r'data/bronze/rtis_mileage.parquet')
m['RlkdReportDate'] = pd.to_datetime(m['RlkdReportDate'])
m['RlkdTotalDistance'] = pd.to_numeric(m['RlkdTotalDistance'], errors='coerce')

print('=== OVERALL MAGNITUDE (votes on cumulative vs trip/daily) ===')
s = m['RlkdTotalDistance']
print(f'rows: {len(m):,}  n_loco: {m["RlkdLocoNumber"].nunique():,}  n_days: {m["RlkdReportDate"].nunique()}')
print(f'min: {s.min():.2f}  p50: {s.median():.2f}  p90: {s.quantile(.9):.2f}  p99: {s.quantile(.99):.2f}  max: {s.max():.2f}')
print('frac < 100 km:', (s < 100).mean().round(4), ' frac > 50,000 km:', (s > 50000).mean().round(5))
print('cumulative odometer for WAP7 would be O(100k-1M km); trip/daily O(10-2000 km)')

# ---- Hypothesis test: per-loco daily max monotonicity ----
print('\n=== H1: CUMULATIVE ODOMETER — per-loco daily MAX over time ===')
daily_max = m.groupby(['RlkdLocoNumber', 'RlkdReportDate'])['RlkdTotalDistance'].max().reset_index()
daily_max = daily_max.sort_values(['RlkdLocoNumber', 'RlkdReportDate'])
loco_stats = []
for loco, g in daily_max.groupby('RlkdLocoNumber'):
    vals = g['RlkdTotalDistance'].to_numpy()
    if len(vals) < 5:
        continue
    diff = np.diff(vals)
    n_dec = int((diff < -0.05).sum())
    n_inc = int((diff > 0.05).sum())
    max_dec = float(-diff.min()) if len(diff) else 0.0
    max_inc = float(diff.max()) if len(diff) else 0.0
    loco_stats.append({'loco': loco, 'n_days': len(vals), 'n_dec': n_dec, 'n_inc': n_inc,
                       'max_dec': max_dec, 'max_inc': max_inc, 'min_v': float(vals.min()), 'max_v': float(vals.max())})
ls = pd.DataFrame(loco_stats)
print(f'locos with >=5 report-days: {len(ls):,}')
print(f'days where daily max DECREASED: total {int(ls["n_dec"].sum()):,} of {int(ls["n_days"].sum()):,} (~{ls["n_dec"].sum()/max(1,ls["n_days"].sum()):.1%})')
print(f'max single-day decrease seen: {ls["max_dec"].max():.1f} km')
print(f'locos that EVER decreased: {int((ls["n_dec"]>0).sum()):,} / {len(ls):,}')
print('--> cumulative odometer REQUIRES near-zero decreases; if many large decreases, REJECT H1')

# ---- Hypothesis test: daily SUM across divisions ----
print('\n=== H3: DAILY TOTAL — sum across divisions per loco/day ===')
day_sum = m.groupby(['RlkdLocoNumber', 'RlkdReportDate'])['RlkdTotalDistance'].sum().reset_index()
day_sum = day_sum.sort_values(['RlkdLocoNumber', 'RlkdReportDate'])
print('per loco-day SUM distribution:')
print(f'  p50: {day_sum["RlkdTotalDistance"].median():.1f}  p90: {day_sum["RlkdTotalDistance"].quantile(.9):.1f}  p99: {day_sum["RlkdTotalDistance"].quantile(.99):.1f}  max: {day_sum["RlkdTotalDistance"].max():.1f}')
# daily totals monotonicity
mono = []
for loco, g in day_sum.groupby('RlkdLocoNumber'):
    vals = g['RlkdTotalDistance'].to_numpy()
    if len(vals) < 5: continue
    d = np.diff(vals)
    mono.append({'loco': loco, 'n': len(vals), 'n_dec': int((d < -0.05).sum()), 'max_dec': float(-d.min()) if len(d) else 0.0})
ms = pd.DataFrame(mono)
print(f'daily-SUM decreased on {int(ms["n_dec"].sum()):,} of {int(ms["n"].sum()):,} day-steps (~{ms["n_dec"].sum()/max(1,ms["n"].sum()):.1%}); max decrease {ms["max_dec"].max():.1f} km')
print('--> if daily sums are ~monotonic, the values might be cumulative-by-day (but magnitudes are small, so unlikely)')

# ---- Hypothesis test: within-day division structure ----
print('\n=== division structure WITHIN a loco-day ===')
g = m.groupby(['RlkdLocoNumber', 'RlkdReportDate']).size()
n_rows = g.value_counts().sort_index()
print('rows per loco-day (top):', dict(n_rows.head(8)))
multi = (g > 1).mean()
print(f'locos-days with >1 division row: {multi:.1%}')

# ---- Hypothesis test: value EXACT repeats across days (reload/corrected) ----
print('\n=== exact-value repeats (corrected-total / reload signal) ===')
keys = m.groupby(['RlkdLocoNumber', 'RlkdReportDate', 'RlkdDivision', 'RlkdTotalDistance']).size()
print('exact duplicate business keys:', int((keys > 1).sum()), ' excess rows:', int((keys - 1).sum()))

# ---- Sample one loco's history for eyeball pattern ----
print('\n=== SAMPLE: loco 37100 daily max over first 15 report days ===')
lm = daily_max[daily_max['RlkdLocoNumber'] == 37100].head(15)
print(lm.to_string(index=False))

print('\n=== SAMPLE: loco 37100 full detail for 3 dates ===')
for d in ['2023-02-16', '2023-02-17', '2023-02-18']:
    sub = m[(m['RlkdLocoNumber'] == 37100) & (m['RlkdReportDate'] == d)]
    print(sub.to_string(index=False))

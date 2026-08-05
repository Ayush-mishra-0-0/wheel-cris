"""Deep disambiguation of RlkdTotalDistance using per-(loco,division) time series.

Key idea: if RlkdTotalDistance is a per-division SNAPSHOT of a cumulative odometer
(or a corrected total), then for a FIXED (loco, division) the value should move
smoothly/monotonically over time (mostly increase, occasional corrections). If it is
a trip/segment distance, the same (loco, division) series will look like a
sawtooth — jump up, reset near zero, jump again. The distribution of day-over-day
DELTAS within a fixed (loco,division) is the decisive test.

Also tests the 'division rows are independent additive segments' claim: within a
loco-day, do the per-division values look like pieces of one route (additive) or
independent odometer snapshots (each close to the same cumulative total)?
"""
import pandas as pd
import numpy as np

m = pd.read_parquet(r'data/bronze/rtis_mileage.parquet')
m['RlkdReportDate'] = pd.to_datetime(m['RlkdReportDate'])
m['RlkdTotalDistance'] = pd.to_numeric(m['RlkdTotalDistance'], errors='coerce')

# ---- A) Day-over-day deltas WITHIN a fixed (loco, division) ----
g = m.sort_values(['RlkdLocoNumber', 'RlkdDivision', 'RlkdReportDate'])
g = g.dropna(subset=['RlkdTotalDistance'])
deltas = g.groupby(['RlkdLocoNumber', 'RlkdDivision'])['RlkdTotalDistance'].diff().dropna()
deltas = deltas[deltas.abs() < 1e6]
print('=== A) day-over-day delta within fixed (loco, division) ===')
print(f'n deltas: {len(deltas):,}')
print(f'pct |delta|<1 km : {(deltas.abs()<1).mean():.3f}')
print(f'pct |delta|<10 km: {(deltas.abs()<10).mean():.3f}')
print(f'pct near-zero (|d|<0.1): {(deltas.abs()<0.1).mean():.3f}')
print(f'delta p25/p50/p75: {deltas.quantile(.25):.2f} / {deltas.median():.2f} / {deltas.quantile(.75):.2f}')
print(f'pct POSITIVE deltas: {(deltas>0).mean():.3f}   pct NEGATIVE: {(deltas<0).mean():.3f}')
print(f'delta p99 abs: {deltas.abs().quantile(.99):.1f}')
print()
print('INTERPRETATION:')
print(' - cumulative odometer/corrected: deltas are small incremental (few km/day), mostly positive, few negatives')
print(' - trip/segment distance: deltas are huge (+/- hundreds of km), both signs, look like resets')
print('   i.e. values jump to a new trip length each report, no smooth accumulation')

# ---- B) Sawtooth detection: count large drops (>50km) within a series ----
big_drop = (deltas < -50)
print(f'\n=== B) large drops (>50 km) in a (loco,division) series: {(big_drop.mean()):.3f} of all day-steps')
print('   (a cumulative counter should have ~0 of these; a trip counter has many)')

# ---- C) Within a loco-day: are division values similar magnitude or additive pieces? ----
print('\n=== C) within loco-day, per-division value structure ===')
grp = m.groupby(['RlkdLocoNumber', 'RlkdReportDate'])['RlkdTotalDistance']
size = grp.size()
multi = m[['RlkdLocoNumber', 'RlkdReportDate']].groupby(['RlkdLocoNumber','RlkdReportDate']).size()
multi_idx = multi[multi > 1].index
m2 = m.set_index(['RlkdLocoNumber', 'RlkdReportDate']).loc[multi_idx].reset_index()
day_grp = m2.groupby(['RlkdLocoNumber', 'RlkdReportDate'])['RlkdTotalDistance']
mx = day_grp.max(); mn = day_grp.min(); sm = day_grp.sum(); md = day_grp.median()
ratio = pd.DataFrame({'max': mx, 'min': mn, 'sum': sm, 'median': md, 'n': day_grp.size()})
ratio['max_over_median'] = ratio['max'] / ratio['median'].replace(0, np.nan)
print(f'within a loco-day with >1 division:')
print(f'  mean of (division max / division median): {ratio["max_over_median"].mean():.2f}')
print(f'  -> close to 1 = divisions report the SAME cumulative snapshot (redundant)')
print(f'  -> much >1   = divisions carry DIFFERENT segment values (additive pieces)')
print(f'  mean division value vs sum: median of (max/sum): {(ratio["max"]/ratio["sum"]).median():.3f}')

# ---- D) eyeball one (loco,division) series ----
print('\n=== D) eyeball: loco 30201, divisions with longest history ===')
sub = m[m['RlkdLocoNumber'] == '30201']
for div, g2 in sub.groupby('RlkdDivision'):
    if len(g2) > 10:
        g2 = g2.sort_values('RlkdReportDate')
        print(f'\ndivision {div} ({len(g2)} reports):')
        print(g2[['RlkdReportDate', 'RlkdTotalDistance']].head(12).to_string(index=False))
        break

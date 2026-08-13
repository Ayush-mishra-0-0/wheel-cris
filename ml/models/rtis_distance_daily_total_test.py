"""Decisive tests for: is the daily SUM (after dedup) the physical daily distance?

Focus: if each (loco, day, division) value is a SEGMENT of one day's travel, then:
  - deduped per-loco-day SUM should be realistic (~300-900 km for a WAP7)
  - consecutive daily sums should NOT be independent-looking; cumulative sum of
    daily sums should grow smoothly like an odometer
  - a loco's max-division value should usually be << the day total

Alternative: if each value is an independent TRIP/leg distance, then per-loco day
totals are meaningless and values should match known route-length buckets.

Also test the 'corrected/reset counter' hypothesis: series that accumulate, then
reset near 0, then accumulate again.
"""
import pandas as pd
import numpy as np

m = pd.read_parquet(r'data/bronze/rtis_mileage.parquet')
m['RlkdReportDate'] = pd.to_datetime(m['RlkdReportDate'])
m['RlkdTotalDistance'] = pd.to_numeric(m['RlkdTotalDistance'], errors='coerce')

# ---- dedupe exact business keys (reloads) ----
ded = m.drop_duplicates(['RlkdLocoNumber', 'RlkdReportDate', 'RlkdDivision', 'RlkdTotalDistance'])
print(f'after exact-key dedupe: {len(ded):,} rows (was {len(m):,})')

# ---- daily SUM per loco-day after dedupe ----
day_sum = ded.groupby(['RlkdLocoNumber', 'RlkdReportDate'])['RlkdTotalDistance'].sum().reset_index()
print('\n=== per-loco-day SUM after dedupe ===')
print(day_sum['RlkdTotalDistance'].describe().round(2).to_string())
print(f'median {day_sum["RlkdTotalDistance"].median():.0f} km/day  <- WAP7 typical daily travel ~400-900 km')
print(f'frac of days >1200 km: {(day_sum["RlkdTotalDistance"]>1200).mean():.3f}   >2000: {(day_sum["RlkdTotalDistance"]>2000).mean():.4f}')

# ---- is the cumulative sum of daily sums smooth (like an odometer)? ----
print('\n=== cumulative-sum smoothness for locos with long history ===')
loco = '30201'
sub = day_sum[day_sum['RlkdLocoNumber']==loco].sort_values('RlkdReportDate')
sub['cum'] = sub['RlkdTotalDistance'].cumsum()
print(loco, f'({len(sub)} report days)')
print(sub.head(10)[['RlkdReportDate','RlkdTotalDistance','cum']].to_string(index=False))
print('... last row cumulative km:', round(sub['cum'].iloc[-1],1), ' over', len(sub), 'report days')

# ---- within a day: how many divisions and are they additive ----
print('\n=== additive check: max-division value as fraction of day sum ===')
g = ded.groupby(['RlkdLocoNumber','RlkdReportDate'])['RlkdTotalDistance']
mx = g.max(); sm = g.sum(); n = g.size()
f = pd.DataFrame({'max':mx,'sum':sm,'n':n})
f['max_frac'] = (f['max']/f['sum']).replace([np.inf],1)
print('multi-division days: mean n per day:', n[n>1].mean().round(2))
print('max/frac: p50', f['max_frac'].median().round(3), ' p90', f['max_frac'].quantile(.9).round(3))
print('  -> if additive segments: no single division should dominate (max_frac << 1)')

# ---- trip-odometer RESET pattern: big drop then small accumulation ----
print('\n=== reset/accumulate pattern in a (loco,division) series ===')
g = ded.sort_values(['RlkdLocoNumber','RlkdDivision','RlkdReportDate'])
g = g.groupby(['RlkdLocoNumber','RlkdDivision'], sort=False).filter(lambda x: len(x) >= 15)
diff = g.groupby(['RlkdLocoNumber','RlkdDivision'])['RlkdTotalDistance'].diff()
g['delta'] = diff
print('locos-divisions with >=15 reports:', g['RlkdLocoNumber'].nunique()*1, 'series:', g[['RlkdLocoNumber','RlkdDivision']].drop_duplicates().shape[0])
for div, ser in g[g['RlkdLocoNumber']=='30201'].groupby('RlkdDivision'):
    if len(ser)>=15:
        print(f'\n30201 / {div}:')
        print(ser[['RlkdReportDate','RlkdTotalDistance','delta']].tail(15).to_string(index=False))
        break

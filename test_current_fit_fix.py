#!/usr/bin/env python
"""Test the current-fit filter on loco 39186."""
from development.dashboard.backend import service

# Test loco 39186
result = service.loco_summary("39186")
print(f"loco_summary('39186'):")
print(f"  n_wheelsets (current, ≤90d): {result['n_wheelsets']}")
print(f"  n_wheelsets_historical: {result['n_wheelsets_historical']}")
print(f"  recency_threshold_days: {result.get('recency_threshold_days')}")
print()
print(f"Current fits (≤90d):")
for w in result['wheelsets']:
    print(f"  WS {w['wheelset_equipment_id']}: {w['staleness_days']}d old")
print()
print(f"Historical wheelsets (>90d, currently hidden by default):")
for w in result['wheelsets_all']:
    if not w['is_current_fit']:
        print(f"  WS {w['wheelset_equipment_id']}: {w['staleness_days']}d old")

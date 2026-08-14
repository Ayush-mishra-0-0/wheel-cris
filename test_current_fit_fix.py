#!/usr/bin/env python
"""Test the current-fit filter on loco 39186.

Exploration result (2026-08-14): no equipment-assignment table exists, so
"is_recently_measured" is the honest proxy: latest measurement still stamped
this loco AND staleness <= recency_threshold_days. For 39186 that yields 6
wheelsets, matching the physical Co-Co axle count; the older rows (up to
1098d) are carried as history, not as current.
"""
from development.dashboard.backend import service

# Test loco 39186
result = service.loco_summary("39186")
print(f"loco_summary('39186'):")
print(f"  n_wheelsets (recent, <=90d): {result['n_wheelsets']}")
print(f"  n_wheelsets_historical: {result['n_wheelsets_historical']}")
print(f"  recency_threshold_days: {result.get('recency_threshold_days')}")
print()
print("Recent wheelsets (is_recently_measured=True):")
for w in result["wheelsets"]:
    print(f"  WS {w['wheelset_equipment_id']}: {w['staleness_days']}d old, "
          f"latest_loco_agrees={w['latest_loco_agrees']}, "
          f"is_current_fit(alias)={w['is_current_fit']}")
print()
print("Historical wheelsets (>90d, hidden by default):")
for w in result["wheelsets_all"]:
    if not w["is_recently_measured"]:
        print(f"  WS {w['wheelset_equipment_id']}: {w['staleness_days']}d old")

# Fleet risk staleness guard: default hides ancient wheelsets
r = service.fleet_risk(page_size=1, max_staleness_days=90)
print()
print(f"fleet_risk(max_staleness_days=90): total={r['total']} (echo {r['max_staleness_days']})")
r_all = service.fleet_risk(page_size=1, max_staleness_days=None)
print(f"fleet_risk(max_staleness_days=None): total={r_all['total']} (all rows)")

#!/usr/bin/env python
"""Verify API response structure."""
import json
from development.dashboard.backend import service

# Test the API response structure
result = service.loco_summary("39186")

print("=== API Response Structure ===")
print(f"n_wheelsets: {result['n_wheelsets']}")
print(f"n_wheelsets_current: {result.get('n_wheelsets_current')}")
print(f"n_wheelsets_historical: {result.get('n_wheelsets_historical')}")
print(f"recency_threshold_days: {result.get('recency_threshold_days')}")
print()

# Show a sample row structure
if result['wheelsets']:
    w = result['wheelsets'][0]
    print("Sample wheelset row:")
    print(f"  wheelset_equipment_id: {w['wheelset_equipment_id']}")
    print(f"  staleness_days: {w.get('staleness_days')}")
    print(f"  is_current_fit: {w.get('is_current_fit')}")
    print()

# Verify the counts make sense
print("=== Verification ===")
print(f"wheelsets list length: {len(result['wheelsets'])}")
print(f"wheelsets_all list length: {len(result.get('wheelsets_all', []))}")
all_recent = sum(1 for w in result.get('wheelsets_all', []) if w.get('is_current_fit', False))
print(f"Count of is_current_fit=True in wheelsets_all: {all_recent}")
print(f"Expected (should match wheelsets): {result['n_wheelsets']}")

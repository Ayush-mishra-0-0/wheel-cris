# Inspection Interval Contract v1.0.0

One consecutive inspection pair for the same equipment/wheelset candidate,
derived only from Business Truth `v1.0` Gold-B timeline records.

V1 eligibility: same equipment/wheelset candidate ID, same assigned locomotive
at both endpoints, strictly positive interval duration, and Gold-B endpoints.
All failures are retained in the exclusion dataset with a reason.

The contract includes endpoint measurement IDs/times, equipment and locomotive
ID, elapsed days, raw geometry at both endpoints and raw changes, turning
indicators, interval tier, exclusion reason and Business Truth lineage.

RTIS, maintenance, weather and track enrichments are deferred to later interval
contract versions; v1.0 establishes only trusted temporal boundaries.

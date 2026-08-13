"""Minimal geodesic + along-line projection utilities (pure numpy).

No geopandas/shapely required. Latitude/longitude are treated as degrees;
distances use the haversine formula. For point-to-polyline projection we work
in a local equirectangular plane (x = lon * cos(lat0) * R, y = lat * R) so the
perpendicular foot can be computed with simple vector maths; the along-track
distance is accumulated with haversine segment lengths.
"""
from __future__ import annotations

import numpy as np

EARTH_R = 6371.0


def _rad(v):
    return np.radians(np.asarray(v, dtype=float))


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Haversine great-circle distance in km (scalar or broadcast arrays)."""
    lat1, lon1, lat2, lon2 = _rad(lat1), _rad(lon1), _rad(lat2), _rad(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_R * np.arcsin(np.sqrt(a))


def _segment_lengths_km(coords: np.ndarray) -> np.ndarray:
    """coords: (n,2) array of [lat, lon]. Returns length of each segment in km."""
    d = haversine_km(coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1])
    return np.asarray(d, dtype=float)


def project_point_to_polyline(lat: float, lon: float, coords: np.ndarray):
    """Perpendicular projection of (lat, lon) onto a polyline.

    Args:
      lat, lon: point (degrees).
      coords: (n, 2) array of [lat, lon] vertices (n >= 2).

    Returns:
      (dist_km, along_km): distance to the closest point on the polyline and
      the cumulative haversine distance along the polyline to that point.
    """
    coords = np.asarray(coords, dtype=float)
    n = len(coords)
    if n < 2:
        raise ValueError("polyline needs >= 2 vertices")
    seg_len = _segment_lengths_km(coords)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    total = cum[-1]

    # local equirectangular plane centred on the mid-latitude of the edge
    lat0 = np.deg2rad(np.mean(coords[:, 0]))
    km_per_deg_lat = np.pi * EARTH_R / 180.0
    km_per_deg_lon = km_per_deg_lat * np.cos(lat0)

    pts = np.column_stack([
        coords[:, 1] * km_per_deg_lon,
        coords[:, 0] * km_per_deg_lat,
    ])
    p = np.array([lon * km_per_deg_lon, lat * km_per_deg_lat])

    a = pts[:-1]
    b = pts[1:]
    ab = b - a
    ab2 = np.einsum("ij,ij->i", ab, ab)
    ab2[ab2 == 0] = 1e-12
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / ab2, 0.0, 1.0)
    proj = a + t[:, None] * ab
    dplane = np.sqrt(np.einsum("ij,ij->i", proj - p, proj - p))

    # convert plane distance back to km (approx: divide by km-per-deg along the
    # local frame; a good approximation for short offsets)
    dist_km = float(dplane.min()) if len(dplane) else float("inf")
    i = int(np.argmin(dplane))
    along_km = float(cum[i] + t[i] * seg_len[i])
    return dist_km, along_km


def build_grid_index(edges: list[np.ndarray], cell_deg: float):
    """Bucket edges into a lat/lon grid.

    edges: list of (n,2) [lat, lon] arrays.
    Returns (grid, keys) where grid maps cell key (i,j) -> list of edge indices.
    """
    grid: dict[tuple[int, int], list[int]] = {}
    for eidx, coords in enumerate(edges):
        lat_min, lat_max = float(coords[:, 0].min()), float(coords[:, 0].max())
        lon_min, lon_max = float(coords[:, 1].min()), float(coords[:, 1].max())
        i0, i1 = int(np.floor(lat_min / cell_deg)), int(np.floor(lat_max / cell_deg))
        j0, j1 = int(np.floor(lon_min / cell_deg)), int(np.floor(lon_max / cell_deg))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                grid.setdefault((i, j), []).append(eidx)
    return grid


def candidate_edges(lat: float, lon: float, grid, cell_deg: float) -> list[int]:
    """Edge indices whose bbox overlaps the 3x3 cell neighbourhood of (lat, lon)."""
    i = int(np.floor(lat / cell_deg))
    j = int(np.floor(lon / cell_deg))
    out: list[int] = []
    seen: set[int] = set()
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for eidx in grid.get((i + di, j + dj), ()):
                if eidx not in seen:
                    seen.add(eidx)
                    out.append(eidx)
    return out

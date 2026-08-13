"""HTTP helper for fetching public datasets behind the corporate MITM proxy.

This environment has no direct DNS: every request MUST traverse the proxy in
HTTP_PROXY/HTTPS_PROXY (default http://172.16.1.61:8080). The proxy terminates
TLS with a corporate root CA that Windows trusts but Python's certifi bundle
does not, so requests first try certificate verification and fall back to
verify=False on an SSLCertVerificationError. All fetches are read-only public
data; the fallback is deliberately explicit and logged as a warning.

Exports:
  get(url, timeout) -> requests.Response
  download(url, dest, timeout) -> Path   (streams to disk, idempotent)
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
PROXIES = {"http": _PROXY, "https": _PROXY} if _PROXY else None


def get(url: str, timeout: int = 180) -> requests.Response:
    """GET with cert-verify-first-then-fallback behind the proxy."""
    headers = {"User-Agent": "Mozilla/5.0 (distance-recovery pipeline)"}
    try:
        return requests.get(url, timeout=timeout, proxies=PROXIES, headers=headers)
    except requests.exceptions.SSLError:
        warnings.warn(
            f"TLS verification failed for {url}; retrying with verify=False "
            "(corporate MITM proxy CA not in certifi bundle). Read-only public data.",
            stacklevel=2,
        )
        return requests.get(url, timeout=timeout, proxies=PROXIES, headers=headers, verify=False)


def download(url: str, dest: Path, timeout: int = 600) -> Path:
    """Download url to dest (streamed). Creates parent dirs. Returns dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    r = get(url, timeout=timeout)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
    return dest

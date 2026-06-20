"""Shared Apify actor runner with clear, actionable error handling.

Every adapter (reddit/linkedin/x) starts an actor, polls it, and reads its dataset. This centralizes
that — and, importantly, turns the failure modes into messages a human can act on instead of a raw
traceback or a silent empty result:

  • Out of Apify credit / monthly usage limit  → clear "top up or use the free Reddit path" message,
    non-zero exit (so the run fails loudly and a scheduled run's output shows why).
  • Actor run FAILED / ABORTED / TIMED-OUT      → surface the run's status message; return [].
  • Didn't finish within the poll window         → "slow cold start, try again"; return [].
  • Succeeded but 0 items                         → note it (likely topics/subreddits too narrow).

Usage:
    from lib.apify import run_actor
    items = run_actor(token, "trudax~reddit-scraper-lite", actor_input, label="reddit")
"""
from __future__ import annotations

import sys
import time

_BASE = "https://api.apify.com/v2"


def _credit_hint() -> str:
    return ("Your Apify account is out of credit / over its usage limit for this period. "
            "Check https://console.apify.com/billing — top up, or wait for the monthly reset. "
            "(Reddit can also run free: set REDDIT_CLIENT_ID/SECRET and use --provider official.)")


def _looks_like_usage_limit(*texts) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(w in blob for w in ("usage limit", "monthly-usage", "usage-hard-limit",
                                   "out of credit", "insufficient", "payment", "quota",
                                   "limit-exceeded", "max-monthly"))


class ApifyCreditError(SystemExit):
    """Raised (exit code 4) when the failure is clearly an Apify credit/usage-limit problem."""
    def __init__(self, msg):
        print(f"[apify] ERROR: {msg}", file=sys.stderr)
        super().__init__(4)


def run_actor(token, actor, actor_input, *, poll=90, interval=5, label="apify"):
    import requests

    # --- start the run ---
    try:
        resp = requests.post(f"{_BASE}/acts/{actor}/runs",
                             params={"token": token}, json=actor_input, timeout=60)
    except requests.RequestException as e:
        print(f"[{label}] ERROR: couldn't reach Apify ({e}). Check your connection.", file=sys.stderr)
        raise SystemExit(1)

    if not resp.ok:
        try:
            err = resp.json().get("error", {}) or {}
        except ValueError:
            err = {}
        etype, emsg = err.get("type", ""), err.get("message", "")
        if resp.status_code in (402, 403) or _looks_like_usage_limit(etype, emsg):
            raise ApifyCreditError(f"{_credit_hint()} (Apify: {emsg or etype or resp.status_code})")
        print(f"[{label}] ERROR starting actor {actor}: HTTP {resp.status_code} — "
              f"{emsg or etype or resp.text[:200]}", file=sys.stderr)
        raise SystemExit(1)

    run_id = resp.json()["data"]["id"]

    # --- poll to completion ---
    st = None
    for _ in range(poll):
        time.sleep(interval)
        try:
            st = requests.get(f"{_BASE}/actor-runs/{run_id}",
                              params={"token": token}, timeout=30).json()["data"]
        except (requests.RequestException, KeyError, ValueError):
            continue
        if st.get("status") in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    status = (st or {}).get("status")
    msg = (st or {}).get("statusMessage", "") or ""

    if status != "SUCCEEDED":
        if status in (None, "RUNNING", "READY"):
            print(f"[{label}] WARNING: actor didn't finish within {poll * interval}s — likely a slow "
                  f"cold start. No results this run; try again.", file=sys.stderr)
            return []
        if _looks_like_usage_limit(status, msg):
            raise ApifyCreditError(f"{_credit_hint()} (Apify run {status}: {msg})")
        print(f"[{label}] WARNING: actor run {status}: {msg or '(no message)'} — no results this run.",
              file=sys.stderr)
        return []

    # --- fetch dataset ---
    try:
        items = requests.get(f"{_BASE}/datasets/{st['defaultDatasetId']}/items",
                             params={"token": token, "format": "json"}, timeout=60).json()
    except (requests.RequestException, ValueError) as e:
        print(f"[{label}] WARNING: run succeeded but fetching results failed ({e}).", file=sys.stderr)
        return []
    if not items:
        print(f"[{label}] note: actor returned 0 items — try broader topics/subreddits, a longer "
              f"--days window, or check the actor.", file=sys.stderr)
    return items

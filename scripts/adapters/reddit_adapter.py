#!/usr/bin/env python3
"""Reddit adapter → OpportunitySignal[].

Default: Apify Reddit actor (trudax/reddit-scraper-lite) — no login, no cookies, uses the SAME
APIFY_API_TOKEN the user already provides for LinkedIn. One credential runs the whole skill.

Optional (power users): the free official OAuth API. Set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET
(a "script" app at https://www.reddit.com/prefs/apps) and pass --provider official. Free and very
durable, but an extra setup step — so it's opt-in, not required. See references/DECISIONS.md for
why we don't require it and why unauthenticated public JSON isn't a viable path.

Reads subreddits/topics from the config; emits normalized signals to a JSON file.

Usage:
    python3 reddit_adapter.py --config config.json -o raw_reddit.json            # Apify (default)
    python3 reddit_adapter.py --config config.json --provider official -o out.json
    python3 reddit_adapter.py --subreddits saas,startups --topics "voice ai" -o out.json

Dependency: requests  (pip install requests)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.opportunity_signal import make_signal  # noqa: E402
from lib.apify import run_actor  # noqa: E402

USER_AGENT = "delta-engage/1.0 (engagement-opportunity-finder)"
OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
# Apify Reddit actor — no login required, but the LITE actor returns NO upvote/comment counts.
# Override with DELTA_ENGAGE_REDDIT_ACTOR only if you've *rented* a paid actor that returns counts
# (e.g. trudax~reddit-scraper 403s "actor-is-not-rented" on a normal BYOK plan — it is NOT a free
# swap). The real free path to full engagement signal is --provider official (a free Reddit app).
APIFY_REDDIT_ACTOR = os.environ.get("DELTA_ENGAGE_REDDIT_ACTOR", "trudax~reddit-scraper-lite")


def _load_config(path):
    if not path:
        return {}
    with open(path) as f:
        return json.load(f)


# --- default path: Apify (no login, single token) ------------------------------------------------

def _t_from_days(days):
    """Reddit search `t` (time) param from a day window — don't over-restrict relevance search."""
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    if days <= 366:
        return "year"
    return "all"


def _apify_urls(subreddits, topics, days, max_urls):
    """Build relevance-SEARCH URLs for the Apify path. Verified live: the lite actor's `searches`
    param returns irrelevant junk, but it DOES scrape per-sub `/search/?q=…&restrict_sr=1` pages
    correctly. So we search the pain (topics) within each subreddit — never mix `/top/` feeds with
    a broken global search. Returns (urls, dropped_note)."""
    from urllib.parse import quote
    t = _t_from_days(days)
    subs = [s.strip().lstrip("r/").strip("/") for s in subreddits if s.strip()]
    qs = [q.strip() for q in topics if q.strip()]
    urls = []
    if subs and qs:                       # the good case: each pain phrase, searched in each sub
        for s in subs:
            for q in qs:
                urls.append(f"https://www.reddit.com/r/{s}/search/?q={quote(q)}"
                            f"&restrict_sr=1&sort=relevance&t={t}")
    elif qs:                              # topics, no subs → site-wide relevance search
        urls = [f"https://www.reddit.com/search/?q={quote(q)}&sort=relevance&t={t}" for q in qs]
    elif subs:                           # subs, no topics → browse community top feeds
        urls = [f"https://www.reddit.com/r/{s}/top/?t={t}" for s in subs]
    dropped = ""
    if len(urls) > max_urls:             # NO SILENT CAPS — say what was dropped
        dropped = (f"[reddit] {len(urls)} sub×topic searches requested; running {max_urls} this run "
                   f"(raise with --max-queries). Skipped {len(urls) - max_urls}.")
        urls = urls[:max_urls]
    return urls, dropped


def search_apify(token, subreddits, topics, limit_per, time_filter, days, max_urls=12):
    urls, dropped = _apify_urls(subreddits, topics, days, max_urls)
    if dropped:
        print(dropped, file=sys.stderr)
    if not urls:
        print("[reddit] nothing to search (no subreddits or topics).", file=sys.stderr)
        return []
    # Minimal input — verified live that the lite actor scrapes /search/ URLs with just these
    # fields; adding the actor's own search* flags made it return nothing.
    actor_input = {
        "startUrls": [{"url": u} for u in urls],
        "maxItems": limit_per * len(urls),
        "skipComments": True,
    }
    # The lite actor is intermittent on Reddit search (Reddit rate-limits the scrape) — retry once
    # on empty before giving up.
    items = run_actor(token, APIFY_REDDIT_ACTOR, actor_input, label="reddit")
    if not items:
        print("[reddit] empty result — retrying once (the lite actor is flaky on Reddit search)…",
              file=sys.stderr)
        items = run_actor(token, APIFY_REDDIT_ACTOR, actor_input, label="reddit")

    cutoff = time.time() - days * 86400
    out = []
    for d in items:
        # the lite actor returns posts and (skipped) comments; keep posts only
        if d.get("dataType") and d.get("dataType") != "post":
            continue
        created = d.get("createdAt") or d.get("created") or d.get("created_utc") or ""
        # best-effort recency filter when we have an epoch
        try:
            if isinstance(d.get("created_utc"), (int, float)) and d["created_utc"] < cutoff:
                continue
        except (TypeError, KeyError):
            pass
        title = d.get("title", "")
        body = d.get("body", d.get("text", d.get("selftext", "")))
        out.append(make_signal(
            platform="reddit",
            post_url=d.get("url", "") or d.get("link", "") or d.get("permalink", ""),
            author_handle=d.get("username", "") or d.get("author", ""),
            author_url=d.get("userUrl", ""),
            text=(title + "\n\n" + (body or "")).strip(),
            title=title,
            timestamp=str(created),
            score=d.get("upVotes", d.get("score", d.get("numberOfVotes", 0))) or 0,
            num_comments=d.get("numberOfComments", d.get("num_comments", 0)) or 0,
            topic_tags=[d.get("communityName", d.get("subreddit", "")).replace("r/", "")],
            source_provider="reddit_apify",
            raw_id=d.get("id", d.get("url", "")),
        ))
    if not out:
        print("[reddit] returned nothing this run — the lite actor is intermittently rate-limited "
              "by Reddit (it already retried once). Try again, broaden your topics, or widen "
              "--days.", file=sys.stderr)
    elif not any(s["score"] or s["num_comments"] for s in out):
        print("[reddit] note: this actor returns no upvote/comment counts — Reddit ranks on "
              "recency + your fit score this run.", file=sys.stderr)
    return out


# --- optional path: official OAuth (free, durable, extra setup) -----------------------------------

def get_oauth_token(client_id, client_secret):
    import requests
    resp = requests.post(
        OAUTH_TOKEN_URL, auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": USER_AGENT}, timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def search_official(token, subreddits, topics, limit_per, time_filter, days):
    import requests
    now = time.time()
    cutoff = now - days * 86400
    headers = {"Authorization": f"bearer {token}", "User-Agent": USER_AGENT}
    seen = {}

    def ingest(children):
        for c in children:
            d = c.get("data", {})
            if d.get("created_utc", 0) < cutoff:
                continue
            pid = d.get("id")
            if not pid or pid in seen:
                continue
            permalink = d.get("permalink", "")
            seen[pid] = make_signal(
                platform="reddit",
                post_url="https://www.reddit.com" + permalink if permalink else d.get("url", ""),
                author_handle=d.get("author", ""),
                author_url=f"https://www.reddit.com/user/{d.get('author','')}",
                text=(d.get("title", "") + "\n\n" + d.get("selftext", "")).strip(),
                title=d.get("title", ""),
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("created_utc", 0))),
                score=d.get("score", 0),
                num_comments=d.get("num_comments", 0),
                topic_tags=[d.get("subreddit", "")],
                source_provider="reddit_official",
                raw_id=pid,
            )

    for sub in subreddits:
        sub = sub.strip().lstrip("r/").strip("/")
        if not sub:
            continue
        try:
            r = requests.get(f"https://oauth.reddit.com/r/{sub}/top", headers=headers,
                             params={"t": time_filter, "limit": limit_per}, timeout=30)
            r.raise_for_status()
            ingest(r.json().get("data", {}).get("children", []))
        except Exception as e:  # noqa: BLE001
            print(f"[reddit] warn: top fetch failed for r/{sub}: {e}", file=sys.stderr)
        for topic in topics:
            try:
                r = requests.get(f"https://oauth.reddit.com/r/{sub}/search", headers=headers,
                                 params={"q": topic, "restrict_sr": 1, "sort": "relevance",
                                         "t": time_filter, "limit": limit_per}, timeout=30)
                r.raise_for_status()
                ingest(r.json().get("data", {}).get("children", []))
            except Exception as e:  # noqa: BLE001
                print(f"[reddit] warn: search '{topic}' in r/{sub} failed: {e}", file=sys.stderr)
            time.sleep(0.5)
    return list(seen.values())


def main():
    ap = argparse.ArgumentParser(description="Reddit adapter → OpportunitySignal[]")
    ap.add_argument("--config", help="path to config.json")
    ap.add_argument("--subreddits", help="comma-separated (overrides config seed_accounts)")
    ap.add_argument("--topics", help="comma-separated (overrides config topics)")
    ap.add_argument("--provider", choices=["apify", "official"], default=None,
                    help="default: apify if APIFY_API_TOKEN set; 'official' needs Reddit creds")
    ap.add_argument("--days", type=int, default=10, help="only posts from the last N days")
    ap.add_argument("--time-filter", default="week", help="reddit window: day/week/month")
    ap.add_argument("--limit-per", type=int, default=25, help="max posts per subreddit/query")
    ap.add_argument("--max-queries", type=int, default=12,
                    help="max sub×topic search URLs per run (caps Apify spend; logged if hit)")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    cfg = _load_config(args.config)
    subreddits = (args.subreddits.split(",") if args.subreddits
                  else cfg.get("seed_accounts", {}).get("reddit_subreddits", []))
    topics = args.topics.split(",") if args.topics else cfg.get("topics", [])
    if not subreddits and not topics:
        print("error: no subreddits or topics (provide --subreddits/--topics or a config)",
              file=sys.stderr)
        sys.exit(2)

    # provider resolution: explicit flag > config.providers.reddit > default(apify)
    provider = args.provider or cfg.get("providers", {}).get("reddit", "apify")

    if provider == "official":
        cid, csecret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
        if not (cid and csecret):
            print("error: --provider official needs REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET "
                  "(create a 'script' app at https://www.reddit.com/prefs/apps). Or use the "
                  "default Apify provider with APIFY_API_TOKEN.", file=sys.stderr)
            sys.exit(1)
        token = get_oauth_token(cid, csecret)
        signals = search_official(token, subreddits, topics, args.limit_per,
                                  args.time_filter, args.days)
    else:
        token = os.environ.get("APIFY_API_TOKEN")
        if not token:
            print("error: set APIFY_API_TOKEN (the single token this skill uses). Alternatively, "
                  "use the free official Reddit API with --provider official + Reddit creds.",
                  file=sys.stderr)
            sys.exit(1)
        signals = search_apify(token, subreddits, topics, args.limit_per,
                               args.time_filter, args.days, args.max_queries)

    with open(args.output, "w") as f:
        json.dump(signals, f, indent=2)
    print(f"[reddit] wrote {len(signals)} signals via {provider} → {args.output}")


if __name__ == "__main__":
    main()

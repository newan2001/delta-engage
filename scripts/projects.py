#!/usr/bin/env python3
"""projects.py — multi-project registry & paths for delta-engage.

delta-engage runs one engagement *profile* per project (its own positioning, ICP, topics,
watchlist, delivery, run history). This script is the deterministic plumbing for managing many of
them: it owns slugs, per-project paths, the registry, and one-time migration from the old
single-config layout. Judgment (what the ICP *is*) stays with the model; this just files it.

Layout (override the base with DELTA_ENGAGE_CONFIG_DIR):
    ~/.config/delta-engage/
    ├── registry.json                  # index of projects (this script maintains it)
    └── projects/<slug>/
        ├── config.json                # that project's profile (the schema in assets/)
        └── runs/                       # per-project working artifacts (raw_*, signals, digest…)

Per-project run dirs are what make parallel sessions safe — two projects running at once never
clobber each other's raw_reddit.json.

Commands:
    migrate                 one-time: move a legacy ~/.config/delta-engage/config.json → default/
    ensure <slug>           create projects/<slug>/ (+ runs/); print its paths as JSON
    resolve <slug>          print {config, runs} paths for an existing project (error if missing)
    register <slug> ...     upsert a registry entry (--name --positioning --cadence --delivery)
    touch <slug>            stamp last_run = today
    list                    print the registry (JSON) — slug, name, cadence, delivery, last_run, paths
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

BASE = os.environ.get("DELTA_ENGAGE_CONFIG_DIR",
                      os.path.expanduser("~/.config/delta-engage"))
PROJECTS = os.path.join(BASE, "projects")
REGISTRY = os.path.join(BASE, "registry.json")


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "project"


def _paths(slug):
    pdir = os.path.join(PROJECTS, slug)
    return {"slug": slug, "dir": pdir,
            "config": os.path.join(pdir, "config.json"),
            "runs": os.path.join(pdir, "runs")}


def _load_registry():
    try:
        with open(REGISTRY) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"projects": []}


def _save_registry(reg):
    os.makedirs(BASE, exist_ok=True)
    with open(REGISTRY, "w") as f:
        json.dump(reg, f, indent=2)


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def ensure(slug):
    slug = slugify(slug)
    p = _paths(slug)
    os.makedirs(p["runs"], exist_ok=True)
    return p


def register(slug, **fields):
    slug = slugify(slug)
    reg = _load_registry()
    entry = next((e for e in reg["projects"] if e["slug"] == slug), None)
    if entry is None:
        entry = {"slug": slug}
        reg["projects"].append(entry)
    for k, v in fields.items():
        if v is not None:
            entry[k] = v
    _save_registry(reg)
    return entry


def cmd_migrate():
    legacy = os.path.join(BASE, "config.json")
    out = {"migrated": False}
    if os.path.exists(legacy) and not os.path.exists(_paths("default")["config"]):
        p = ensure("default")
        os.rename(legacy, p["config"])
        try:
            cfg = json.load(open(p["config"]))
        except (ValueError, FileNotFoundError):
            cfg = {}
        register("default", name=cfg.get("name", "Default"),
                 positioning=cfg.get("positioning", ""),
                 cadence=cfg.get("cadence", ""),
                 delivery=(cfg.get("delivery", {}) or {}).get("channel", "in_app"))
        out = {"migrated": True, "config": p["config"],
               "action_required": ("A pre-existing scheduled task that runs a BARE '/delta-engage' "
                                   "is now ambiguous (a bare call with >1 project asks which to run, "
                                   "which a headless run can't answer). Repoint it to "
                                   "'/delta-engage default' (or rename it delta-engage-default).")}
    return out


def cmd_list():
    reg = _load_registry()
    # backfill from disk in case a project dir exists without a registry entry
    known = {e["slug"] for e in reg["projects"]}
    if os.path.isdir(PROJECTS):
        for slug in sorted(os.listdir(PROJECTS)):
            if slug not in known and os.path.exists(_paths(slug)["config"]):
                reg["projects"].append({"slug": slug})
    for e in reg["projects"]:
        e.update({k: v for k, v in _paths(e["slug"]).items() if k in ("config", "runs")})
    return reg


def main():
    ap = argparse.ArgumentParser(description="delta-engage multi-project registry/paths")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("list")
    for c in ("ensure", "resolve", "touch"):
        sp = sub.add_parser(c)
        sp.add_argument("slug")
    rp = sub.add_parser("register")
    rp.add_argument("slug")
    rp.add_argument("--name")
    rp.add_argument("--positioning")
    rp.add_argument("--cadence")
    rp.add_argument("--delivery")

    args = ap.parse_args()
    if args.cmd == "migrate":
        print(json.dumps(cmd_migrate(), indent=2))
    elif args.cmd == "list":
        print(json.dumps(cmd_list(), indent=2))
    elif args.cmd == "ensure":
        print(json.dumps(ensure(args.slug), indent=2))
    elif args.cmd == "resolve":
        p = _paths(slugify(args.slug))
        if not os.path.exists(p["config"]):
            print(f"error: no project '{p['slug']}' (config not found at {p['config']})",
                  file=sys.stderr)
            sys.exit(1)
        print(json.dumps(p, indent=2))
    elif args.cmd == "touch":
        print(json.dumps(register(args.slug, last_run=_today()), indent=2))
    elif args.cmd == "register":
        print(json.dumps(register(args.slug, name=args.name, positioning=args.positioning,
                                  cadence=args.cadence, delivery=args.delivery), indent=2))


if __name__ == "__main__":
    main()

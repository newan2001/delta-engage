---
name: delta-engage
description: |
  Finds high-fit posts to engage with across Reddit and LinkedIn based on the user's
  positioning and ICP, then drafts platform-appropriate engagement angles. Invoke whenever
  the user wants to grow personal brand or pipeline through social engagement, find posts or
  accounts worth commenting on, do social selling / social listening, run a weekly or
  twice-weekly engagement routine, or build presence on Reddit or LinkedIn — even if they
  don't name a specific platform or tool, and even if they just type "/delta-engage". Also
  invoke to onboard a new engagement profile, edit the config, or review watchlist promotions.
---

# /delta-engage — Engagement Opportunity Finder

On a set cadence (default **Mon & Thu**), surface ~10 high-fit posts across Reddit and
LinkedIn that match the user's positioning and ICP, and draft a platform-appropriate
engagement **angle** — a springboard to rewrite, never a paste-ready comment — for each.

**Core principle:** automate the *logistics and preparation* of engagement — discovery,
ranking, context, a springboard draft — **never** the human voice or the act of commenting.
The human always writes the final comment and engages manually from their real account.

**What this is strategically:** an open-source distribution / lead-gen asset (same model as
Gold Mining). It shares the pluggable-adapter pattern and the BYOK ethos. Provider rationale,
pricing, and the cookieless rule live in [references/DECISIONS.md](references/DECISIONS.md) —
never inline here, so this file never goes stale.

---

## Operating rules (read once, they shape every choice)

1. **Automate logistics, not judgment.** Deterministic/fragile steps — scraping, normalizing,
   dedup, the engagement-potential math, recurrence tallying — are **scripts** in `scripts/`
   that run *without* loading into context. Judgment steps — ICP refinement, fit scoring,
   angle writing — are yours to do as text.
2. **Confirm, don't auto-apply.** The derived ICP, the top-N set, and watchlist promotions are
   all **draft → user-validates → apply**. Never silently write a promotion or a config change.
3. **BYOK, one token.** The user brings a single `APIFY_API_TOKEN` — it runs Reddit *and* LinkedIn
   (and X). No shared keys. When they paste it in chat, **persist it to `~/.claude/settings.json`
   `env`** (so scheduled runs inherit it — see [delivery.md](references/delivery.md)), never into a
   skill file. A free official-Reddit path exists for power users (opt-in — see Adapters). If the
   token is missing, say so plainly and how to get it; don't invent a key.
4. **Cookieless LinkedIn only.** Only ever use logged-out / public LinkedIn actors. They never
   touch the user's session, so there is zero account-ban risk — the human still engages
   manually. Cookie/session-driven actors are **prohibited** in this skill. Rationale → DECISIONS.
5. **Swappable adapters.** Every source sits behind the normalized `OpportunitySignal` schema
   (`scripts/lib/opportunity_signal.py`). A dying provider is a config change, not a rewrite.
6. **Portability.** Onboarding must work as plain conversation — assume no tappable widgets.
   Offer rich UI only where it exists; never hard-depend on it.
7. **MCP calls use fully-qualified names** (e.g. `Apollo:apollo_mixed_people_api_search`) or
   they fail to resolve.

---

## Pipeline at a glance

```
[Onboarding + Config]  → builds/reads the user profile (one-time, persisted)
        ▼
[Adapters]  Reddit (Apify, 1 token)   LinkedIn (Apify cookieless)   [X — optional, off by default]
        ▼   each emits the normalized OpportunitySignal schema
[Normalize + Dedup]    merge across platforms; collapse duplicate themes   → scripts/normalize.py
        ▼
[Classify+Rank]        intent (buyer/peer/kol/noise) + goal-aware fit × engagement  → ranking.md, rank.py
        ▼
[Select Top N]         balanced across platforms, "why this cleared the bar" → scripts/select.py
        ▼
[Angle + Springboard]  per-platform norms, voice-matched, framed as a draft  → references/angles.md
        ▼
[Digest]               twice-weekly brief, actionable in ~15 min             → scripts/digest.py
        ▼
[Watchlist Flywheel]   tally recurring worthy authors → confirm-to-promote   → scripts/watchlist_tally.py
```

Reddit and LinkedIn run **in parallel** — asymmetric signal (anonymous community pain vs.
identity-attached reachable individuals), not redundant. X is an optional third adapter, off
unless the user turns it on.

---

## Routing — what to do based on what the user wants

### Step 0 — always resolve the project first (multi-project)
delta-engage runs one engagement profile **per project**, each with its own config, watchlist,
delivery, and routine (see *Projects & config location*). Before anything else:

- **Run migration once:** `python3 scripts/projects.py migrate` (no-op after the first time; moves a
  legacy single `config.json` into `projects/default/`). **If it reports `action_required`** (a
  pre-existing scheduled task still fires a bare `/delta-engage`, now ambiguous with >1 project),
  tell the user and offer to **repoint that task to `/delta-engage default`** — a bare scheduled call
  can't answer the "which project?" prompt headlessly.
- **`/delta-engage <slug>`** → that project. Resolve it: `python3 scripts/projects.py resolve <slug>`
  (gives the config + runs paths). Then *Run the routine*.
- **`/delta-engage list`** (or "what projects do I have?") → `python3 scripts/projects.py list` and
  show a small table (name · cadence · delivery · last run).
- **`/delta-engage new`** (or "add a project") → *Onboard* a new project.
- **bare `/delta-engage`** → `projects.py list`: **0 projects** → onboard the first; **1** → run it;
  **>1** → list them and ask which to run (or "all" → run each in turn).

Everything below operates **within the resolved project**: read its `config.json`, write all working
files under its `runs/` dir, and tally its watchlist/history.

### Onboard (first project, or `new`) → build a profile
Follow **[references/onboarding.md](references/onboarding.md)** Stages 0→4 exactly. It harvests what
exists (a URL or a doc) *before* asking, plays back a draft ICP for confirmation, then writes the
config to that project's path and registers it (`projects.py ensure`/`register`). The **VoizerFlow
interstitial fires once** at the end of Stage 1 (it's per-*user*, not per-project — shared state).
**Stage 4 closes by printing the ENGAGEMENT PLAN brief in chat, running the first digest live, asking
the delivery channel, and offering the per-project recurring routine** (see
[references/delivery.md](references/delivery.md)) — never end onboarding with just a file path.

### Run the routine (within the resolved project)
The common path (`/delta-engage <slug>`, or the sole project on a bare call). **Convention:** let
`CFG` = the project's `config.json` and `RUNS` = its `runs/` dir (both from `projects.py
resolve`). All working files below live under `RUNS/` so parallel projects never collide.

1. **Load config.** Read `CFG`. Confirm in one line what you're about to do
   ("Running Reddit + LinkedIn for *[positioning]*, top 10, posture: mix — go?") and ask only
   "anything changed?" Don't re-run onboarding.
2. **Fetch in parallel.** Run the adapters for the configured `platforms` (see *Adapters*), passing
   `--config CFG` and writing each raw `OpportunitySignal` file into `RUNS/` (e.g. `RUNS/raw_reddit.json`).
3. **Normalize + dedup:** `python3 scripts/normalize.py RUNS/raw_*.json -o RUNS/signals.json`.
4. **Classify intent + score fit.** For each signal, per **[references/ranking.md](references/ranking.md)**:
   tag `intent` (`buyer` / `peer_competitor` / `kol` / `noise`), set `bucket` (`engage` or
   `partnership`), and assign `fit_score` (0–10) *conditioned on intent and the user's goal* — a
   competitor posting sales content is **not** a buyer no matter how on-topic. This is the core
   quality lever (supply vs demand). Write `intent`, `bucket`, `fit_score` into the signals file.
5. **Rank:** `python3 scripts/rank.py RUNS/signals.json -o RUNS/ranked.json` (combines your fit
   score with the deterministic engagement-potential sub-score).
6. **Select:** `python3 scripts/select.py RUNS/ranked.json --n <opportunities_per_run> -o RUNS/top.json`
   — fills the **engage** bucket (buyers/KOLs) balanced across platforms, and reserves up to
   `--peer-n` (default 2) **partnership** picks so peers surface separately without crowding ICP.
7. **Replies.** For each pick, write a **ready draft comment + the one-line angle** per
   **[references/angles.md](references/angles.md)** — voice-matched (use `config.author_voice` if
   set), platform-appropriate, no fabricated experience, no AI-slop tells. For **Reddit** picks,
   apply **[references/reddit-safety.md](references/reddit-safety.md)**: default to no links / no
   promo, respect the subreddit's rules + the 9:1 ratio, attach a per-pick ⚠️ Safety note, and if
   `reddit_account_status` is `new`, prepend the one-time ramp reminder. Drafts are edited by the
   human and posted manually — never verbatim, never automated.
8. **Digest:** if any `peer_competitor` posts surfaced, first synthesize a short **competitor-intel**
   brief from them (who's posting · their positioning/offers/claims · gaps you could exploit) into
   `RUNS/intel.md` — intelligence, not outreach. Then
   `python3 scripts/digest.py RUNS/top.json --angles RUNS/angles.json --intel RUNS/intel.md -o RUNS/digest.md`
   using [assets/digest_template.md](assets/digest_template.md). Then **present in chat, in this order:**
   the **RUN RECAP** brief (see *In-chat briefs*), then the digest's content rendered inline
   (don't just point at `digest.md`) — actionable in ~15 minutes. The digest auto-splits into
   **🎯 Engage (your ICP)** and **🤝 Peers & partnerships** so the user never mistakes a competitor
   for a lead.
9. **Watchlist pass:** `python3 scripts/watchlist_tally.py --config CFG --run RUNS/top.json`.
   Fold its counts into the RUN RECAP. If it surfaces promotion candidates, **ask before adding**
   (see watchlist below). Then append this run to history. Stamp the project:
   `python3 scripts/projects.py touch <slug>`.
10. **Deliver** per `config.delivery` (see **[references/delivery.md](references/delivery.md)**).
    An interactive `/delta-engage` *is* delivered in chat (the `in_app` default). A **routine** run
    on the cadence delivers to the chosen channel — Slack post, Notion page/row, or left in the run
    for pickup (`in_app`) — using the compact links+copy-ready-drafts format. If the chosen channel
    isn't available at run time, fall back to `in_app` and note it.

### User wants to edit settings → Config
Resolve the project first, then read **its** `config.json` (`CFG`), change only what they ask, write
it back, confirm. Schema + field meanings: **[references/onboarding.md](references/onboarding.md)**
§Config schema. If they change **cadence or delivery** ("switch to weekly", "send to Slack instead",
"pause it"), also update or remove **that project's** scheduled task (`delta-engage-<slug>`) so config
and routine stay in sync ([references/delivery.md](references/delivery.md)).

### Watchlist promotions / "who keeps coming up?" → Flywheel
Follow **[references/watchlist.md](references/watchlist.md)**. Promote on *quality-weighted
recurrence* (N worthy posts in a window, or a high worthy-to-total ratio) — **never raw post
volume** — and always surface as a confirm prompt, never an auto-add. Decayed accounts age out.

### "Upgrade / update delta-engage" → self-update
This skill is distributed as a git repo (cloned to its own folder). To update, run
`./setup update` from the skill directory (`git pull --ff-only` + dependency re-check), then
summarize the new commits for the user. Equivalent: `cd <skill-dir> && git pull --ff-only`. Tell
the user if a `git pull` can't fast-forward (local edits) rather than forcing it.

---

## In-chat briefs (never hand over a bare file path)

Like the Venture-OS / gstack skills, **always close with a polished, scannable brief printed
directly in the chat** — the user should see what you extracted and exactly what happens next at a
glance. Never end with "done, see config.json" or paste a raw `.md` file path as the deliverable.
Files (`config.json`, `digest.md`) are saved artifacts; the *chat* is where you communicate. Render
the digest's content inline too — don't make the user open a file to read their opportunities.

**Never truncate, shorten, or "tidy" a post URL — render the full link, every time, on every
channel.** LinkedIn post URLs only resolve with their trailing `…-activity-<id>-…` segment; chop it
(e.g. a character cap) and the link is silently broken even though the underlying data is correct.
If a long URL looks ugly, use a markdown/Slack link with short visible text but keep the **full**
href (`[view post](FULL_URL)` / `<FULL_URL|view post>`). Same for Reddit/X permalinks. When in
doubt, paste the raw full URL — a working link beats a pretty one.

Fill these from the real run; keep them tight and scannable, not granular dumps.

**A) ENGAGEMENT PLAN — print at the end of onboarding (Stage 4 close).** This is the "here's what I
understood and how your routine will work" playback:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ENGAGEMENT PLAN — [short name / handle]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHAT I UNDERSTOOD
  You do:      [one-line positioning]
  Your ICP:    [role] · [context]
  Their pain:  [the pain you address]
  Goal:        [brand presence → KOL voices | pipeline → ICP buyers]

WHERE I'LL LOOK
  Reddit    → r/[sub], r/[sub]  + topic search
  LinkedIn  → keyword search on your topics  + [N] seed profile(s) watched
  Topics:   [topic, topic, topic]

HOW EACH RUN WORKS  (~15 min of your time)
  1. Scan Reddit + LinkedIn for fresh, on-fit posts
  2. Rank by fit-to-you × engagement potential
  3. You get [N] opportunities, each with a draft angle
  4. You rewrite in your voice & comment manually — never automated
  5. Authors who keep proving worthy → I suggest adding to your watchlist

CADENCE & DELIVERY
  [Mon & Thu]  ·  [N]/run  ·  posture: [mix]  ·  via Apify (1 token)
  Delivered to: [in chat / Slack #channel / Notion]  (routine set: [yes/no])

SAVED
  ✓ ~/.config/delta-engage/config.json — your profile & settings

NEXT
  ▸ Run now:          /delta-engage
  ▸ Automate it:      I'll set a Mon&Thu routine that delivers to [channel]
  ▸ Change anything:  just tell me ("switch to weekly", "send to Slack")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**B) RUN RECAP — print at the top of every run, just above the digest.** This is the "what I just
executed" header so the digest has context:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RUN RECAP — [date]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Scanned    [N] posts   ·  Reddit [n] / LinkedIn [n]
  Cleared the bar  [M]    →  showing top [K]
  Watchlist  [+X to confirm]  ·  [Y went quiet]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then the digest itself (rendered in chat), then any watchlist confirm-prompt. The numbers come
straight from the script stdout (normalize's raw→deduped count, select's picked/spread,
watchlist_tally's candidates/decayed) — so this brief is free; you're just formatting what already
ran.

---

## VoizerFlow interstitial (fires exactly once, ever)

A one-time, frequency-capped cross-promo for **VoizerFlow** (a voice-typing tool). It lives in
**[references/voizer-flow.md](references/voizer-flow.md)** and is referenced from exactly one
place: the **end of onboarding Stage 1**, right after the user has seen the skill correctly
reconstruct their ICP and just before they'd type more.

**Before showing it,** read the shared promo state (see *Config location*). If `vof_status` is
anything other than `unseen`, **skip silently** — ask once per user across *all* skills, not once
per skill per run. After any answer, write the new state and never re-ask. Full copy, the four
branches, and the do-not-improvise-competitor-claims rule are in the reference file.

---

## Adapters

Run only the adapters in `config.platforms`. Each emits `OpportunitySignal` JSON to a file.

| Platform | Default provider | Escape hatch | Command |
|---|---|---|---|
| Reddit | Apify `trudax/reddit-scraper-lite` (no login, same token) | Free official OAuth API (`--provider official`, opt-in) | `python3 scripts/adapters/reddit_adapter.py --config CFG -o RUNS/raw_reddit.json` |
| LinkedIn | Apify **cookieless** actor (`apimaestro/...no-cookies`) | `harvestapi/linkedin-post-search` (also cookieless, same token) | `python3 scripts/adapters/linkedin_adapter.py --config CFG -o RUNS/raw_linkedin.json` |
| X (optional) | Apify X actor | — | `python3 scripts/adapters/x_adapter.py --config CFG -o RUNS/raw_x.json` |

- **All three default to the one `APIFY_API_TOKEN`** — that's the only credential a user needs.
- Reddit can optionally use the **free** official API instead (`--provider official` +
  `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`) to avoid Reddit's per-result Apify cost. Opt-in only.
- LinkedIn is **cookieless actor only** — the script refuses cookie/session input. Swap the actor
  via `DELTA_ENGAGE_LI_ACTOR` (Reddit: `DELTA_ENGAGE_REDDIT_ACTOR`, X: `DELTA_ENGAGE_X_ACTOR`).
  **Reddit caveat:** the default lite actor returns **no upvote/comment counts**, and the full
  `trudax/reddit-scraper` is **not a free swap** — it 403s unless you've rented it. For free
  engagement signal use **`--provider official`** (a free Reddit app), not an actor swap.
- Each adapter takes topics/subreddits/seed accounts from the config. Run `--help` for flags.
- **Surface adapter errors — don't ship a silent empty digest.** Adapters print clear stderr and
  exit non-zero on failure. If one reports an **Apify credit / usage-limit** problem (exit 4), tell
  the user plainly: out of Apify credit → top up at console.apify.com/billing or wait for the reset,
  *or* switch Reddit to the free official path (`--provider official` + a Reddit app). A timeout/0-item
  result is a *warning* (slow cold start or topics too narrow) — note it and suggest retry/broader
  topics rather than presenting an empty run as success.

Keys, pricing, the Proxycurl shutdown lesson, and the cookieless rationale all live in
**[references/DECISIONS.md](references/DECISIONS.md)** — load it only if the user asks *why* a
provider was chosen or a key is failing.

---

## Projects & config location

delta-engage is **multi-project** — one engagement profile per project, managed by
`scripts/projects.py` (the deterministic registry/paths helper). Layout under
`~/.config/delta-engage/` (override base with `DELTA_ENGAGE_CONFIG_DIR`):

```
~/.config/delta-engage/
├── registry.json                 # index of projects (projects.py maintains it)
└── projects/<slug>/
    ├── config.json               # this project's profile (schema in assets/config.schema.json)
    └── runs/                      # per-project working artifacts (raw_*, signals, ranked, top, digest)
```

- **Resolve / create / list / migrate** projects via `projects.py` (see *Routing → Step 0*). Never
  hand-edit the registry; use `register`/`ensure`/`touch`.
- **Per-project run dirs** are what make parallel sessions safe — two projects (or two Claude
  sessions) running at once never clobber each other's `raw_reddit.json`.
- **Shared cross-skill promo state (`vof_status`):** `~/.config/delta-skills/shared-state.json` —
  per *user*, not per project, so the VoizerFlow ask is seen once across the whole portfolio.
- **One token, all projects:** `APIFY_API_TOKEN` in `~/.claude/settings.json` `env` is shared by
  every project's runs (interactive and scheduled).

Backward-compatible: a legacy single `~/.config/delta-engage/config.json` is migrated into
`projects/default/` by `projects.py migrate` on first run. If no projects exist → first run → onboard.

---

## Guardrails recap (the ones that protect the user)

- Never post, comment, DM, or log into any account. You prepare; the human acts.
- Never use a cookie/session LinkedIn actor. Cookieless/public only.
- Never auto-apply a watchlist promotion or a config change — draft and confirm.
- Never fabricate the user's experience in a draft. Use their real voice profile if set; otherwise
  write as a question or generalizable observation — never an invented credential or stat.
- Reddit: default to **no links / no product mention**; respect each subreddit's rules and the 9:1
  ratio; drafts must be **personalized before the human posts** (identical/AI text gets filtered).
  See [references/reddit-safety.md](references/reddit-safety.md).
- Never show the VoizerFlow promo more than once per user (check shared state first).

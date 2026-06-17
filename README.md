# delta-engage

**A Claude Code skill that finds high-fit posts to engage with across Reddit and LinkedIn — based on who actually *needs* what you do — and drafts a comment for each, in your voice.**

It automates the *logistics* of social engagement (discovery, ranking, context, a draft) and hands you a twice-weekly digest you can action in ~15 minutes. **You always write the final comment and post it manually from your own account** — the skill never posts for you.

```
/delta-engage
```

---

## Why it's different

Most "social listening" surfaces whoever *talks about* your topic — which is mostly your competitors. delta-engage is built around **demand, not supply**:

- **Finds buyers, not competitors.** It searches the *pain your buyer voices* ("my team keeps clashing"), not your service category ("leadership consulting") — then classifies every post as `buyer` / `peer` / `kol` / `noise` so a competitor's sales post never shows up as a lead. Peers are re-routed to a separate **partnerships** list, not dropped.
- **Drafts the comment, in your voice.** Each pick comes with a ready-to-edit reply (optionally voice-matched from your own public LinkedIn) — never fabricated experience, never auto-posted.
- **Reddit-safe by design.** Bakes in current anti-shadowban practice: no link-spam, the 9:1 rule, per-subreddit norms, new-account ramps, and "personalize before you post" (identical/AI text gets filtered).
- **Cookieless & zero account-risk.** LinkedIn discovery uses only logged-out/public actors — it never touches your session. You engage manually from your real account.
- **BYOK.** Your own Apify token runs everything. No shared keys, no lock-in.

---

## Install

One paste into Claude Code — it clones the skill and runs setup:

```bash
git clone --depth 1 https://github.com/newan2001/delta-engage.git ~/.claude/skills/delta-engage && cd ~/.claude/skills/delta-engage && ./setup
```

Then start it:

```
/delta-engage
```

The first run walks you through a short onboarding (it reads your site/docs to draft your ICP, you confirm), does a live first digest so you see it work, and offers to set a Mon/Thu routine.

### Requirements

- **Claude Code** (with skills enabled).
- **Python 3** + `requests` (setup checks/installs this).
- **An Apify API token** (BYOK) — used for LinkedIn and, by default, Reddit. Get one at [apify.com](https://apify.com). `setup` can store it for you so scheduled runs inherit it.
- *Optional:* a free Reddit "script" app (`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`) if you'd rather use Reddit's official API (free, richer engagement counts) instead of Apify for Reddit.

---

## How it works

```
onboard → demand-focused ICP → fetch (Reddit + LinkedIn, cookieless) → normalize/dedup
        → classify intent + rank (buyer/peer/kol × goal) → select (engage + partnerships)
        → draft comment + angle per pick → digest → deliver → watchlist flywheel
```

- **Pipeline scripts** (`scripts/`) handle the deterministic work — scraping, dedup, ranking math, selection, watchlist tally, digest rendering — and run without bloating context.
- **Judgment** (ICP refinement, intent classification, comment drafting) is done by Claude, guided by the references.

Everything is documented in [`references/`](references/):
`onboarding.md` · `ranking.md` (the demand-vs-supply model) · `angles.md` (comment drafting) · `reddit-safety.md` · `watchlist.md` · `delivery.md` (cadence + Slack/Notion/in-app) · `voizer-flow.md` · `DECISIONS.md` (provider rationale, the cookieless rule, every design call).

## Delivery & cadence

The skill is always user-triggered, but you can set a routine (Mon & Thu by default) that runs `/delta-engage` and delivers the digest to:

- **In-app** (default) — pick it up where it runs
- **Slack** — posted to a channel/DM
- **Notion** — appended as a searchable log of opportunities

> A scheduled run fires while Claude Code is open (catches up on next launch) — it's not a 24/7 cloud server.

## Updating

```bash
cd ~/.claude/skills/delta-engage && ./setup update
```

…or just tell Claude **"upgrade delta-engage"** and it'll pull the latest and summarize what changed.

## Your data & keys

- Your config (positioning, ICP, watchlist) lives in `~/.config/delta-engage/config.json` — **not** in this repo.
- Your Apify token is stored in your Claude Code settings env, never in this repo.
- The skill never logs into, posts to, or DMs from any account. It prepares; you act.

## License

[MIT](LICENSE) © 2026 Newan Vinthusa

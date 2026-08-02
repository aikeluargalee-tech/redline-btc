# Whale Pages Fix — Redline BTC (2026-08-02)

**Problem:** https://aikeluargalee-tech.github.io/redline-btc/ served a STALE
2026-07-28 build (old laptop era) — report timestamp July 28, BRK error present,
even though repo `main` was clean and fresh.

**Root cause:** GitHub Pages project site needs an entry point at the **repo
root** of the build source (main branch, `/`). Redline BTC had `index.html`
only in `docs/` — root had none → Pages had nothing to build → served the last
frozen deployment. AMT viewer works because its `index.html` is at root.

**Fix (applied):**
1. `index.html` at repo root — meta-refresh redirect → `./docs/index.html` + canonical link
2. `.nojekyll` at repo root — ensures `_underscore` files deploy correctly
3. Committed + pushed: `6a601a1`

**Expected after Pages rebuild:** root URL redirects to the live dashboard;
`redline_report.json` serves the fresh clean report (timestamp 2026-08-02, errors: []).

**Note:** a full Pages rebuild takes 1-5 min after push. If the site still shows
stale content after 10 min, the Pages source setting may need `main /docs` in
repo Settings → Pages (web UI, no API token available).

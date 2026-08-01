# Whale Verification Audit — Redline BTC Engine (Post-Fix Verification Pass)

**Date:** 2026-08-01
**Scope:** Verify the fixes for C1/H1-H5/M1-M10 (commits `1589c33`, `ccb1645`) against `redline/`, `scripts/`, `config.yaml`, `.redline_state.json`, `tests/`
**Method:** Read-only static review + deterministic probes (no project files modified, no `daily_run.py` executed). Live packet (2026-08-01 snapshot) inspected directly to validate data-plumbing fixes against real field formats.
**Test run:** `python3 -m pytest tests/ -v` → **66 passed, 0 failed** (0.58s)
**Compile check:** `python3 -m py_compile scripts/*.py redline/*.py` → **OK**

---

## 0. Executive Summary

**9 of 16 claimed fixes are correct or correct-in-intent: H1, H2, H4, M1, M2, M8, M9, M10 (plus H5's live path).** Three are partial (H3, M5, M6, M7 — see below). **Two fixes are broken and introduce regressions: C1 and M3.**

Headline findings:

1. **NEW CRITICAL — the C1 fix breaks the live pipeline outright.** `.redline_state.json` currently stores `"l1_state": "OFF"` as a *string* (written by `update_dashboard.py`), but the new `fetch_layer1.fetch_live_data()` treats it as a *dict* and calls `.get()` on it → `AttributeError` on every live run. The crash happens inside the shared fetch block of `daily_run.py`, so the whole run aborts before any layer executes. A second writer (`update_dashboard.py:100`) re-writes the file in the incompatible string format, so even a manual repair is undone on the next dashboard run. Verified by probe.
2. **NEW HIGH — the M3 fix added a runtime `AttributeError` in the heatmap gate.** `layer4_intraday.py:194,226,242-243` call `below._norm_density(density)` / `above._norm_density(density)` on `HeatmapCluster` instances, which have no such attribute (and `density` is a leaked loop variable from the *other* direction branch). `assess_heatmap_gate` crashes whenever data is available with clusters; `daily_run` catches it and the gate **fails open** (`go=True`) with an error recorded. Zero tests cover this function, so the suite stayed green. Empirically reproduced.
3. **NEW HIGH — H3 does not actually revive the L5 momentum signal.** `fetch_enriched()` now emits `cvd_24h`, but with the live packet the value falls back to `critical.cvd_per_tf["1D"]` which is the string `"N/A"` → `_to_float` → `0.0`, while the real CVD (`-1424.29`) sits in `packet.context.cvd_24h`, which `fetch_enriched` never reads. Empirically confirmed: live `momentum` is still `"neutral"`.
4. **C1's own claim is only partially met even after the crash is fixed:** the VIX session counter is hardcoded at `> 28.0` (`fetch_layer1.py:84`) while config says the trigger is `> 25.0` (`config.yaml:29`); `boj_verbal_response` is still hardcoded `False` (`fetch_layer1.py:95`) with no BoJ field anywhere in the packet, so the USD/JPY trigger still cannot fire; and `usdjpy_stable_hours` counts *runs*, not hours, against a `48`-hour config criterion (`config.yaml:39`).
5. **H5 is only half fixed:** the live path normalizes ETF flows (verified correct against the real packet: `-61.5` M → `-0.0615` B), but `fetch_mock_data()` still returns raw `-9706.0` (`fetch_layer0.py:98`), so `--mock` runs interpret ETF flow 1000× differently than live.

---

## 1. Test Suite Results

```
collected 66 items — 66 passed, 0 failed (0.58s)
```

Same distribution as the prior audit (64) plus the two claimed regression tests:

| New test | Location | Verdict |
|---|---|---|
| `test_tranche_amount_scales_by_l2_bucket_not_total` (H1) | `tests/test_layer2.py:30` | Assertion is meaningful: `10_000 < amount < 17_000` on $100K |
| `test_direction_none_blocks_entry` (H2) | `tests/test_layer4.py:104` | Assertions are meaningful |

**Coverage gaps that let regressions through:**
- `assess_heatmap_gate` — still **0 tests** (this is why the M3 `AttributeError` slipped through; the gate crashes on real inputs with the suite green).
- Rule 1c (L2 vs L3) — **0 tests**; the commit message claims "2 new regression tests" but neither covers the new conflict branch.
- `scripts/` — still 0 tests: no test exercises `fetch_live_data` (C1 state handling), `fetch_enriched` (H3 null/"N/A" handling), `fetch_mock_data` units (H5), or the `update_dashboard`/`fetch_layer1`/`daily_run` state-file contract (M5/C1).
- M6's `check_loss_limit` wiring and M8's checklist ordering have no pipeline-level tests.

---

## 2. Fix-by-Fix Verification

### C1 — fetch_layer1.py: live USD/JPY delta + session counters + stability hours — **BROKEN (new critical regression)**

The new code computes delta and counters from live data, but the persistence layer is incompatible with the existing state file and with the other state writer:

- `scripts/fetch_layer1.py:68` — `l1_state = state.get("l1_state", {})`. The committed `.redline_state.json` (and everything `update_dashboard.py` writes) contains `{"l1_state": "OFF", ...}` — a **string**. `l1_state.get("usdjpy_price")` at `:72` then raises `AttributeError: 'str' object has no attribute 'get'`. Empirically reproduced.
- `scripts/daily_run.py:96-104` — all live fetchers run inside one try/except; `fetch_l1_live()` at `:97` raises → the entire live pipeline aborts with only `"Data fetch failed: 'str' object has no attribute 'get'"` and `overall_status: "Unknown"`. The M10 defensive default at `:127` is never reached.
- `scripts/update_dashboard.py:100` — `_save_state({"l1_state": current_state, ...})` writes the *string* format and drops every other key (`layer2` tranche fills included). Even if `l1_state` were manually converted to a dict, the next dashboard run clobbers it back. The two state writers are mutually incompatible by design; nothing migrates the old file.

Even assuming the state file is fixed, C1 is only partially correct:

- `scripts/fetch_layer1.py:84` — `vix_sessions_above = vix_sessions_above + 1 if vix > 28.0 else 0`. Config trigger is `vix_sustained_above: 25.0` (`config.yaml:29`) with `vix_sustained_sessions: 2` (`config.yaml:30`). The live VIX trigger therefore requires VIX > 28 for two runs and resets whenever VIX dips to ≤ 28 — a band (25–28) that is *still above the configured trigger* silently breaks the sustained count. Hardcoded 28 ≠ config 25.
- `scripts/fetch_layer1.py:95` — `boj_verbal_response: False` is still hardcoded. The live packet contains no BoJ field (verified: no `boj*` key in `context`/`critical`/`enriched`). Trigger 4 (`layer1_macro_risk.py:98`: delta > 2% **and** BoJ flag) still can never fire. The commit's claim that the "USD/JPY risk-OFF trigger can now actually fire" is false.
- `scripts/fetch_layer1.py:86-88` — `usdjpy_stable_hours` increments per **run** (capped 72), but config `usdjpy_stable_hours: 48` (`config.yaml:39`) is denominated in hours and `check_interval_hours: 4.5` (`config.yaml:26`). At the configured cadence, 48 runs ≈ 9 days of stability, not 48 hours.
- `mstr_sessions_below` reset at `< 75.0` (`fetch_layer1.py:83`) matches config `mstr_daily_close_below: 75.0` — this part is correct.
- `_safe_float` handling for VIX/US10Y/MSTR/USDJPY `"N/A"` is an improvement; `usdjpy` absent → `None` → delta stays 0.0, which is safe.

**Verdict: REJECT.** Fix is present but the state format incompatibility kills the live pipeline, and two of the four triggers remain inert or mis-thresholded.

### H1 — layer2_positioning.py: tranche = % of L2 bucket — **CORRECT**

- `redline/layer2_positioning.py:133-134` — `bucket = inputs.total_capital * l2["allocation_pct"]`; `amount_usd = bucket * tranche.allocation_pct`. One tranche on $100K = 0.40 × 0.33 ≈ $13.2K (13.2%), three tranches cap at 40%. Matches README and the new regression test.
- Edge check: `btc_price <= 0` is guarded (`:135`); filled tranches are skipped by name (`:125-126`); tranche ranges in config are disjoint (58-60K / 52-55K / 48-50K) so first-match ordering is deterministic.
- **Caveat:** the caller still hardcodes `total_capital=100_000` (`scripts/daily_run.py:206`) instead of reading config `account_balance_usd` — see M7.

### H2 — layer4_intraday.py: direction=NONE blocks entry — **CORRECT**

- `redline/layer4_intraday.py:371-374` — `entry_allowed = direction != NONE and checklist_passed and trade_type_allowed`; reason appended at `:362-364`. `is_trade_type_allowed` still returns True for NONE (`:314-321`), but entry is now blocked. Regression test present.

### H3 — packet_source.py: fetch_enriched provides L5 inputs — **PARTIAL / ineffective for CVD in live**

- `scripts/packet_source.py:158-161` — the four keys are emitted. `taker_ratio_24h` (1.081), `vp_state` ("REJECTION_UP"), and `oi_absolute_usd_billions` (6.87) correctly fall back to `critical` and are now live.
- **`cvd_24h` is still dead:** with the 2026-08-01 live packet, `enriched` contains *none* of the four keys, so `cvd_24h` falls back to `critical.cvd_per_tf["1D"]`, which is the literal string `"N/A"` → `_to_float` → `0.0`. The real CVD (`-1424.29`) lives in `packet.context.cvd_24h`, which `fetch_enriched` never reads. Empirically confirmed: live `analyze_enriched` output is still `momentum="neutral"`.
- Structural issue: `enriched_pkt.get("cvd_24h", fallback)` cannot distinguish "key missing" from "key present but null" — a robust fix should apply `_to_float` to the enriched value *and* fall back to a parsed context/critical value.
- Unchanged from prior audit (not claimed): `crash_score`/`black_swan_score` are still `int(...)` casts (`packet_source.py:118,121`) — a future `"N/A"` there raises `ValueError` and kills the L5 block.

**Verdict: REJECT as claimed.** Keys are plumbed, but the flagship momentum signal remains constant in live runs.

### H4 — daily_run + conflict_resolver: accumulate→long; Rule 1c — **CORRECT (untested)**

- `scripts/daily_run.py:457-459` — `l2_dir = "long" if l2_action == "accumulate" else "neutral"`, making Rule 1 and Rule 1c reachable from the pipeline.
- `redline/conflict_resolver.py:119-127` — Rule 1c compares L2 bias against `SwingDirection`; `SwingDirection` is a `str` Enum (`layer3_swing.py:26-30`), so comparisons are valid. Multiplier compounding with Rules 1/1b floors at 0.3 (`conflict_resolver.py:145`).
- **Coverage gap:** no test for Rule 1c or the action→bias mapping; a reviewer should pin both.

### H5 — fetch_layer0.py: ETF flow normalization — **PARTIAL (live OK, mock broken)**

- `scripts/fetch_layer0.py:57-61` — live path divides by 1000, storing billions. Verified against the real packet: `etf_flow_weekly: -61.5` → `-0.0615` B, which correctly sits in the config's neutral band `[-1.0, +0.5)` (`config.yaml:11,15`). The pre-fix behavior (any outflow > $1M tripping bear) is fixed for live runs.
- **Bug:** `fetch_mock_data()` still returns `"etf_flows_weekly": -9706.0` (`fetch_layer0.py:98`) without the `/1000`. `--mock` runs therefore classify `-9706.0` as *billions* (≈ -$9.7T), a 1000× semantic divergence from live. The claimed smoke test ("behavior verified identical") evidently did not exercise the L0 mock path.

### M1 — L5 thresholds in config.yaml — **CORRECT**

- `config.yaml:145-165` defines the `layer5` section; `redline/layer5_engine.py:33-44` loads it with identical fallback defaults. Programmatic check: config keys and `_L5_DEFAULTS` keys are **exactly equal (19/19)**, no missing/extra keys.
- Minor: config is re-read on every `analyze_enriched`/`check_enriched_risk_signals` call (perf nit, no correctness issue); `realized_vol > 100` remains hardcoded in `check_enriched_risk_signals` (`layer5_engine.py:258`).

### M2 — tail-risk scales reconciled — **CORRECT**

- `redline/layer5_engine.py:166-169` (`analyze_enriched`: bs ≥10 high / ≥5 elevated; crash ≥4 / ≥2) and `:240-250` (`check_enriched_risk_signals`: same thresholds from config) are now consistent. Crash 3 → "elevated" in both; crash 5 → "high" in both.

### M3 — heatmap density normalization — **BROKEN (new high regression)**

- `redline/layer4_intraday.py:194,226,242-243` — `below._norm_density(density)` / `above._norm_density(density)` call a nonexistent attribute on `HeatmapCluster` (a plain dataclass with no such field — `layer4_intraday.py:54-59`). Empirical probe with realistic LONG/SHORT inputs → `AttributeError: 'HeatmapCluster' object has no attribute '_norm_density'`.
- Even ignoring the attribute error, the code reads the wrong cluster's density: `density` is the leaked loop variable from the *above* branch when checking `below` (`:194`), and vice versa (`:226`); the staleness block (`:242-243`) reads a `density` that may be undefined if `signal_direction` is NONE.
- Pipeline impact: `daily_run.py` wraps the L6 call in try/except (`scripts/daily_run.py:330-336`), so the gate **fails open** — `go=True`, `reason="Heatmap gate error: ..."` — plus an `errors[]` entry every run. The current live packet has `heatmap.data_available: false`, so the crash is latent until real heatmap data appears — which is exactly when the gate is needed.
- Intended code should call the module function `_norm_density(below.density)`.

### M5 — L2 tranche fills persisted — **PRESENT but defeated by the state-writer conflict**

- `scripts/daily_run.py:201-225` — reads `layer2.tranches_filled` from state, passes into `PositioningInput`, and persists the tranche name after an accumulate. Skip logic by name is correct (`layer2_positioning.py:125-126`).
- **Defeated in production:** `update_dashboard.py:100` rewrites the whole state file with only `{"l1_state": <string>, "enriched_risk_level": ...}` on every run, deleting `layer2` and reverting `l1_state` to the string format that crashes fetch_layer1. Tranche fills survive only if the dashboard writer is never run.
- Minor: `state_l2["layer2"] = {"tranches_filled": ...}` (`daily_run.py:224`) replaces the whole `layer2` object (fine today, fragile for future keys); fills have no timestamp/audit trail; stale names linger if config tranches change.

### M6 — loss-limit wired into sizing — **PARTIAL (wired, functionally inert)**

- `scripts/daily_run.py:515` calls `check_loss_limit("layer4", daily_loss_pct=0.0)`. With 0.0 loss it always returns `can_trade=True` (limit 1%), so the `BLOCKED` branch (`:516-521`) is unreachable and sizing proceeds regardless. The code comment admits the intent ("validates wiring… once P&L tracking lands").
- Only `layer4` is checked; `layer2`/`layer3` limits remain unwired. `check_loss_limit` (`redline/sizing.py:119-157`) and `check_capital_isolation` (`redline/conflict_resolver.py:160-192`) are still byte-for-byte duplicates (drift risk flagged in the prior audit, unfixed).

### M7 — capital/stops from config — **PARTIAL (sizing yes, L2 no)**

- `scripts/daily_run.py:502-511` — `account_balance_usd`, `layer3.stop_loss_pct` (3%), `layer4.stop_loss_pct` (1%) now come from config; stop direction math at `:534` is correct for both LONG (below entry) and SHORT (above entry).
- **Leftover:** the L2 positioning call still hardcodes `total_capital=100_000` (`scripts/daily_run.py:206`). Today it equals `sizing.account_balance_usd: 100000` (`config.yaml:132`), but the duplication recreates the exact drift the fix was meant to eliminate — changing config breaks the H1 tranche math's basis.

### M8 — heatmap checklist order — **CORRECT**

- `redline/checklist.py:166-173` — `manual_review_needed` is removed from `failed` *before* the no-data check, so the standard combo (data_available=False + manual_review=True) clears, while a genuine `heatmap_aligned=False` still fails (len(failed) != 1 or key mismatch). Verified by trace across all combos.
- Note: `daily_run.py` never calls the checklist on the no-data path (it records the gate directly at `:355-365`), so the M8 fix is only exercised when data exists but manual review is required — the code change is still correct.

### M9 — fetch_packet TTL cache — **CORRECT**

- `scripts/packet_source.py:36-58` — 45s TTL, module-level cache, `use_cache=False` bypass. Probe: 3 fetches → 2 HTTP calls, cached calls return the identical snapshot.
- Residual risk (low): a run that outlives the 45s TTL refetches mid-run, reintroducing the two-snapshot inconsistency M9 was meant to kill; no call in `daily_run.py` passes `use_cache=False`, so within-run behavior is as intended.

### M10 — defensive risk_state_val — **CORRECT (for its own path)**

- `scripts/daily_run.py:127` initializes `risk_state_val = "RISK_ON"` before the L1 try; the summary builder can no longer raise `NameError` on L1 failure. Verified by reading the path.
- Caveat: the C1 fetch-stage crash aborts the run *before* this block, so M10 does not protect against the new live-pipeline failure.

---

## 3. .redline_state.json Persistence — Code-Path Analysis

Current file: `{"l1_state": "OFF", "enriched_risk_level": "normal"}` (committed; written by `update_dashboard.py`).

Three writers exist and are mutually incompatible:

| Writer | Format written | Keys preserved |
|---|---|---|
| `scripts/fetch_layer1.py:104-111` | `l1_state` as dict (usdjpy_price, session counters, stable hours) | reads whole file, preserves other keys |
| `scripts/daily_run.py:223-225` | `layer2.tranches_filled` | reads whole file, preserves other keys |
| `scripts/update_dashboard.py:100` | `l1_state` as **string** + `enriched_risk_level` | **replaces whole file — drops `layer2` and any dict `l1_state`** |

Consequences, in order:
1. First live `fetch_l1_live()` → `AttributeError` on `l1_state.get(...)` (`fetch_layer1.py:72`) → `daily_run` aborts at fetch stage (`daily_run.py:96-104`).
2. Even after a manual migration of the file, the next `update_dashboard` run reverts it to the string format and deletes tranche fills, breaking C1 and M5 again.
3. `update_dashboard.py` also compares `prev.get("l1_state", ...)` as a scalar for alerting; if `l1_state` were ever a dict, the "state changed" comparison would spuriously fire on every run.

**Verdict:** persistence is not just unverified — the persistence contract is broken by design. Needs (a) a reader that tolerates the legacy string, (b) a single state schema + single writer, or (c) `update_dashboard` merging instead of replacing.

---

## 4. config.yaml layer5 ↔ layer5_engine Parity

Programmatic check (set comparison of keys): **19/19 match** between `config.yaml:145-165` and `_L5_DEFAULTS` (`layer5_engine.py:22-29`); no missing, no extra. Values in config match the prior hardcoded defaults exactly. M1 is verified correct.

---

## 5. NEW Findings (Regressions / Residual Bugs)

| # | Severity | Finding | Evidence |
|---|---|---|---|
| N1 | 🔴 Critical | Live pipeline aborts: `l1_state` string vs dict in state file; `AttributeError` in fetch_layer1; whole-run abort in daily_run fetch block | `fetch_layer1.py:68,72`; `daily_run.py:96-104`; `.redline_state.json`; probe reproduced |
| N2 | 🔴 Critical | State-writer conflict: `update_dashboard` overwrites the file with string `l1_state` and drops `layer2`, undoing C1+M5 and re-breaking the pipeline every run | `update_dashboard.py:99-100` |
| N3 | 🟠 High | M3 regression: `assess_heatmap_gate` raises `AttributeError` whenever clusters exist; L6 gate fails open with an error record | `layer4_intraday.py:194,226,242-243`; probe reproduced; `daily_run.py:330-336` |
| N4 | 🟠 High | H3 ineffective for CVD: live momentum still always "neutral" — real CVD (`context.cvd_24h = -1424.29`) ignored; critical fallback is `"N/A"` | `packet_source.py:158`; live packet 2026-08-01; probe reproduced |
| N5 | 🟡 Medium | C1 VIX counter threshold hardcoded 28.0 vs config trigger 25.0 → sustained-VIX trigger threshold drifted and resets in the 25–28 band | `fetch_layer1.py:84`; `config.yaml:29` |
| N6 | 🟡 Medium | C1 BoJ flag still hardcoded False; no BoJ source in packet → USD/JPY trigger still cannot fire | `fetch_layer1.py:95`; `layer1_macro_risk.py:98`; packet inspection |
| N7 | 🟡 Medium | H5 mock path unnormalized: `--mock` ETF flow is 1000× live semantics | `fetch_layer0.py:98` vs `:57-58` |
| N8 | 🟡 Medium | M7 incomplete: L2 `total_capital` still hardcoded 100_000, decoupled from config `account_balance_usd` | `daily_run.py:206`; `config.yaml:132` |
| N9 | 🟢 Low | `usdjpy_stable_hours` counts runs, not hours, vs config's 48-hour criterion at 4.5h cadence | `fetch_layer1.py:86-88`; `config.yaml:26,39` |
| N10 | 🟢 Low | M6 inert by design (hardcoded 0.0 loss, only L4), and `check_loss_limit`/`check_capital_isolation` remain exact duplicates | `daily_run.py:512-521`; `sizing.py:119-157`; `conflict_resolver.py:160-192` |
| N11 | 🟢 Low | L5 "extreme volatility" threshold (100) still hardcoded outside config | `layer5_engine.py:258` |
| N12 | 🟢 Low | `crash_score`/`black_swan_score` still unsanitized `int()` casts — pre-existing M4 remains unfixed | `packet_source.py:118,121` |

Not-new, still-open (recorded for completeness): `btc_above_structure_low` hardcoded True (`fetch_layer1.py:99`) — consistent with config `btc_structure_low_required: true` today, but brittle; L2/L3/L4 `entry_checklist` config flags still decorative; no pipeline tests.

---

## 6. Fix Verdict Summary

| Item | Claim | Verdict |
|---|---|---|
| C1 | Live USD/JPY delta + session counters persisted | ❌ Broken — state-format crash kills live pipeline; VIX counter off-by-threshold; BoJ still inert |
| H1 | Tranche = % of L2 bucket | ✅ Correct |
| H2 | NONE blocks entry | ✅ Correct |
| H3 | fetch_enriched provides L5 inputs | ⚠️ Partial — keys emitted, but CVD still resolves to 0/"N/A" live → momentum still neutral |
| H4 | accumulate→long + Rule 1c | ✅ Correct (untested) |
| H5 | ETF flows normalized | ⚠️ Partial — live correct, mock still raw units |
| M1 | L5 thresholds → config | ✅ Correct (19/19 parity) |
| M2 | Tail-risk scales reconciled | ✅ Correct |
| M3 | Density normalization | ❌ Broken — new AttributeError regression; gate fails open |
| M5 | Tranche fills persisted | ⚠️ Present but defeated by update_dashboard clobber |
| M6 | Loss-limit wired into sizing | ⚠️ Wired but functionally inert (0.0 hardcoded) |
| M7 | Capital/stops from config | ⚠️ Partial — sizing yes, L2 total_capital still hardcoded |
| M8 | Checklist order fixed | ✅ Correct |
| M9 | fetch_packet TTL cache | ✅ Correct (verified by probe) |
| M10 | Defensive risk_state_val | ✅ Correct for its path |

**Bottom line:** the suite is green and 9 fixes are genuinely correct, but the two highest-stakes fixes (C1 and M3) are wrong in production, and H3's core goal is unmet. **Do not promote this to a production state until N1/N2 (state-file contract), N3 (heatmap gate), and N4 (CVD plumbing) are fixed.** Recommended order: unify/version the state file writer contract → make fetch_layer1 tolerant of the legacy string → fix `_norm_density` call sites → read CVD from `packet.context` with a real fallback → add pipeline tests for all of the above.

*End of verification audit. No project files were modified (working tree verified clean after the pass).*

# Whale Audit — Redline BTC Engine

**Date:** 2026-02-16 (session)
**Scope:** `redline/` (all 10 modules), `scripts/` (8 files), `config.yaml`, `tests/` (64 tests), README cross-reference
**Method:** Read-only static review + empirical verification of suspected bugs (small Python probes, no files modified, no pipeline run)
**Test run:** `python3 -m pytest tests/ -v` → **64 passed, 0 failed** (0.49s)

---

## 0. Executive Summary

The engine is well-structured, testable, and the 64-test suite is green. The core architecture (5 layers + engine + conflict resolver + sizing) is sound, and config-driven thresholds are correctly read in most decision paths (L0 cycle/MVRV/ETF, L1 MSTR/US10Y/VIX thresholds, L1.5 TPs, L3 ADX gate, L4 bear trade-type restrictions, sizing multipliers).

However, the audit found **1 critical, 5 high, 10 medium, and ~15 low severity issues**. The most serious themes:

1. **Production data plumbing makes several risk controls inert** — Layer 1's live fetcher hardcodes the USD/JPY spike, BoJ flag, and session counters, so 2 of the 4 risk-OFF triggers and the "2 sessions" sustain requirements can never fire from live data.
2. **Layer 2 tranche math over-allocates** — tranches are computed as % of *total capital* (33% each) instead of % of the 40% L2 bucket; filling all three tranches deploys 100% of capital, not 40%.
3. **Layer 5's momentum signal is dead in the live pipeline** — `analyze_enriched()` reads `cvd_24h`/`taker_ratio_24h` which `fetch_enriched()` never provides → momentum is always "neutral".
4. **Conflict Rule 1 (L2 vs L4) is dead in the pipeline** — `daily_run.py` feeds `layer2_direction="accumulate"/"hold"` (positioning *action*) into the resolver, which only matches `"long"/"short"`. And L2↔L3 contradiction is never checked at all, despite "higher layer wins direction".
5. **Config is not the single source of truth it claims to be** — ~40 thresholds/multipliers/flags are hardcoded or dead (L0 skew/premium, L1 session keys, L1.5 SL buffer, L3/L4 checklist flags, all of L5, conflict multipliers, sizing caps).

No race conditions were found in the layer modules themselves (they are pure functions). The pipeline has a repeated-download consistency risk (each run fetches the full packet ~8–10 times) and `update_dashboard.py` does an unguarded auto-push on cron.

---

## 1. Test Suite Results

```
collected 64 items — 64 passed, 0 failed, 0.49s
```

| File | Tests | Result |
|---|---|---|
| test_conflicts.py | 5 | PASS |
| test_layer0.py | 8 | PASS |
| test_layer1.py | 8 | PASS |
| test_layer1_5.py | 4 | PASS |
| test_layer2.py | 9 | PASS |
| test_layer3.py | 9 | PASS |
| test_layer4.py | 8 | PASS |
| test_layer5.py | 3 | PASS |
| test_sizing.py | 7 | PASS |

**Coverage gaps (untested behaviors that the audit found buggy):**
- Heatmap gate (`assess_heatmap_gate`) — 0 tests; density-string matching and distance thresholds unverified.
- L6 checklist no-data path — 0 tests; the "unavailable ≠ fail" logic is contradicted by the code (M8).
- L4 with `direction=NONE` — 0 tests; currently returns `entry_allowed=True` (H3).
- L2 total deployment across all tranches — 0 tests; only "sums to 1.0" is asserted (H2).
- L2↔L3 contradiction — 0 tests (H5).
- `analyze_enriched`/`check_enriched_risk_signals` with "N/A" strings — 0 tests (M4).
- `scripts/` — **no tests at all**; every high-severity data-plumbing bug lives here.

---

## 2. Findings by Severity

### 🔴 CRITICAL

#### C1 — Layer 1 live fetcher hardcodes the fields that gate 2 of 4 risk-OFF triggers and all "sustained session" criteria
- Evidence: `scripts/fetch_layer1.py:30-44` — `usdjpy_change_pct: 0.0`, `boj_verbal_response: False`, `mstr_sessions_below: 0`, `vix_sessions_above: 0`, `usdjpy_stable_hours: 72`, `btc_above_structure_low: True` are all hardcoded constants in `fetch_live_data()`. Only MSTR close and US10Y (plus VIX level) come from real data.
- Consequence (verified against `redline/layer1_macro_risk.py:90,128-129`):
  - Trigger 2 (VIX) **can never fire live**: requires `vix_sessions_above >= 2` but the counter is always 0.
  - Trigger 4 (USD/JPY spike + BoJ) **can never fire live**: `usdjpy_change_pct` is always 0.0 (the USD/JPY *price* is fetched into `_usdjpy_price` but the delta is never computed).
  - Risk-ON criteria `mstr_above_2_sessions`, `vix_below_2_sessions`, `usdjpy_stable_48h`, `btc_above_structure_low` are **always True** in live runs (0 sessions, 72 stable hours, hardcoded True).
- Net effect: the live risk switch degrades to `MSTR < 75 OR US10Y > 4.60 → OFF` / `MSTR > 82 AND VIX < 22 AND US10Y < 4.55 → ON`. This is a **regulatory-grade safety gap** for the layer the README calls the "binary gate".
- Recommendation: compute USD/JPY session delta from `_usdjpy_price` vs prior close (persist in `.redline_state.json`), and persist/track `mstr_sessions_below` / `vix_sessions_above` / `usdjpy_stable_hours` across runs.

### 🟠 HIGH

#### H1 — Layer 2 tranches allocate % of TOTAL capital, not % of the 40% L2 bucket (over-allocation risk)
- Evidence: `redline/layer2_positioning.py:139-140` — `amount_usd = inputs.total_capital * tranche.allocation_pct` with `allocation_pct` = 0.33/0.33/0.34 (`config.yaml` layer2.bear_regime.accumulation_tranches). `scripts/daily_run.py:183` passes `total_capital=100_000` (full account).
- Verified: one tranche on $100K → **$33,000 = 33% of the whole account**. Filling all three tranches deploys $100K = 100% of capital.
- Documentation says otherwise: README sizing table — L2 max 40%, per tranche **13%** (0.33 × 0.40 = 13.2%); L1.5/L2/L3/L4 + reserve = 85% max deployed. The test `test_tranche_allocation_sums_to_one` (`tests/test_layer2.py:96-98`) codifies sum=1.0, confirming the tranche fractions were meant to be fractions of the 40% bucket.
- Recommendation: `amount_usd = total_capital * l2["allocation_pct"] * tranche.allocation_pct`, or pass the L2 sub-account as `total_capital`.

#### H2 — L4 `assess_intraday_trade` returns ALLOWED for direction=NONE
- Evidence: `redline/layer4_intraday.py:347-357` — `entry_allowed = checklist_passed and trade_type_allowed`; `inputs.direction` is never checked against NONE. `is_trade_type_allowed()` returns True for any non-LONG/SHORT direction in BEAR (`layer4_intraday.py:314-321`).
- Verified: `IntradayInputs(direction=NONE, all 7 checklist flags True, type_c, BEAR)` → `entry_allowed=True`.
- Live relevance: `fetch_intraday_signals()` returns `"NONE"` whenever neither TF is bearish and both aren't bullish — a common state — and `daily_run.py:232` maps unknown directions to `IntradayDirection.NONE` with trade type defaulting to `TYPE_C`.
- Recommendation: require `inputs.direction != IntradayDirection.NONE` in `entry_allowed`.

#### H3 — L5 momentum signal is dead in the live pipeline
- Evidence: `redline/layer5_engine.py:30-49` reads `enriched.get("cvd_24h", 0)` and `enriched.get("taker_ratio_24h", 1.0)`; `scripts/packet_source.py:60-113` (`fetch_enriched`) never emits `cvd_24h`, `taker_ratio_24h`, `vp_state`, or `oi_absolute_usd_billions` (verified by AST diff of consumed vs provided keys). Defaults: `cvd_24h=0 → momentum="neutral"` always; `vp_state → "unknown"` always; `oi_absolute_usd_billions → 0`.
- Consequence: in live runs the flagship "momentum" output of the analysis engine is a constant, and `taker_ratio_24h`/`vp_state` outputs are meaningless. Only mock runs exercise the real logic.
- Recommendation: either add these keys to `fetch_enriched()` (from `packet["enriched"]` or `packet["critical"]`) or remove them from `analyze_enriched`.

#### H4 — Conflict Rule 1 (higher layer wins direction: L2 vs L4) never fires in the pipeline; L2 vs L3 contradiction unchecked
- Evidence: `scripts/daily_run.py:431` — `l2_dir = report.get("positioning", {}).get("action", "neutral")` feeds `action` = `"accumulate"/"hold"/"none"` into `ConflictInput.layer2_direction`. `redline/conflict_resolver.py:95-108` only matches `layer2_direction in ("short","long")` → **Rule 1 is unreachable** with real pipeline values (verified: a LONG L4 vs L2 "accumulate" produced no Rule-1 reason; only Rule 1b fired because L3 was SHORT).
- Additionally, `resolve_conflicts` checks L2↔L4 and L3↔L4 but **never L2↔L3**, so a L3 LONG against an L2 short bias (the documented "higher layer wins direction" hierarchy, README "Conflict Resolution Rules" #1) passes unflagged.
- Recommendation: map positioning action → bias (`accumulate`/`hold` → "long" in bear accumulation context) and add an L2↔L3 direction conflict branch (downgrade/block with size cut).

#### H5 — ETF flow unit mismatch between fetcher and classifier thresholds
- Evidence: `scripts/fetch_layer0.py:57-58` passes `ctx.get("etf_flow_weekly", 0.0)` **raw** into `etf_flows_weekly`, while the same function's log divides by 1000 (`fetch_layer0.py:63`: `f"ETF={etf_weekly / 1000:.2f}B"`) and the mock value is `-9706.0` (i.e., packet units are **millions**). `config.yaml` thresholds are in **billions** (`layer0.regime.bear.etf_flow_weekly_min: -1.0`, `bull.etf_flow_weekly_min: 0.5`).
- Verified: `-500.0` (=-$0.5B, should be NEUTRAL per config band [-1.0, +0.5)) is classified as a bear signal because `-500 < -1.0`; any outflow >$1M magnitude trips the bear signal. Either the packet units or the `/1000` log are wrong — either way fetcher and classifier disagree.
- Recommendation: normalize once in `fetch_layer0` (divide by 1000) and store billions; add a unit test pinning the conversion.

### 🟡 MEDIUM

#### M1 — Config is not the "single source of truth" it claims to be (~40 hardcoded values / dead keys)
Verified hardcoded (not in config, or in config but never read):

| Location | Hardcoded value(s) |
|---|---|
| `redline/layer0_regime.py:115-123` | options skew ±5.0, coinbase premium ±0.5 (the `FALLBACK_DEFAULTS` at :19-26 is dead code — its own TODO admits "pending migration to config.yaml") |
| `redline/layer0_regime.py:132,143` | conviction_threshold 0.5 (BULL/BEAR) |
| `redline/layer1_macro_risk.py:128-129` | session criteria use `== 0`; config keys `mstr_above_sessions` / `vix_below_sessions` (config.yaml:38,40) **never read** (verified by grep) |
| `redline/layer1_5_macro_short.py:102` | SL buffer `1.02` (2%); config `stop_loss.above_trigger_level: true` is a dead boolean |
| `redline/layer3_swing.py:99-116` | config flags `require_major_support`, `cvd_positive`, `require_4h_1d_bearish`, `cvd_rolling` **never read** (conditions hardcoded; verified by grep) |
| `redline/layer4_intraday.py:259-276` | 7-item checklist hardcoded; `config.yaml` `entry_checklist` flags never read |
| `redline/layer5_engine.py` | CVD ±200 (:38-40), vol 80/50/20 (:54-60), OI 3.0/1.0 (:69-75), funding ±0.0005 (:78-82), FNG 15/35/55/75 (:92-99), corr ±0.7/±0.4 (:146-154), DXY 106 (:219), crash 3/4, black-swan 8/10 (:133-139, 213-220) |
| `redline/conflict_resolver.py:102-141` | size cuts 0.5/0.7/0.3 floor |
| `redline/checklist.py:136` | R:R ≥ 1.5 |
| `redline/sizing.py` | **leverage caps from config (`layer2` bear 1.0 / bull 2.0 / transitional 1.5) are never read or enforced**; README's L3 3x / L4 5x / L1.5 5x caps don't exist in config at all |

Design debt, not necessarily behavior bugs — but it defeats the stated config contract and makes tuning/backtesting impossible from config alone.

#### M2 — Inconsistent thresholds for the same signals inside layer5_engine
- `analyze_enriched` tail risk: black-swan ≥10 high / ≥5 elevated; crash ≥4 / ≥2 (`layer5_engine.py:133-139`).
- `check_enriched_risk_signals`: black-swan ≥8 elevated; crash ≥3 elevated (`layer5_engine.py:213-220`).
- Same underlying signals, two different scales in one module → a crash_score of 3 is "elevated" in one function and "low" in the other.
- ADX used inconsistently across layers: L3 blocks ≥35 (`layer3_swing.py:86`, config), L4 trade type A >35 / B ≥20 (`fetch_intraday_signals.py:63-65`), L4 `adx_direction` >25 (:71). Not wrong per se (different purposes), but duplicated magic numbers.

#### M3 — L4 heatmap gate: fragile string matching + hardcoded geometry
- `redline/layer4_intraday.py:169-201` — `density in ("Dense 🔥",)` depends on the exact emoji string from the packet; "Moderate"/"Scattered" must match byte-for-byte. Distance cutoffs 2.0%/1.0%/0.5%, staleness 15/60 min, vice-grip $500 all hardcoded (docs at :116-119 describe them as GetClaw rules).
- `HeatmapGateInput.current_price` (`layer4_intraday.py:98`) is never used by the gate (distances are precomputed in the packet).
- No tests exist for this function.

#### M4 — Unsanitized packet values can crash L5 / L1 (silently, via daily_run try/except)
- `scripts/packet_source.py:66-68` — `int(enriched_pkt.get("crash_score", 0))` raises `ValueError` on `"N/A"` (which the packet demonstrably uses for other fields, e.g. `vix` default `"N/A"`).
- `redline/layer5_engine.py:104-113` — `sr_1d_support`/`sr_1h_support` pass through unsanitized; a `"N/A"` string is truthy → `nearest_support="N/A"` → `(btc_price - "N/A")` → `TypeError`, killing the whole `analyze_enriched` (wrapped, so it degrades, but the L5 section silently vanishes).
- `scripts/fetch_layer1.py:28-29` — `vix`/`us10y` unsanitized (compare `_safe_float` used elsewhere in the same file at :50-56 and in `fetch_layer0.py:44-52`).
- Inconsistent sanitization strategy across fetchers.

#### M5 — No state persistence: L2 tranches re-trigger every day
- `scripts/daily_run.py:186` always passes `tranches_filled=[]`; `.redline_state.json` stores only `l1_state` + `enriched_risk_level` (`scripts/update_dashboard.py:113`). While price sits in a tranche range, every daily run re-recommends the same "ACCUMULATE $33K" — an operator acting daily over-allocates (compounds H1).
- Same gap applies to C1's session counters and `layer4_pnl_pct` (M6): nothing persists intra-run state.

#### M6 — Capital isolation (Rule 5) and escalation (Rule 4) are never enforced in the pipeline
- `scripts/daily_run.py:443` hardcodes `layer4_pnl_pct=0.0` → conflict Rule 4 (losing L4 must meet L3 criteria) is inert; the pipeline has no position/P&L tracking at all.
- `check_loss_limit` (`redline/sizing.py:119-157`) and `check_capital_isolation` (`redline/conflict_resolver.py:160-192`) are **never called** by `daily_run.py` — the daily loss limits in `config.yaml` (`sizing.loss_limits`) are dead configuration in the live flow, despite README rule #5 "capital isolation… enforced by the sizing layer" (`conflict_resolver.py:146`).
- The two functions are exact duplicates of each other — drift risk.

#### M7 — daily_run hardcodes capital and uses one stop distance for both L3 and L4
- `scripts/daily_run.py:183,484` — `total_capital` / `account_balance = 100_000` (not config).
- `scripts/daily_run.py:479` — `stop_loss_price = btc_price * 1.03/0.97` for **both** L3 and L4. A 3% stop is far too wide for L4 intraday/scalps (the 0.5 layer multiplier implies ~0.5–1% risk per trade); position size and leverage outputs are therefore distorted for L4.
- The single `size_mult` from conflict resolution (`daily_run.py:476`) is applied to **both** L3 and L4 sizing, though conflicts are L4-centric.

#### M8 — L6 heatmap checklist contradicts its own "no data is not a fail" comment
- `redline/checklist.py:193-200` — the "unavailable is not a fail" branch only clears `heatmap_data_available` when it is the *only* failed item. The standard no-data combination is `data_available=False` **and** `requires_manual_review=True` (as produced by `assess_heatmap_gate` no-data path, `layer4_intraday.py:126-134`) → the checklist fails. Comment says "NOT a fail — it's a warning"; code fails it.

#### M9 — Repeated full-packet downloads per run; no caching → stale-data inconsistency
- A single `daily_run.py` execution triggers ~8–10 `fetch_packet()` HTTP downloads (fetch_layer0 + fetch_brk + fetch_layer1 + fetch_data_packet + fetch_swing_signals (2) + fetch_intraday_signals + fetch_enriched at L1 stage (`daily_run.py:129`) + fetch_enriched again at L5 stage (`daily_run.py:384`) + fetch_heatmap). Each returns the full aggregated JSON.
- The two `fetch_enriched()` calls can return **different snapshots** — L1's enriched-risk override and L5's analysis may disagree in the same report. Recommend fetch-once + pass through.

#### M10 — If Layer 1 raises, the summary builder raises NameError and the run is marked FAILED
- `scripts/daily_run.py:113-118` — the L1 except block never assigns `risk_state_val` (unlike L0's `regime_val = "TRANSITIONAL"` fallback at :104). The summary builder at :517 references `risk_state_val` → `NameError` → caught → `overall_status="FAILED"` with a misleading reason, even if everything else succeeded.

### 🟢 LOW (consolidated)

- **L0 docstring stale** — `layer0_regime.py:37-39` documents AND-based classification ("BULL: Cycle ≥ X AND MVRV-Z ≥ Y AND ETF positive"); code is vote-based (3-of-5). `total_signals = 5` (:94) must be updated manually if signals are added. `fetch_layer0.py:54` reads `options_skew_25d` but labels it `options_skew_30d`.
- **L1 reactivation weaker than documented** — `mstr_above_2_sessions` is implemented as `mstr_sessions_below == 0` (`layer1_macro_risk.py:128`), i.e. "never dipped below 75", not "above $82 for 2 sessions" as README/config claim; `btc_structure_low_required` is a bool-equality against the trigger field (`:132`).
- **L1 `assess_macro_risk` field inconsistency** — ON-state branch returns `reactivation_criteria_met={}` when `can_reactivate` is True but the full dict when False (`layer1_macro_risk.py:176-183`).
- **L1.5 inactive output uses `stop_loss=0.0`** (`layer1_5_macro_short.py:88-97`) — consumers may read 0.0 as "no stop"; also no validation that `trigger_event_level > btc_price` (SL below entry would be a long-stop on a short).
- **L5 `liquidation_risk` mislabeled** — `bool(nearest_support or nearest_resistance)` (`layer5_engine.py:119`) is "near S/R level", not liquidation risk. `fng_value` output reverts to the raw string for non-numeric input (:176) — type instability vs the numeric path.
- **L2 conflict semantics** — `check_leverage_allowed` returns True for any regime whose `leverage_max > 1.0`; bear 1.0/transitional 1.5 are consistent, but the README's L2 "1x only" is only true in bear.
- **Sizing edge cases** — `sizing.py:106-113`: negative `entry_price` yields a negative position size; leverage is reported but never clamped to layer/regime caps (see M1); the zero-diff guard is good.
- **fetch_intraday direction bias** — any bearishness on 1D *or* 4H → SHORT; LONG requires both bullish (`fetch_intraday_signals.py:44-56`); `mtf_alignment` is True whenever 4H is non-neutral even if 1D disagrees (:74), contradicting the "2 of 3 agree" comment.
- **fetch_swing_signals heuristics** — `daily_sr_level` depends on literal `"ZONE_MISS"/"ZONE_HIT"` substrings and `BALANCE` in `balance_state` (:46-51); `at_major_support` regex-parses `liq_clusters` with a hardcoded 0.5% window (:71-80). Both silently degrade to neutral/False on format drift.
- **update_dashboard** — `subprocess.run([... "&&" ...], shell=True)` (:98-103) is fragile; auto `git add/commit/push` on cron with no lock can race a manual run writing `docs/redline_report.json`; the `_send_tg_alert` external bridge path is unvalidated.
- **README / config drift** — README says "Layer 1: Risk ON", config `current_state.layer1_risk` says "OFF", `.redline_state.json` says `l1_state: "OFF"`. `config.yaml`'s "Current State (updated by fetch scripts)" comment (config.yaml:148) is false — nothing writes it.
- **Test-suite blind spots** — see §1; notably zero coverage of `scripts/` where all critical/high bugs live.

---

## 3. Layer-by-Layer Verdict

| Layer | Verdict | Notes |
|---|---|---|
| L0 Regime | ✅ Logic sound, config-matched | Vote math correct; dead-zone bands match `transitional` ranges in config. Hardcoded skew/premium + ETF unit bug (H5). |
| L1 Risk Switch | ⚠️ Safety gap | Thresholds correct in code, but live data makes VIX & USD/JPY triggers and session criteria inert (C1). Sanitization gap (M4). |
| L1.5 Macro Short | ✅ Logic sound | Correctly gated on Risk OFF + below structure; TPs from config. SL buffer hardcoded 2% (M1). |
| L2 Positioning | ⚠️ Over-allocation | Tranche math = % of total capital, not 40% bucket (H1); no fill persistence (M5). |
| L3 Swing | ✅ Logic sound | Gates match docs/config (ADX<35, S/R, bear long/short rules); config flags decorative (M1). |
| L4 Intraday | ⚠️ Signal integrity | NONE-direction passes (H2); heatmap gate untested & string-fragile (M3); checklist config dead (M1). |
| L5 Engine | ⚠️ Dead signals | Momentum/vp/OI constants in live runs (H3); "N/A" crash risk (M4); inconsistent tail-risk scales (M2). |
| Conflict Resolver | ⚠️ Partially dead | Rules 1b/2/3/4 tested & correct; Rule 1 unreachable in pipeline, L2↔L3 never checked (H4); Rule 5 never invoked (M6). |
| Sizing | ✅ Formula correct | Risk math, cap, zero-diff guard all good; leverage caps unenforced (M1), hardcoded capital/stop in caller (M7). |
| daily_run | ⚠️ Plumbing debt | Per-layer try/except is good; but hardcoded values, double-fetch, NameError cascade (M9/M10). |

---

## 4. Top Recommended Fix Order

1. **C1** — Track & persist L1 session counters, USD/JPY delta, BoJ flag; stop hardcoding them.
2. **H1** — Scale tranche amounts by the 40% L2 allocation.
3. **H2** — Block `direction=NONE` in L4 entry logic.
4. **H3** — Wire `cvd_24h`/`taker_ratio_24h`/`vp_state` through `fetch_enriched`.
5. **H4** — Map positioning action → direction bias; add L2↔L3 conflict branch.
6. **H5** — Normalize ETF flow units in `fetch_layer0`.
7. **M1/M2** — Migrate the hardcoded threshold table to config (or at least to module-level constants) and reconcile the two tail-risk scales.
8. **M5/M6** — Extend `.redline_state.json` (tranche fills, session counters, daily P&L) and call `check_loss_limit` in the sizing step.
9. Add pipeline tests (`tests/` currently covers `redline/` only) and heatmap-gate/L6-checklist tests.

---

## 5. What Was Verified as Correct

- Config thresholds correctly drive: L0 cycle/MVRV/ETF bands; L1 MSTR/VIX/US10Y/USDJPY trigger levels; L1.5 TP targets; L3 `adx_below`; L4 bear long restrictions; sizing `base_risk_pct`, layer multipliers, regime adjustments, loss limits, `max_position_size_usd`.
- L1.5 correctly refuses activation when Risk ON or BTC above structure; `should_close_normal_ops` is right.
- L3's `entry_allowed` correctly ANDs structure + S/R + ADX + direction + zero reasons.
- Conflict resolver: rule ordering, the BLOCK guard, and the 0.3 floor behave as tested; downgrade reasons are accurate.
- Sizing: `position_size = (risk / |entry−stop|) × entry` is arithmetically correct for both long and short (abs handles inverted stops); cap and zero-diff guard work; `risk_pct` is recomputed post-cap honestly.
- All 64 tests pass; layer modules are pure, deterministic functions (no shared mutable state, no race conditions inside the engine).

*End of audit. No project files were modified.*

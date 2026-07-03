# Redline BTC — Structured Trading Framework

A 5-layer BTC trading framework with inter-layer conflict resolution, designed for the current BEAR market regime.

## Architecture

```
Layer 0 — Market Regime Classifier    (daily)
  ↓
Layer 1 — Macro Risk Switch           (4-6h)
  ↓
Layer 1.5 — Macro Short Activation    (emergency, Risk OFF only)
  ↓
Layer 2 — Positioning                 (weekly)
  ↓
Layer 3 — Swing Trading               (daily, 2-10 day)
  ↓
Layer 4 — Intraday Trading            (real-time, hours)
```

**Layer 5 — Analysis Engine** feeds data upward but makes no decisions.

## Layer Summary

| Layer | Timeframe | Max Size | Purpose |
|-------|-----------|----------|---------|
| L0 | Daily | — | Classifies market: BULL/BEAR/TRANSITIONAL |
| L1 | 4-6h | — | Binary Risk ON/OFF gate (4 triggers) |
| L1.5 | Emergency | 15% | Macro short when Risk OFF |
| L2 | Weekly | 40% | Spot accumulation in tranches |
| L3 | 2-10 day | 20% | Swing trades on structure breaks |
| L4 | Real-time | 10% | Intraday scalps and mean reversion |

## Current State

**Regime:** BEAR MARKET (Cycle 25.2, MVRV-Z 0.25, ETF -$1B/week)
**Layer 1:** Risk ON (all 3 checkable triggers clear)

### BEAR Market Rules
- Short bias. Rallies are exits/shorts
- Intraday longs = scalps only, tight stops
- Layer 2: accumulate spot in tranches, 1x only

## Layer 1 — Macro Risk Switch

Risk OFF triggers (ANY 1 fires):
| # | Trigger | Level |
|---|---------|-------|
| 1 | MSTR daily close | < $75 |
| 2 | VIX sustained | > 25 |
| 3 | US10Y | > 4.60% |
| 4 | USD/JPY spike + BoJ | +2% single session |

Risk ON requires ALL 5 criteria to clear (MSTR > $82 for 2 sessions, VIX < 22 for 2 sessions, US10Y < 4.55%, USD/JPY stable 48h, BTC above 4H structure low).

## Sizing Template

| Layer | Max Capital | Per Trade/Tranche | Max Leverage |
|-------|-------------|-------------------|:------------:|
| L2 (Positioning) | 40% | 13% | 1x |
| L3 (Swing) | 20% | 10% | 3x |
| L4 (Intraday) | 10% | 5% | 5x |
| L1.5 (Macro Short) | 15% | — | 5x |
| Reserve | 15% | — | — |
| **Max deployed** | **85%** | | |

## Conflict Resolution Rules

1. **Direction:** Higher layer wins direction. Always.
2. **Size:** Lower layers use smaller size. Do not stack across layers.
3. **Contradiction:** If L4 contradicts L3 → Type C scalp only, no Type A.
4. **Escalation:** A losing L4 trade must meet L3 criteria to hold. Otherwise: stop out.
5. **Capital isolation:** Each layer has its own loss limit. A loss in one does not justify larger size elsewhere.

## Setup

```bash
cd ~/projects/redline-btc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Daily analysis with mock data
python scripts/daily_run.py --mock

# Daily analysis with live data
python scripts/daily_run.py

# Save report to file
python scripts/daily_run.py --output report.json

# Run tests
python -m pytest tests/
```

## Project Structure

```
redline-btc/
├── config.yaml              # All thresholds (single source of truth)
├── redline/
│   ├── layer0_regime.py     # Market regime classifier
│   ├── layer1_macro_risk.py # Macro risk switch
│   ├── layer1_5_macro_short.py  # Macro short activation
│   ├── layer2_positioning.py    # Positioning / spot accumulation
│   ├── layer3_swing.py      # Swing trading
│   ├── layer4_intraday.py   # Intraday trading
│   ├── layer5_engine.py     # Analysis engine
│   ├── conflict_resolver.py # Inter-layer conflict resolution
│   ├── sizing.py            # Position sizing calculator
│   └── checklist.py         # Pre/end-of-session checklists
├── scripts/
│   ├── fetch_layer0.py      # On-chain data fetcher
│   ├── fetch_layer1.py      # Macro trigger fetcher
│   ├── fetch_data_packet.py # BTC data packet fetcher
│   └── daily_run.py         # Full daily orchestrator
├── tests/                   # pytest test suite
└── data/                    # Runtime data
```

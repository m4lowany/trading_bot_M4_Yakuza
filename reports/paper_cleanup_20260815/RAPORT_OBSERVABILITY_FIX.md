# YAKUZA — Paper Observability Fix Report
**Date:** 2026-08-15  
**Scope:** DATA PIPELINE observability only  
**Status:** implemented, tests green, **not committed** (awaiting acceptance)

---

## What changed

| File | Change |
|------|--------|
| `main.py` | Passes `paper_confidence`, `paper_entry_quality`, `paper_source` into `save_setup_snapshot` |
| `setup_stats.py` | Persists `paper_*` on every snapshot; enrichment attaches `paper_*` + `snapshot_signal_*` **without** overwriting `trade.confidence` / `trade.entry_quality` |
| `setup_engine.py` | Docstring only — documents dual-path / NO_SETUP passthrough / WAIT boost (no logic change) |
| `ARCHITECTURE.md` | Dual-path snapshot field table + analytics note |
| `test_paper_observability.py` | **new** regression suite |

## What did NOT change
scoring, signals, setup conditions, structure_confluence, risk_manager, leverage, entry/exit, TP/SL, NO_SETUP gate behavior.

## Tests run (all passed)
```
python3 test_paper_observability.py
python3 test_structure_events_snapshot.py
python3 test_structure_confluence.py
python3 test_structure_events_leg.py
```

Coverage in `test_paper_observability.py`:
1. NO_SETUP passthrough → `paper_source=signal`, paper_* == signal_*
2. WAIT + MEDIUM setup boost → `0/LOW → 3/MEDIUM`
3. Snapshot persistence of diverging `paper_*` vs `signal_*`
4. Enrichment does not clobber `trade.confidence`
5. Legacy snapshots without `paper_*` stay safe (`UNKNOWN` + reason inference)

## Diff summary
```
ARCHITECTURE.md | 14 ++++++++++
main.py         |  3 +++
setup_engine.py | 21 (docstring)
setup_stats.py  | 72 +++++++
+ test_paper_observability.py (new)
```

## Next step after accept
1. Commit / push (on request)
2. Restart paper bot → **RUN → COLLECT NEW DATA → ANALYZE**
3. New `setup_history.jsonl` rows will include `paper_confidence` / `paper_entry_quality` / `paper_source`
4. Analyze NEW cohort using `paper_*` (or trade.confidence), never raw `signal_confidence` for setup_engine opens

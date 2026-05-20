# Architecture — trading_bot_yakuza

Dokument techniczny dla deweloperów i agentów AI. Opisuje **jak działa kod**, nie strategię handlową (patrz `notes/yakuza_strategy_core.md`).

**Status execution:** analityka + paper trading. **Brak realnych zleceń** na MEXC.

---

## Cel systemu

Modularny silnik decyzyjny BTC/USDT (spot, MEXC, ccxt):

1. Pobiera dane OHLCV na wielu timeframe'ach.
2. Liczy wskaźniki, strukturę, price action.
3. Emituje `SIGNAL` (BUY/SELL/WAIT) + jakość wejścia.
4. Klasyfikuje setup (Yakuza-style).
5. Symuluje pozycje (paper).
6. Loguje snapshoty do analizy edge.

---

## Moduły (mapa plików)

| Moduł | Plik | Odpowiedzialność |
|-------|------|------------------|
| Entry point | `main.py` | Pętla, fetch, integracja, print, logi plikowe |
| Config | `config.py` | Symbol, TF, wskaźniki, `LOOP_DELAY`, progi |
| Utils | `utils.py` | Walidacja TF i świec OHLCV |
| Indicators | `indicators.py` | MA60, EMA238, RSI, FVG; stuby BAG, FIBO |
| Market structure | `market_structure.py` | HH/HL/LH/LL, momentum, liquidity_event |
| Price action | `price_action.py` | Świeca, knoty, fake breakout, S/R, momentum shift |
| MTF | `timeframe_analysis.py` | Per-TF analiza, alignment, filtr końcowy |
| Scoring | `scoring.py` | Score, confidence 0–5, entry_quality |
| Signals | `signals.py` | Próg ±3 → BUY/SELL/WAIT |
| Setup engine | `setup_engine.py` | Typ setupu, kierunek, quality, paper override |
| Risk | `risk_manager.py` | can_trade, dynamic leverage, target profit % |
| Paper | `paper_trader.py` | Open/close symulacji, TP/SL, cooldown |
| Stats | `setup_stats.py` | `save_setup_snapshot`, `generate_stats` |
| Report | `stats_report.py` | CLI raportu z `logs/` |
| Observer | `structure_events.py` | BOS, CHoCH, control shift — **tylko obserwacja** |

Testy pomocnicze (nie część runtime bota): `test_structure_events_snapshot.py`.

---

## Flow danych (jedna iteracja)

```
┌─────────────┐
│  ccxt.mexc  │ fetch_ticker + fetch_ohlcv × 3 TF
└──────┬──────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│ analyze_timeframe() × 3  (30m, 15m, 5m)                   │
│   → indicators + market_structure → signal per TF        │
└──────┬───────────────────────────────────────────────────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│ Entry 5m: price_action + score + confidence              │
│ analyze_timeframe_alignment() + apply_alignment_*        │
│   → SIGNAL, entry_quality, trade_allowed (legacy)        │
└──────┬───────────────────────────────────────────────────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│ setup_engine.detect_setup()                              │
│ resolve_paper_from_setup() → paper_signal, paper_*     │
└──────┬───────────────────────────────────────────────────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│ risk_manager.calculate_dynamic_leverage()                │
│ paper_trader.process_paper_trading()                     │
└──────┬───────────────────────────────────────────────────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│ Observer (po decyzjach tradingowych):                    │
│   structure_events.analyze_structure_events(entry 5m)    │
│   setup_stats.save_setup_snapshot() → setup_history.jsonl│
└──────────────────────────────────────────────────────────┘
```

**Ważne:** `structure_events` jest wywoływane **po** paper — nie uczestniczy w `SIGNAL` ani `paper_signal`.

---

## MTF flow

| Rola | TF (config) | Funkcja |
|------|-------------|---------|
| Trend | `30m` | Bias / kontekst wyższego TF |
| Confirm | `15m` | Potwierdzenie, nie musi = BUY/SELL |
| Entry | `5m` | Timing, PA, FVG, score końcowy |

### Alignment (`timeframe_analysis.py`)

- `FULL_BULLISH` / `FULL_BEARISH` — wszystkie TF: BUY lub SELL (nie WAIT).
- `MIXED` — rozbieżność.

### Filtr końcowy (legacy)

- `MIXED` → `SIGNAL = WAIT`, `trade_allowed = False`.
- `FULL_BULLISH` → tylko BUY; `FULL_BEARISH` → tylko SELL.

### setup_engine (warstwa nad MTF)

- Nie wymaga 3× identycznego sygnału.
- `TREND_CONTINUATION` — 30m+15m zgodne + trigger na 5m.
- `PULLBACK_ENTRY` — MIXED, ale pullback zgodny z biasem.
- `REVERSAL_ATTEMPT` — reversal_chance + trigger przeciw trendowi.
- `resolve_paper_from_setup()` — przy `SIGNAL==WAIT` może ustawić `paper_signal` (MEDIUM/HIGH).

---

## setup_engine

**Wejście:** `trend_tf`, `confirm_tf`, `entry_tf` (wynik `analyze_timeframe`), `price_action`, `fvg`.

**Wyjście:**

```python
{
  "setup_type": "TREND_CONTINUATION" | "PULLBACK_ENTRY" | "REVERSAL_ATTEMPT" | "NO_SETUP",
  "setup_direction": "BUY" | "SELL" | "WAIT",
  "setup_quality": "LOW" | "MEDIUM" | "HIGH",
  "setup_reasons": list[str],
  # opcjonalnie po karze:
  "setup_confidence_penalty": int,
}
```

### Soft filter: sideways continuation penalty

Gdy jednocześnie:

- `setup_type == TREND_CONTINUATION`
- entry `structure == SIDEWAYS` i `structure_strength == WEAK`

→ reason `sideways continuation penalty`, HIGH→MEDIUM, `setup_confidence_penalty += 1`.  
**Bez** hard block. Nie dotyczy PULLBACK ani REVERSAL.

---

## paper_trader

Symulacja pozycji w `logs/paper_trades.json`:

| Reguła | Zachowanie |
|--------|------------|
| Open | `paper_signal` ≠ WAIT, quality ≠ LOW, confidence ≥ 3, brak active |
| Close natychmiast | TP hit, SL hit, opposite signal |
| MIXED | Warning 2 iter., close po 3. kolejnej z rzędu |
| Cooldown | 3 iteracje bez open po close |

Używa `paper_signal` z `main` (może pochodzić z setup_engine).

---

## Observer layer — structure_events

**Cel:** czysta PA (BOS, CHoCH, przejęcie kontroli) bez nowych wskaźników.

**Zasada:** OBSERVER ONLY — nie importowany przez scoring/setup_engine/paper do decyzji.

**Wyjście** (`analyze_structure_events(candles)`):

- `bos`, `choch`, `last_swing_high/low`, `broken_level`
- `buyers_take_control`, `sellers_take_control`, `control_shift`
- `event_strength`, `event_reasons`

**Integracja:** `main.py` → print + `save_setup_snapshot(structure_events=...)`.

Mapowanie pól JSONL: `setup_stats.structure_event_snapshot_fields()`.

---

## setup_stats i logi

| Plik | Zawartość |
|------|-----------|
| `logs/setup_history.jsonl` | 1 JSON / iteracja (snapshot) |
| `logs/paper_trades.json` | active_trade, history, cooldown |
| `logs/market_log.txt` | Pełny tekst iteracji (ENABLE_LOGS) |
| `logs/signals_history.txt` | SIGNAL per iteracja |
| `logs/trend_history.txt` | trend label |

`stats_report.py` → `generate_stats("logs")` + formatowany raport (w tym structure events).

---

## Warstwy decyzyjne (podsumowanie)

| Warstwa | Decyduje o |
|---------|------------|
| Legacy SIGNAL | Konsola, alignment filter, część trade_allowed |
| setup_engine | setup_type, setup_quality, paper override |
| paper_trader | Faktyczny open/close symulacji |
| Observer | Tylko dane do analizy |

---

## Czego nie ma (świadomie)

- Real execution (market/limit na MEXC).
- FIBO / BAG (stuby w `indicators.py`).
- MTF 1D / 1H (docelowo w strategii; kod: 30m proxy).
- ML / modele predykcyjne.

---

## Zasady rozwoju

1. Nowa logika decyzyjna → osobny moduł lub rozszerzenie `setup_engine`, nie rozlewać po `main.py`.
2. Observery nie wpływają na SIGNAL bez explicit request + testów stats.
3. Zmiany scoring/signals/risk — osobny PR, uzasadnienie edge z `stats_report`.
4. `logs/` nigdy w git (`.gitignore`).

---

## Powiązane dokumenty

- `README.md` — uruchomienie, roadmapa
- `notes/yakuza_strategy_core.md` — filozofia strategii
- `PROMPT_LIBRARY.md` — prompty dla agentów
- `.cursor/rules/project_rules.md` — reguły pracy w repo

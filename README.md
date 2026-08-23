# trading_bot_yakuza

Modularny bot analityczny dla rynku krypto: **MEXC** + **ccxt**, para **BTC/USDT** (spot). Pobiera dane rynkowe, analizuje wiele timeframe'ów, strukturę rynku i price action, generuje sygnał **BUY / SELL / WAIT** z oceną jakości wejścia — **bez składania realnych zleceń** na giełdzie.

Strategia referencyjna: [`notes/yakuza_strategy_core.md`](notes/yakuza_strategy_core.md).

**Foundation (dev / AI):** [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`PROMPT_LIBRARY.md`](PROMPT_LIBRARY.md) · [`.cursor/rules/project_rules.md`](.cursor/rules/project_rules.md)

## Checkpoint architektury (stan projektu)

Modularny pipeline decyzyjny — **bez real execution** na giełdzie.

```
MEXC OHLCV
    → MTF 30m (trend) / 15m (confirm) / 5m (entry)
    → indicators + market_structure + price_action
    → scoring + signals + MTF alignment (legacy SIGNAL)
    → setup_engine (bias + trigger, setup_quality)
    → risk_manager (advisory)
    → paper_trader (symulacja TP/SL)
    → setup_stats → logs/setup_history.jsonl
    → structure_events (observer: log + snapshot only)
```

| Warstwa | Moduł | Rola |
|---------|--------|------|
| **MTF** | `timeframe_analysis.py` | 30m / 15m / 5m; alignment FULL_BULL/BEAR/MIXED |
| **Setup** | `setup_engine.py` | `TREND_CONTINUATION`, `PULLBACK_ENTRY`, `REVERSAL_ATTEMPT`; paper override przy WAIT |
| **Paper** | `paper_trader.py` | Symulacja; cooldown 3 iter.; MIXED → close po 3 iter. |
| **Stats** | `setup_stats.py`, `stats_report.py` | Snapshoty + raport edge (w tym structure events) |
| **Observer** | `structure_events.py` | BOS / CHoCH / control shift — **nie wpływa na SIGNAL** |
| **Soft filter** | `setup_engine.py` | `sideways continuation penalty` — entry SIDEWAYS+WEAK obniża quality continuation |

**Nie zaimplementowane:** realne zlecenia MEXC, FIBO/BAG (stuby), MTF docelowe 1D/1H.

## Architektura

| Plik | Rola |
|------|------|
| `main.py` | Główna pętla, integracja modułów, logowanie |
| `config.py` | Symbol, timeframe'y, lista wskaźników, parametry |
| `indicators.py` | MA60, EMA238, RSI, FVG (+ **stuby** BAG, FIBO) |
| `market_structure.py` | HH/HL/LH/LL, siła struktury, momentum, liquidity event |
| `structure_events.py` | BOS, CHoCH, swingi, przejęcie kontroli (czysta PA) |
| `price_action.py` | Siła świecy, knoty, fake breakout, S/R, momentum shift |
| `timeframe_analysis.py` | Analiza per-TF, MTF alignment, filtr końcowy |
| `setup_engine.py` | Klasyfikacja setupu: bias + trigger (TREND / PULLBACK / REVERSAL) |
| `scoring.py` | Score wskaźników, confidence (0–5), entry_quality |
| `signals.py` | Zamiana score na sygnał (próg ±3) |
| `risk_manager.py` | `can_trade`, dynamiczna dźwignia i target profit (advisory) |
| `paper_trader.py` | Symulacja pozycji: TP/SL, cooldown, MIXED warning |
| `setup_stats.py` | Snapshoty iteracji → `logs/setup_history.jsonl` |
| `stats_report.py` | Raport edge: `python3 stats_report.py` |
| `utils.py` | Walidacja timeframe'ów i świec OHLCV |

Przepływ: MEXC → MTF (30m / 15m / 5m) → scoring + alignment → `setup_engine` → risk → paper → logi / statystyki.

## Giełda i dane

- **Giełda:** MEXC (`ccxt.mexc()`)
- **Para:** `BTC/USDT` (spot)
- **Źródło:** ticker + świece OHLCV

## Multi-timeframe (MTF)

| Rola | Timeframe |
|------|-----------|
| Trend | `30m` |
| Confirm | `15m` |
| Entry | `5m` |

> Entry na `5m` — MEXC spot może nie wspierać `3m`. Docelowo strategia: 1D / 1H / 15m / 5m (patrz notes).

**MTF alignment** (`timeframe_analysis.py`):

- `FULL_BULLISH` / `FULL_BEARISH` — wszystkie TF zgodne
- `MIXED` — rozbieżność; legacy filtr wymusza `WAIT` na głównym `SIGNAL`

**setup_engine** (`setup_engine.py`) — warstwa nad alignment:

- `TREND_CONTINUATION`, `PULLBACK_ENTRY`, `REVERSAL_ATTEMPT`, `NO_SETUP`
- Może zasugerować `paper_signal` przy `SIGNAL == WAIT` (quality MEDIUM/HIGH)
- **Sideways continuation penalty** (soft): entry `SIDEWAYS` + `WEAK` + `TREND_CONTINUATION` → obniżona `setup_quality`, reason `sideways continuation penalty`, bez hard block

## Wskaźniki

| Wskaźnik | Status | Opis |
|----------|--------|------|
| **MA60** | Gotowy | SMA(60), cena vs MA |
| **EMA238** | Gotowy | EMA(238), bias kierunku |
| **RSI** | Gotowy | RSI(14), pomocniczo (<30 / >70) |
| **FVG** | Gotowy | Fair Value Gap, touch, rejection |
| **BAG** | **Stub** | Zawsze `WAIT` — planowane jako confluence |
| **FIBO** | **Stub** | Zawsze `WAIT` — planowane jako confluence |

RSI jest pomocniczy; główny kierunek: **świece, struktura, PA** (zgodnie ze strategią Yakuza).

## Structure events (`structure_events.py`)

Analiza wyłącznie ze świec (entry TF w `main.py` — log + snapshot):

- **BOS** — kontynuacja struktury (wybicie swing high/low + zamknięcie)
- **CHoCH** — zmiana charakteru (wybicie LH w downtrend / HL w uptrend)
- **buyers_take_control** / **sellers_take_control** — przejęcie kontroli po świecy przeciwnej
- `event_strength`: LOW / MEDIUM / HIGH

*Nie wpływa jeszcze na scoring ani setup_engine — tylko obserwacja i logi.*

## Paper trading

Moduł `paper_trader.py` — **symulacja**, bez realnych zleceń:

- Otwarcie: `paper_signal`, quality ≠ LOW, confidence ≥ 3, `trade_allowed`
- Zamknięcie: TP, SL, opposite signal
- `MIXED` alignment: warning → zamknięcie po 3 kolejnych iteracjach
- Cooldown: 3 iteracje bez nowego open po close
- Stan: `logs/paper_trades.json`

## Statystyki setupów

```bash
python3 stats_report.py
```

- Czyta `logs/setup_history.jsonl` + `logs/paper_trades.json`
- Win rate, breakdown po setup_type / quality / alignment / structure events (BOS, CHoCH, control shift, krzyżówki)

## Risk manager

Tylko rekomendacje (bez execution): dźwignia 1–20, target profit % wg zmienności.

## Status execution

| Funkcja | Status |
|---------|--------|
| Analityka + sygnały | Działa |
| Paper trading | Działa |
| Realne zlecenia MEXC | **Nie istnieje** |

## Logi

Przy `ENABLE_LOGS = True`:

- `logs/market_log.txt`
- `logs/signals_history.txt`
- `logs/trend_history.txt`
- `logs/setup_history.jsonl` (snapshoty z `setup_stats`)
- `logs/paper_trades.json`

Katalog `logs/` w `.gitignore`.

## Uruchamianie

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

## Roadmapa

- [x] Paper trading (symulacja)
- [x] setup_engine (bias + trigger)
- [x] setup_stats / stats_report
- [x] structure_events.py (observer — log + snapshot)
- [x] sideways continuation soft penalty
- [ ] Integracja structure_events → scoring / setup_engine
- [ ] **FIBO** jako confluence (nie główny trigger)
- [ ] **BAG** jako confluence
- [ ] MTF **1D / 1H** bias (zamiast proxy 30m)
- [ ] Walidacja edge na paper stats (min. próbka tradów)
- [ ] **Execution** — realne zlecenia MEXC — **dopiero po stabilnym paper**

- [ ] Integracja alertów TradingView (opcjonalnie)

## Runtime V1 (local paper process)

Safe start/stop/status/logs wrappers — **no strategy changes**. Do not run two `main.py` instances.

```bash
./scripts/start_bot.sh    # refuses if already running
./scripts/status_bot.sh
./scripts/logs_bot.sh     # Ctrl+C = stop tail only
./scripts/stop_bot.sh     # verifies cmdline/cwd; use --force only for manual starts
```

- Managed log: `logs/runs/live_run.log` · PID file: `logs/runs/yakuza_paper.pid`
- Legacy manual log (if used): `live_run.log` at repo root

## Dokumentacja strategii

- [`notes/yakuza_strategy_core.md`](notes/yakuza_strategy_core.md) — pełna filozofia Yakuza, TF docelowe, ryzyko, czego unikać.

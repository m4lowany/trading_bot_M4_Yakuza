# trading_bot_yakuza

Modularny bot analityczny dla rynku krypto: **MEXC** + **ccxt**, para **BTC/USDT** (spot). Pobiera dane rynkowe, analizuje wiele timeframe'ów, liczy wskaźniki i strukturę rynku, generuje sygnał **BUY / SELL / WAIT** z oceną jakości wejścia i ryzyka — **bez składania realnych zleceń** na giełdzie.

## Architektura

Projekt jest podzielony na niezależne moduły:

| Plik | Rola |
|------|------|
| `main.py` | Główna pętla, integracja modułów, logowanie |
| `config.py` | Symbol, timeframe'y, lista wskaźników, parametry |
| `indicators.py` | MA60, EMA238, RSI, FVG (+ stuby BAG, FIBO) |
| `market_structure.py` | HH/HL/LH/LL, siła struktury, momentum, liquidity event |
| `price_action.py` | Siła świecy, knoty, fake breakout, S/R, momentum shift |
| `timeframe_analysis.py` | Analiza per-TF, **MTF alignment**, filtr końcowy |
| `scoring.py` | Score wskaźników, **confidence** (0–5), **entry_quality** |
| `signals.py` | Zamiana score na sygnał (próg ±3) |
| `risk_manager.py` | `can_trade`, dynamiczna dźwignia i target profit (advisory) |
| `utils.py` | Walidacja timeframe'ów i świec OHLCV |

Przepływ: dane z MEXC → analiza na 3 TF → alignment → price action na entry → confidence → risk → stdout + logi.

## Giełda i dane

- **Giełda:** MEXC (`ccxt.mexc()`)
- **Para:** `BTC/USDT` (spot)
- **Źródło:** ticker + świece OHLCV (`fetch_ticker`, `fetch_ohlcv`)

## Multi-timeframe (MTF)

Domyślne interwały w `config.py`:

| Rola | Timeframe |
|------|-----------|
| Trend | `30m` |
| Confirm | `15m` |
| Entry | `5m` |

> Entry ustawione na `5m`, bo MEXC spot może nie wspierać `3m` (komentarz w `config.py`).

**MTF alignment** (`timeframe_analysis.py`):

- `FULL_BULLISH` — wszystkie TF sygnalizują BUY
- `FULL_BEARISH` — wszystkie TF sygnalizują SELL
- `MIXED` — rozbieżność TF → sygnał wymuszony na **WAIT**, trade zablokowany

Filtr końcowy blokuje SELL przy pełnym byku i BUY przy pełnym niedźwiedziu.

## Wskaźniki

| Wskaźnik | Status | Opis |
|----------|--------|------|
| **MA60** | Gotowy | SMA(60), cena vs MA → BUY/SELL/WAIT |
| **EMA238** | Gotowy | EMA(238), cena vs EMA |
| **RSI** | Gotowy | RSI(14), <30 BUY, >70 SELL |
| **FVG** | Gotowy | Fair Value Gap: typ, rozmiar luki, touch, rejection |
| **BAG** | Stub | Zawsze `WAIT` — do implementacji |
| **FIBO** | Stub | Zawsze `WAIT` — do implementacji |

## Market structure

Moduł `market_structure.py`:

- Struktura: **BULLISH** / **BEARISH** / **SIDEWAYS** (HH, HL, LH, LL)
- Siła struktury: WEAK / MEDIUM / STRONG
- Momentum, szansa kontynuacji / odwrócenia
- **liquidity_event** — twarda blokada wejścia w `main.py`

## Price action

Moduł `price_action.py` (na świecach entry TF):

- Siła świecy, odrzucenie knotem (wick rejection)
- Fake breakout, reakcja na support/resistance
- Momentum shift

Wyniki wpływają na **confidence** w `scoring.py`.

## Scoring i sygnał

- **Score:** statusy wskaźników (`BUY`/`BULLISH` +1, `SELL`/`BEARISH` -1) + bonusy FVG rejection i mocnej struktury
- **Sygnał** (`signals.py`): `score >= 3` → BUY, `score <= -3` → SELL, inaczej WAIT
- **Confidence** (0–5): jakość setupu (struktura, momentum, PA, FVG, alignment)
- **entry_quality:** LOW / MEDIUM / HIGH

## Risk manager

Moduł `risk_manager.py` (tylko rekomendacje, bez execution):

- `can_trade(signal)` — False dla WAIT
- `calculate_dynamic_leverage()` — dźwignia 1–20 i target profit % wg zmienności i poziomu ryzyka
- W `main.py`: `trade_allowed` łączy sygnał, alignment, liquidity event i fake breakout

## Status tradingu

Bot **nie otwiera pozycji** i **nie wysyła zleceń** na MEXC. Działa jako silnik analityczno-decyzyjny + logger.

## Logi

Przy `ENABLE_LOGS = True` (domyślnie):

- `logs/market_log.txt` — pełny snapshot iteracji
- `logs/signals_history.txt` — historia sygnałów
- `logs/trend_history.txt` — historia trendu (alignment)

Katalog `logs/` jest w `.gitignore`.

## Uruchamianie

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Wymagania: Python 3, pakiet `ccxt` (patrz `requirements.txt`).

## Roadmapa

- [ ] Implementacja **FIBO**
- [ ] Implementacja **BAG**
- [ ] **Paper trading** (symulacja pozycji bez realnych środków)
- [ ] Integracja alertów **TradingView**
- [ ] **Execution** — realne zlecenia MEXC (market/limit + obsługa pozycji)

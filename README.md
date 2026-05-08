# trading_bot_yakuza

## Co to jest
`trading_bot_yakuza` to modularny bot tradingowy dla rynku krypto (MEXC, para `BTC/USDT`) z architekturą opartą o wskaźniki, scoring i generator sygnału.

## Co działa teraz
- Pobieranie ceny `BTC/USDT` przez `ccxt`.
- Pobieranie świec `OHLCV` dla wskaźników.
- Obliczanie i statusy wskaźników:
  - `RSI(14)` na `CONFIRM_TIMEFRAME`
  - `EMA(238)` na `TREND_TIMEFRAME`
  - `MA/SMA(60)` na `TREND_TIMEFRAME`
- Budowa `indicator_status` jako słownika statusów wskaźników.
- Scoring statusów (`BUY/BULLISH` = `+1`, `SELL/BEARISH` = `-1`, reszta `0`).
- Generowanie sygnału z progu punktowego (`BUY`, `SELL`, `WAIT`).
- Logowanie danych do `logs/market_log.txt`, `logs/signals_history.txt`, `logs/trend_history.txt`.

## Struktura plików
- `main.py` - główna pętla bota, logowanie, integracja modułów.
- `config.py` - konfiguracja symbolu, timeframe'ów i listy wskaźników.
- `indicators.py` - obliczenia wskaźników i agregacja `get_all_indicators()`.
- `scoring.py` - punktacja statusów wskaźników.
- `signals.py` - zamiana punktacji na sygnał transakcyjny.
- `risk_manager.py` - warstwa walidacji wejścia (kontrola możliwości trade).

## Aktualne wskaźniki
- `RSI`
- `EMA238`
- `MA60`

## Aktualny status tradingu
Bot **na razie nie otwiera pozycji** i nie wysyła zleceń na giełdę. Obecna wersja działa jako silnik analityczno-decyzyjny + logger.

## Roadmapa
- Implementacja `FVG`.
- Implementacja `FIBO`.
- Integracja alertów z TradingView.
- Tryb paper trading.
- Realne zlecenia `MEXC` (market/limit + obsługa pozycji).

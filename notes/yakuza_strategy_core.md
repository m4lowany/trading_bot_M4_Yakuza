# Yakuza Strategy Core

Dokument referencyjny strategii **Yakuza** dla bota `trading_bot_yakuza`.  
Opisuje **docelową logikę decyzyjną** (jak trader), nie implementację linia po linii.

> **Stan kodu (skrót):** bot działa na MEXC, BTC/USDT, MTF **30m / 15m / 5m**, moduły: wskaźniki, struktura, PA, scoring, `setup_engine`, paper trading, statystyki.  
> Docelowe TF w strategii: **1D / 1H / 15M / 5M–3M** — do wdrożenia w kolejnych iteracjach bez zmiany filozofii.

---

## 1. Fundament systemu

### Filozofia

- **Brak ML, brak „magii”** — wyłącznie reguły oparte na strukturze rynku, wskaźnikach kontekstowych i price action.
- **Modularność** — każdy filar (bias, confirm, entry, risk) w osobnym module; decyzja = warstwy, nie jeden wskaźnik.
- **Bias → kontekst → trigger** — nie wymagamy identycznego BUY/SELL na wszystkich TF; ważne jest **zgodne wejście w kierunku dominującego trendu**.
- **Jakość > ilość** — bot może długo być w `WAIT`; handel tylko przy `entry_quality` MEDIUM/HIGH i sensownym setupie.
- **Ochrona kapitału** — najpierw „czy wolno handlować”, potem „w którą stronę”, na końcu „ile ryzyka”.

### Warstwy decyzyjne (docelowy przepływ)

```
Dane OHLCV (MTF)
    → Bias makro (1D)
    → Struktura / trend (1H)
    → Potwierdzenie (15M)
    → Trigger wejścia (5M / 3M)
    → Scoring + confidence + setup_type
    → Risk (trade_allowed, SL/TP, dźwignia)
    → Paper / execution (osobna warstwa)
```

### Sygnały i stany

| Pojęcie | Znaczenie |
|---------|-----------|
| `BUY` / `SELL` / `WAIT` | Kierunek z silnika wskaźników (próg score) |
| `setup_direction` | Kierunek z `setup_engine` (bias + trigger) |
| `paper_signal` | Sygnał użyty do paper tradingu (może nadpisać WAIT przy dobrym setupie) |
| `entry_quality` | LOW / MEDIUM / HIGH — czy warto siadać przy stole |
| `confidence` | 0–5 — siła potwierdzeń |

### Typy setupów (`setup_engine`)

| Typ | Opis |
|-----|------|
| `TREND_CONTINUATION` | Trend na wyższych TF + trigger na entry |
| `PULLBACK_ENTRY` | MIXED alignment, ale pullback zgodny z biasem 30m + trigger 5m |
| `REVERSAL_ATTEMPT` | Próba odwrócenia — niższa jakość, ostrożnie |
| `NO_SETUP` | Brak edge (słaba struktura, liquidity, brak triggera) |

---

## 2. Timeframe logic

Hierarchia czasowa — **góra ustala kierunek, dół ustala timing**.

### 1D — makro bias

**Rola:** odpowiedź na pytanie *„w jakim środowisku jesteśmy?”*

- Cena względem **EMA238** (powyżej = bias bullish, poniżej = bearish).
- **MA60** jako filtr średnioterminowy (np. bull tylko gdy cena > MA60 na 1D).
- Struktura HH/HL vs LH/LL (swing macro).
- **Nie szukamy precyzyjnego entry na 1D** — tylko zezwolenie na long / short / neutral.

**Reguły:**

- Bull bias: cena > EMA238, struktura nie jest wyraźnie bearish, brak liquidity breakdown na makro.
- Bear bias: cena < EMA238, struktura nie jest wyraźnie bullish.
- Neutral / WAIT makro: mieszanka sygnałów, sideways na 1D — ograniczamy agresję na niższych TF.

**Mapowanie na kod (teraz):** proxy przez **30m** jako `TREND_TIMEFRAME` — docelowo osobny fetch 1D.

---

### 1H — struktura

**Rola:** *„jak wygląda aktualny trend operacyjny?”*

- Identyfikacja **BULLISH / BEARISH / SIDEWAYS** (HH/HL, LH/LL).
- **structure_strength:** WEAK / MEDIUM / STRONG.
- **momentum** i **trend_continuation_chance**.
- Poziomy S/R z ostatnich swingów (kontekst dla pullbacków).

**Reguły:**

- Kontynuacja trendu: seria HH+HL (long) lub LH+LL (short) + momentum STRONG.
- Sideways: brak czystej struktury — nie forsujemy entry, czekamy na trigger przy krawędzi range.
- Słaba struktura (WEAK) bez triggera na entry → `NO_SETUP`.

**Mapowanie na kod (teraz):** częściowo **30m** + `market_structure.py` na każdym TF.

---

### 15M — confirmation

**Rola:** *„czy niższy TF potwierdza, że można szukać wejścia?”*

- Nie musi dawać tego samego sygnału co 1H/1D — może być **WAIT** w fazie korekty.
- Ważne: **15m nie przeciw** kierunkowi biasu (np. bearish confirm przy bullish bias = blokada pullback long).
- RSI: strefy wykupienia/wyprzedania jako filtr (nie solo trigger).
- FVG / reakcja na poziom — pierwsze potwierdzenie „rynek reaguje”.

**Reguły:**

- Idealnie: bias zgodny z 1H, 15m w korekcie lub lekkim confirm (wick, FVG touch).
- Zły confirm: 15m struktura przeciwna + momentum przeciwne — `NO_SETUP` lub tylko `REVERSAL_ATTEMPT`.

**Mapowanie na kod (teraz):** `CONFIRM_TIMEFRAME = 15m`.

---

### 5M / 3M — entry

**Rola:** *„kiedy dokładnie wchodzimy?”*

- **Trigger** — nie pełna analiza trendu; precyzja timing.
- Preferowany TF: **5m** (MEXC spot); **3m** gdy dostępny (futures / mapping giełdy).
- Wejście po **zamknięciu świecy** triggerowej (docelowo), nie w środku losowego ticka.

**Triggery entry (long):**

- Bullish FVG + `rejection_after_touch`
- Reakcja na support (wick down, zamknięcie bullish)
- Strong bull candle + momentum shift
- Score entry TF ≥ próg (docelowo niższy niż na 1H, np. ±2 zamiast ±3)

**Triggery entry (short):** symetrycznie (resistance, bear FVG, strong bear candle).

**Mapowanie na kod (teraz):** `ENTRY_TIMEFRAME = 5m`, `price_action.py`, `setup_engine` triggery.

---

### Tabela MTF (docelowa vs obecna)

| Rola | Docelowo | W bocie (teraz) |
|------|----------|-----------------|
| Makro bias | 1D | 30m (proxy) |
| Struktura | 1H | 30m (częściowo) |
| Confirmation | 15M | 15M |
| Entry | 5M / 3M | 5M |

---

## 3. EMA238 i MA60

### EMA238 — „linia Yakuzy”

- Okres **238** (EMA na close).
- **Bias:** cena powyżej EMA238 → preferencja long; poniżej → preferencja short.
- Na wyższych TF (1D, 1H) = filtr kierunku; na entry = kontekst, nie samodzielny trigger.
- Cena „przy” EMA238 po silnym ruchu = strefa decyzji (odbicie lub przebicie).

### MA60 — filtr średnioterminowy

- **SMA(60)**.
- Potwierdza czy rynek jest po „właściwej” stronie średniej.
- Typowo: long gdy cena > MA60 **i** bias bullish; short gdy cena < MA60 **i** bias bearish.
- Rozjazd MA60 vs EMA238 → ostrożność, możliwy sideways / korekta.

### Wspólne reguły

- **Zgodność EMA238 + MA60 + struktura** → podwyższona `confidence` i `setup_quality`.
- **Rozjazd** (np. cena > MA60 ale < EMA238) → WAIT lub tylko setupy defensywne.
- Oba wskaźniki liczą się w **score** (+1 / -1); nie dublować tej samej informacji na wielu warstwach bez wag (roadmapa: wagi per TF).

**Mapowanie:** `indicators.py` → `get_ema238`, `get_ma60`.

---

## 4. Short setup

Short to **lustrzane odbicie** long — ten sam pipeline, odwrócone warunki.

### Warunki kontekstu (short)

- Makro / struktura: bias **bearish** (cena < EMA238, LH/LL, momentum bearish).
- 15m: nie bullish confirm; akceptowalny WAIT w korekcie w górę.
- Brak `liquidity_event` po stronie „panic dump” już zrealizowanym — uważaj na dołki po liquidity grab (często WAIT).

### Warunki entry (short)

- Bearish FVG rejection po touch.
- Reakcja na **resistance** (wick up, close bearish).
- Fake breakout **w górę** (przebicie oporu i powrót) — sygnał short po potwierdzeniu, nie w środku knotu.
- `candle_strength == STRONG_BEAR`, momentum shift bearish.

### Typy short w `setup_engine`

| Typ | Opis |
|-----|------|
| `TREND_CONTINUATION` | 30m+15m bearish, trigger na 5m |
| `PULLBACK_ENTRY` | MIXED, trend bearish, korekta w górę bez psucia biasu, trigger short na 5m |
| `REVERSAL_ATTEMPT` | Próba topu — tylko przy MEDIUM quality max, wąski SL |

### Filtry legacy MTF

- `FULL_BEARISH` alignment → tylko SELL z głównego silnika.
- `FULL_BULLISH` → SELL zablokowany (filtr końcowy zachowany).

---

## 5. Market breathing / exhaustion

**„Oddychanie rynku”** — faza spowolnienia po impulsie; **exhaustion** — wyczerpanie trendu przed korektą lub reversalem.

### Objawy (do kodowania)

| Objaw | Znaczenie |
|-------|-----------|
| Malejące body świec | Słabnący impuls |
| Sideways + WEAK structure | Konsolidacja / „oddech” |
| Momentum WEAK po serii STRONG | Możliwa pauza lub reversal |
| RSI neutralne po ekstremum | Brak kontynuacji |
| Brak nowych HH (w uptrend) / LL (w downtrend) | Exhaustion struktury |
| Długie knoty obustronne | Niezdecydowanie |

### Jak bot ma to traktować

- **Breathing w kierunku trendu** → czekaj na pullback i trigger (PULLBACK_ENTRY), nie agresywny market entry.
- **Exhaustion przeciw otwartej pozycji** → rozważ wcześniejsze zamknięcie paper / trailing.
- **Exhaustion + reversal_chance HIGH** → tylko `REVERSAL_ATTEMPT`, jakość max MEDIUM, mały rozmiar.

**Mapowanie (częściowe):** `market_structure` → momentum, structure_strength, reversal_chance; brak dedykowanego modułu `breathing` (roadmapa).

---

## 6. Fibonacci

### Retracement (wejście)

- Swing: wybierz **od low do high** (long) lub **od high do low** (short) na 1H / 15m.
- Strefy priorytetowe: **0.382 – 0.618** (golden pocket).
- Entry long: bias bullish + cena w strefie fibo + trigger PA (wick, FVG).
- Entry short: symetrycznie.

**Reguły:**

- Fibo **nie otwiera** trade sam — tylko podbija `confidence` / `setup_quality`.
- Poza strefą 0.382–0.618 → brak bonusu, możliwy WAIT.

### Extended TP (wyjście)

- Przy silnym trendzie: cele rozszerzone **1.272, 1.618, 2.0** od tego samego swingu.
- `target_profit_percent` dynamiczny może być mapowany na najbliższy poziom Fibo zamiast stałego % (roadmapa).
- Częściowe TP na 1.272, reszta trailing do 1.618.

**Mapowanie:** `get_fibo` — **stub** (`WAIT`); do implementacji w `indicators.py`.

---

## 7. FVG (Fair Value Gap)

### Definicja

- **Bullish FVG:** luka między high świecy 1 a low świecy 3 (3-świecowa formacja).
- **Bearish FVG:** luka między low świecy 1 a high świecy 3.
- Minimalny rozmiar luki: `FVG_MIN_GAP_PERCENT` (config).

### Logika decyzyjna

| Stan | Akcja |
|------|--------|
| FVG nie dotknięty | Kontekst / bias (słabszy sygnał) |
| FVG touched | Obserwuj reakcję |
| `rejection_after_touch` | **Trigger** — +score, +confidence |
| FVG przeciwnego kierunku już dotknięty | **-2 confidence** (pułapka) |

### Zastosowanie MTF

- FVG na **15m** = confirm strefy.
- FVG na **5m** = precyzyjny entry trigger.
- Najsilniejszy setup: bias zgodny + FVG rejection na entry TF w kierunku biasu.

**Mapowanie:** `indicators.py` → `get_fvg`; bonus w `scoring.py` i `setup_engine`.

---

## 8. BAG

**BAG** (Break And Go / strefa wybicia po akumulacji) — moduł planowany, obecnie **stub**.

### Koncepcja (docelowa)

- Identyfikacja **akumulacji** (wąski range, malejąca zmienność, breathing).
- **Break** — zamknięcie poza range z body > średnia.
- **Go** — kontynuacja w kierunku wybicia; entry na retest krawędzi range lub pierwszym FVG po breaku.

### Reguły (do kodowania)

- Long BAG: break w górę + retest + trigger bull.
- Short BAG: break w dół + retest + trigger bear.
- Fałszywy break (powrót do range) → powiązanie z **fake_breakout**, nie handluj BAG.

### Integracja

- Osobna funkcja `get_bag()` → status + kierunek + siła.
- Wpływ na score (+1/-1) i `setup_type` (może wzmacniać `TREND_CONTINUATION`).

**Mapowanie:** `indicators.py` → `get_bag()` zwraca `WAIT`.

---

## 9. Fake breakout

### Definicja

- Cena **przebija** ostatni resistance (lub support).
- W ciągu 1–2 świec **wraca** pod poziom (lub nad support).
- Zamknięcie potwierdza powrót do range.

### Znaczenie

- **Pułapka płynności** — wybicie zbierające stop-lossy przed ruchem w przeciwną stronę.
- Dla bota: **nie wchodzić** w kierunku fałszywego wybicia; rozważ setup przeciwny po potwierdzeniu.

### Wpływ na system

| Warstwa | Efekt |
|---------|--------|
| `price_action.fake_breakout` | -1 confidence |
| Risk | `risk_level` → MEDIUM |
| `setup_engine` | Nie używać jako jedynego triggera |
| Paper | Ostrożnie; nie otwierać w stronę fake break |

**Mapowanie:** `price_action.py` → `fake_breakout`.

---

## 10. Risk management

### Zasady ogólne

- **Najpierw:** `trade_allowed` — jeśli NIE, żadnego nowego paper/real trade.
- **Pozycja:** rozmiar zależny od `entry_quality` i `risk_level` (docelowo % equity).
- **SL:** poniżej ostatniego HL (long) / powyżej LH (short) na entry TF; minimum % od `target_profit` (paper: `stop_loss_percent ≈ 0.5 × TP`).
- **TP:** dynamiczny % lub poziom Fibo / struktura.
- **Jedna aktywna pozycja** (paper już tak działa).

### Zamknięcie pozycji (paper / docelowo real)

| Powód | Opis |
|-------|------|
| TP hit | Cel zysku osiągnięty |
| SL hit | Stop trafiony |
| Opposite signal | Silny sygnał przeciwny |
| Alignment MIXED | Utrata zgodności MTF (legacy filtr) |
| Liquidity / NO_SETUP | Warunek awaryjny (roadmapa) |

### Poziomy ryzyka

| Poziom | Kiedy |
|--------|--------|
| LOW | Momentum STRONG, struktura zgodna, brak fake break |
| MEDIUM | Normal / fake breakout |
| HIGH | `liquidity_event` — **brak nowych wejść** |

**Mapowanie:** `risk_manager.py`, `paper_trader.py`, `main.py` → `trade_allowed`.

---

## 11. Dynamic leverage

### Cel

Dostosować **rekomendowaną dźwignię** i **target profit %** do zmienności i jakości setupu — advisory, nie automatyczne margin trading bez zgody.

### Logika (obecna w `risk_manager.py`)

**Zmienność** (zakres % z ostatnich 10 świec entry):

| move_percent | Bazowa dźwignia |
|--------------|-----------------|
| ≥ 8% | 2 |
| ≥ 5% | 3 |
| ≥ 3% | 5 |
| ≥ 1.5% | 8 |
| < 1.5% | 12 |

**Korekta risk_level:**

| risk_level | Korekta |
|------------|---------|
| HIGH | -3 |
| MEDIUM | 0 |
| LOW | +2 |

- Wynik: clamp **1–20**.
- `target_profit_percent = max(move_percent × 0.25, 0.25)`.

### Zasady Yakuza (docelowe rozszerzenia)

- Wyższa dźwignia tylko przy `setup_quality == HIGH` i `TREND_CONTINUATION`.
- Przy `REVERSAL_ATTEMPT` i `PULLBACK_ENTRY` — cap dźwigni (np. max 5–8).
- Przy `liquidity_event` → dźwignia 0, TP/SL nieaktywne.

---

## 12. Czego bot ma unikać

### Twarde blokady (must avoid)

1. **Handel podczas `liquidity_event`** — breakdown, brak reakcji kupujących, silny bearish momentum.
2. **Ignorowanie biasu makro** — long w bearish 1D bez reversal setup.
3. **Overtrading** — otwieranie przy `entry_quality == LOW` lub `confidence < 3` (paper).
4. **Wejście w fake breakout** — bez potwierdzenia powrotu i triggera przeciwnego.
5. **Handel w SIDEWAYS bez triggera** — struktura WEAK + brak PA = `NO_SETUP`.
6. **ML / czarne skrzynki** — brak modeli predykcyjnych w core.
7. **Realne zlecenia bez warstwy paper + statystyk** — najpierw edge na `setup_history` / `paper_trades`.

### Miękkie ostrzeżenia (redukuj confidence)

- MIXED alignment (legacy) — setup_engine może nadal sugerować paper przy PULLBACK.
- FVG przeciwnego kierunku dotknięty.
- RSI ekstremalne przeciw kierunkowi (np. short przy RSI < 30 bez reversal).
- Zbyt wysoka dźwignia przy HIGH volatility.

### Behawioralne (filozofia)

- Gonienie ceny bez pullbacku.
- Handel „bo sygnał się świeci” bez `setup_type`.
- Zwiększanie lewara po stracie (roadmapa: cooldown w paper).

---

## 13. Finalny cel systemu

### Krótkoterminowy

- Stabilny **silnik analityczny** BTC/USDT na MEXC z pełnym logowaniem i paper tradingiem.
- **Mierzalny edge** — `setup_stats` / `stats_report.py`: win rate per `setup_type`, per `setup_quality`, TP/SL %.
- Wdrożenie brakujących modułów: **FIBO**, **BAG**, pełne MTF **1D / 1H**.

### Średnioterminowy

- Mapowanie docelowych TF bez psucia modularności.
- Entry na zamknięciu świecy 5m; opcjonalnie 3m gdy feed dostępny.
- SL/TP ze struktury + Fibo extended, nie tylko stały %.
- Alerty TradingView / webhook (roadmapa README).

### Długoterminowy

- **Execution** na MEXC (market/limit) z tymi samymi bramkami co paper.
- System, który **sam rzadko handluje**, ale handluje **w punkt** — zgodnie z biasem, po pullbacku, na triggerze, z kontrolowanym ryzykiem.
- Bot jako **„Yakuza desk”**: analiza → setup → jakość → ryzyko → decyzja, a nie generator sygnałów co minutę.

### Definicja sukcesu

> Bot nie ma przewidywać każdego ruchu. Ma **filtrować syf**, **nazywać setup**, **mierzyć wynik** i pozwalać traderowi (lub przyszłej warstwie execution) działać tylko wtedy, gdy matematyka i struktura są po naszej stronie.

---

## Załącznik: mapowanie modułów → strategia

| Moduł | Element strategii |
|-------|-------------------|
| `config.py` | TF, symbol, progi |
| `indicators.py` | EMA238, MA60, RSI, FVG, FIBO, BAG |
| `market_structure.py` | HH/HL, momentum, liquidity |
| `price_action.py` | Trigger, fake breakout |
| `timeframe_analysis.py` | Legacy alignment |
| `setup_engine.py` | Bias + pullback + setup_type |
| `scoring.py` | Confidence, entry_quality |
| `signals.py` | Próg BUY/SELL |
| `risk_manager.py` | Dźwignia, TP |
| `paper_trader.py` | Symulacja, SL/TP |
| `setup_stats.py` | Analityka edge |

---

*Ostatnia aktualizacja dokumentu: zgodnie ze stanem repozytorium (MTF 30m/15m/5m, setup_engine, paper, stats).*

# Legacy: Chart Guardian (stary bot Gemini / TradingView)

**Źródło (usunięte po ekstrakcji):** `notes/yakuza_knowlege/trading_bot/`  
(dawniej także `/home/malowany/Pobrane/trading_bot`)

**Werdykt:** projekt **nieprzydatny jako kod runtime** względem `trading_bot_yakuza` (inny stack: GUI screenshots + Gemini vs MEXC/ccxt + reguły).  
Poniżej **wyciągnięta wiedza strategiczna**, której nie ma (lub jest tylko stubem) w obecnym bocie — do ewentualnego wdrożenia FIBO / BAG / filtrów PA.

---

## 1. Strategia Pawła (RSI + MSB + Fibo)

### SHORT
1. **RSI > 80** (wykupienie).
2. **MSB w dół** — silna czerwona świeca przebija lokalne dołki (łamie strukturę wzrostową).
3. **Wejście** — korekta do Fibo **0.382–0.5** (od szczytu do dołka impulsu spadkowego).
4. **TP** — rozszerzenie Fibo **1.27** (najpewniejszy cel z opisów treningowych).

### LONG
1. **RSI < 20** (wyprzedanie).
2. **MSB w górę** — silna zielona świeca przebija lokalne szczyty.
3. **Wejście** — korekta do Fibo **0.382–0.5**.
4. **TP** — rozszerzenie Fibo **1.27**.

### Uwagi operacyjne
- Skan bazowy: **5M**; potwierdzenie: **15M / 30M / 60M** (wyższe TF nie mogą przeczyć kierunkowi).
- Sygnał ważny tylko po **wyraźnym** złamaniu struktury (MSB), nie po samym RSI.
- **Liquidity sweep ≠ MSB** — wybicie lokalnego high/low samym knotem i szybki powrót to zbieranie płynności, nie prawdziwe MSB.

### Rozszerzenia z przykładów treningowych
- Przy silnych ruchach: **0.786** bywa poziomem reakcji / częściowym TP; **1.618 / 1.809** jako maksymalne TP.
- Strefa **0.5–0.786** opisywana jako S/R przy potwierdzeniu longa po sweepe dolków.
- Filtry dodatkowe: knoty, Marubozu (impuls), Doji/Harami przy poziomie, FVG/BAG.

---

## 2. FVG vs BAG (definicja Pawła)

| | **FVG (Fair Value Gap)** | **BAG (Breakaway Gap)** |
|---|---|---|
| Budowa | 3 świece; ciało 3. zamyka się **wewnątrz knotu** 2. (nad/pod ciałem 2.) | 3 świece; ciało 3. zamyka się **całkowicie poza** zakresem 2. |
| Sens | Luka / imbalance — rynek często **wraca** do strefy | Czysty momentum — często **bez** cofnięcia |
| Użycie | Strefa powrotu + kontynuacja | Kontynuacja wybicia; nie grać jak FVG retest |

**Reguła Pine (Bull FVG/BAG-style Pawła):** 3 zielone + `close[0] > close[1]` + `close[0] <= high[1]`.  
**Bear:** 3 czerwone + `close[0] < close[1]` + `close[0] >= low[1]`.

Pełny wskaźnik TradingView: [`legacy_pawel_bag_fvg_v6.pine`](legacy_pawel_bag_fvg_v6.pine).

> W `yakuza_strategy_core.md` FIBO/BAG są nadal **planowane / stub** — ten plik + Pine to konkretna definicja do portu.

---

## 3. Formuła lewara (z `analizuj.py`)

Cel: minimum **25%** zysku brutto do TP (`MIN_TARGET_PROFIT_PERCENT`).

```
move_percent = |tp - entry| / entry * 100
lewar_raw   = 25 / move_percent
lewar       = min(ceil(lewar_raw, 1 decimal), MAX_LEVERAGE)   # domyślnie max 20x
```

Bez opłat, fundingu, poślizgu i ryzyka likwidacji.

---

## 4. Przepływ starego bota (referencja, nie do uruchamiania)

```
trening (screen + opis) → screenshot 5M TradingView → Gemini skan
  → ALERT? → screenshoty 15/30/60 → potwierdzenie MTF
  → lewar + opcjonalny Pine entry/SL/TP
```

- Few-shot w prompcie (max ~12 przykładów) — **bez** trwałego treningu modelu.
- Model: `gemini-2.5-flash` (historycznie).
- Stack Windows-oriented: `pyautogui`, `pygetwindow`, `winsound` — nie pasuje do obecnego Linux + ccxt.

---

## 5. Lekcje PA ze skryptu treningowego (TikTok / świece)

Priorytet decyzji: **RSI + MSB + Fibo + FVG/BAG**; formacje świec tylko jako filtr.

- Marubozu → potwierdzenie impulsu/MSB, nie solo entry.
- Doji → niezdecydowanie; znaczenie dopiero przy poziomie.
- Harami → kompresja; wymaga wybicia/reakcji.
- Sweep płynności → nie mylić z MSB.
- Seria mocnych świec + ekstremalne RSI → możliwe wyczerpanie; czekać na MSB + korektę Fibo.

---

## 6. Co celowo NIE przenoszono

- `analizuj.py`, `main.py` (screenshot), `local_ai_ui.py` (Ollama) — zbędny stack.
- Zrzuty JPG / filmiki treningowe — duże media; treść opisów powyżej.
- Klucze API / `.env` — nie było `.env` w kopii; nic nie kopiowano.

---

## 7. Mapowanie na obecny projekt

| Legacy | Obecny `trading_bot_yakuza` |
|--------|------------------------------|
| RSI ekstremum + MSB | częściowo: RSI + `structure_events` / BOS·CHOCH |
| Fibo 0.382–0.5 / 1.27 | **stub / do wdrożenia** |
| FVG/BAG Pawła | FVG częściowo; **BAG stub** — użyj definicji z §2 + Pine |
| Potwierdzenie MTF GUI | MTF 30m/15m/5m w kodzie |
| Paper / live | paper + observability `paper_*` |
| Gemini vision | nie używane |

**Backup archiwum (opcjonalnie):** `notes/yakuza_knowlege/trading_bot.rar` — pełny dump starego folderu, poza Git.

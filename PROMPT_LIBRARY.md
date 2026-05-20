# Prompt Library — trading_bot_yakuza

Gotowe prompty do pracy z agentem AI nad tym repozytorium.  
Kopiuj sekcję, dopisz kontekst (logi, błąd, plik).

**Zasady ogólne:** nie zmieniaj logiki tradingowej bez wyraźnej prośby; najpierw analiza, potem diff.

---

## Analiza repo

```
Przeanalizuj projekt trading_bot_yakuza.

Przeczytaj: ARCHITECTURE.md, README.md, notes/yakuza_strategy_core.md.

Opisz:
1. Moduły i zależności
2. Flow jednej iteracji main.py
3. Różnicę: SIGNAL vs paper_signal vs setup_engine
4. Co jest observer-only (structure_events)
5. Co jest stubem (FIBO, BAG)
6. Czego brakuje do execution

Nie zmieniaj kodu. Tylko raport.
```

```
Porównaj README.md z faktycznym kodem.

Wskaż rozbieżności i zaproponuj tylko aktualizacje dokumentacji (bez zmian .py).
```

---

## Debug

```
Mam problem w trading_bot_yakuza: [OPIS BŁĘDU / STACK TRACE].

Kroki:
1. Zidentyfikuj moduł (main, paper_trader, setup_engine, ccxt, …)
2. Przeczytaj tylko potrzebne pliki
3. Wyjaśnij przyczynę
4. Zaproponuj minimalny fix

Nie zmieniaj: scoring.py, signals.py, risk_manager.py, setup_engine.py
chyba że błąd jest tam i poproszę explicite.

Nie uruchamiaj main.py ani skryptów sieciowych bez pytania.
```

```
Bot kończy na WAIT / nie otwiera paper.

Sprawdź kolejność bramek:
- get_signal (±3)
- apply_alignment_final_filter (MIXED)
- detect_setup / resolve_paper_from_setup
- can_open_paper_trade (confidence, quality, cooldown)

Podaj która bramka najpewniej blokuje i dlaczego (na podstawie kodu).
Bez zmian logiki — tylko diagnoza.
```

---

## Observer analysis

```
Przeanalizuj warstwę observer: structure_events.py + integracja w main.py.

Potwierdź:
1. Czy moduł wpływa na SIGNAL lub paper_trader (powinien: NIE)
2. Kiedy jest wywoływany w pętli
3. Jakie pola trafiają do setup_history.jsonl

Nie dodawaj integracji ze scoring/setup_engine.
Tylko raport + ewentualne poprawki dokumentacji.
```

```
Chcę podłączyć structure_events do setup_engine w przyszłości.

Zaproponuj PLAN (bez implementacji):
- które pola BOS/CHoCH mają sens jako confluence
- które setup_type dotyczy
- jak uniknąć podwójnej kary z market_structure SIDEWAYS

Tylko markdown plan, zero zmian w .py.
```

---

## Stats analysis

```
Przeanalizuj setup_stats.py i stats_report.py.

Opisz:
1. Skąd biorą się dane (setup_history.jsonl, paper_trades.json)
2. Jak łączone są trady ze snapshotami
3. Jakie breakdowny structure events są dostępne

Nie zmieniaj logiki tradingowej.
Jeśli brakuje metryki w raporcie — zaproponuj tylko rozszerzenie setup_stats (soft).
```

```
Mam logs/setup_history.jsonl i paper_trades.json.

Powiedz jak interpretować:
- win rate TREND_CONTINUATION
- setup_quality + structure_event_strength
- sideways continuation penalty w setup_reasons

Bez uruchamiania bota. Mogę wkleić fragment stats_report.
```

---

## Structure events

```
Przeanalizuj structure_events.py: BOS, CHoCH, control shift.

Wyjaśnij reguły w języku tradera (bez ML).
Wskaż ograniczenia prostego algorytmu swingów.
Nie zmieniaj kodu.
```

```
Chcę test structure events.

Powiedz który znany skrypt w repo jest bezpieczny:
- test_structure_events_snapshot.py

Podaj komendę i co powinno przejść.
Nie uruchamiaj nic innego.
```

```
W logach widzę STRUCTURE_EVENT_BOS=NONE przy wyraźnym trendzie.

Na podstawie kodu structure_events.py wyjaśnij możliwe przyczyny
(MIN_CANDLES, prior_structure NEUTRAL, close vs swing).

Tylko analiza — bez zmiany progów bez prośby.
```

---

## Rozwój funkcji (szablon)

```
Zadanie: [KRÓTKI OPIS]

Ograniczenia:
- Zachowaj modularność
- Nie ruszaj scoring/signals/risk bez zgody
- Minimalny diff
- py_compile po zmianach
- Bez real execution

Najpierw plan w 5 punktach, potem implementacja po moim OK.
```

---

## Checkpoint / porządek

```
Zrób checkpoint projektu (tylko dokumentacja + .gitignore jeśli trzeba):

1. git status
2. Czy ARCHITECTURE.md / PROMPT_LIBRARY.md / .cursor/rules są aktualne
3. Krótki raport stanu modułów

Nie zmieniaj logiki tradingowej.
```

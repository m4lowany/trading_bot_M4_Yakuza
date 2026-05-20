# Project rules — trading_bot_yakuza

Reguły dla agentów AI i deweloperów pracujących w tym repozytorium.

---

## Priorytety

1. **Nie zmieniaj logiki tradingowej bez wyraźnej prośby użytkownika.**
   Dotyczy m.in.: `scoring.py`, `signals.py`, `risk_manager.py`, `setup_engine.py`, `timeframe_analysis.py` (filtry alignment), `paper_trader.py` (reguły open/close).

2. **Zachowaj modularność.**
   - Nowa funkcja → nowy moduł lub rozszerzenie istniejącego z jedną odpowiedzialnością.
   - Unikaj rozlewania logiki po `main.py` (tylko integracja i I/O).

3. **Nie refaktoruj wszystkiego naraz.**
   - Jeden cel na zmianę (np. tylko stats, tylko docs, tylko observer field).
   - Mały, reviewowalny diff.

4. **Nie uruchamiaj nieznanych plików.**
   - Dozwolone bez pytania: `python3 -m py_compile`, znane testy z repo (`test_structure_events_snapshot.py`), `stats_report.py` (read-only na logs).
   - `main.py` (sieć MEXC), instalatory, obce skrypty — tylko na prośbę użytkownika.

5. **Najpierw analiza, potem zmiany.**
   - Przeczytaj `ARCHITECTURE.md` i dotknięte moduły.
   - Krótki plan przed edycją kodu.
   - Raport po pracy: pliki, co zmienione, py_compile, jak testować.

---

## Architektura (skrót)

- **MTF:** 30m / 15m / 5m (`config.py`).
- **SIGNAL** — legacy scoring + alignment; **paper_signal** — może pochodzić z `setup_engine`.
- **structure_events** — **observer only**; nie wpływa na decyzje bez explicit task.
- **Brak real execution** na giełdzie.

---

## Observer layer

- `structure_events.py` loguje i zapisuje snapshot — nie podłączać do scoring/setup_engine bez osobnego zadania i uzasadnienia stats.
- Wywołanie w `main.py` pozostaje **po** decyzjach paper.

---

## Dokumentacja

- Strategia: `notes/yakuza_strategy_core.md`
- Technika: `ARCHITECTURE.md`
- Prompty: `PROMPT_LIBRARY.md`
- Po większej zmianie modułu — zaktualizuj README lub ARCHITECTURE (nie oba jeśli wystarczy jeden).

---

## Git i sekrety

- Nie commituj: `logs/`, `venv/`, `.env`, `__pycache__/`, `*.pyc`.
- Nie dodawaj kluczy API do repo.
- Commity tylko gdy użytkownik poprosi.

---

## Testy i jakość

- Po zmianach `.py`: `python3 -m py_compile` na dotkniętych plikach.
- Nie dodawaj ciężkich zależności (pandas, ML) bez zgody.
- Testy tylko jeśli mają sens dla realnego zachowania modułu.

---

## Czego unikać

- Globalne obniżanie progów score „żeby częściej handlował”.
- Hard block całego bota bez soft filter / stats.
- Usuwanie sideways penalty lub MIXED cooldown bez dyskusji.
- Force push, amend commitów bez prośby.

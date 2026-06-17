#!/usr/bin/env python3
"""ETAP 2.5 — structure leg state machine tests."""

from structure_events import (
    _StructureStateMachine,
    _resolve_structure_event,
    analyze_structure_events,
    _run_state_machine,
    _filter_valid_swings,
    _find_swings,
)


def _candle(o, h, l, c):
    return [0, o, h, l, c, 0]


def _bearish_base_pattern():
    """Bearish LH/LL swings; last_LH ~ 101.0 at index 14."""
    return [
        (100.0, 100.4, 99.6, 100.2),
        (100.2, 100.5, 99.8, 100.3),
        (100.3, 100.6, 99.9, 100.1),
        (100.1, 100.3, 99.0, 99.2),
        (99.2, 99.5, 98.8, 99.0),
        (99.0, 99.3, 98.5, 98.7),
        (98.7, 101.5, 98.6, 101.0),   # swing high ~6
        (101.0, 101.2, 99.5, 99.8),
        (99.8, 100.0, 99.0, 99.2),
        (99.2, 99.5, 98.8, 99.0),
        (99.0, 99.2, 97.8, 98.0),     # swing low ~10
        (98.0, 98.5, 97.5, 98.3),
        (98.3, 98.8, 98.0, 98.6),
        (98.6, 100.0, 98.4, 99.8),
        (99.8, 101.0, 99.5, 100.0),   # LH ~14, high 101.0
        (100.0, 100.2, 98.5, 99.0),   # reaction down
        (99.0, 99.2, 98.0, 98.5),
        (98.5, 98.8, 98.0, 98.3),     # buffer index 17
    ]


def _build_bear_to_bull_bos_sequence():
    """
    BEARISH -> CHOCH_BULLISH (close > LH 101) -> BULLISH -> BOS_BULLISH.
    """
    rows = list(_bearish_base_pattern())
    lh_level = 101.0
    rows.append((100.5, lh_level + 0.5, 100.2, lh_level + 0.3))   # CHOCH bar
    rows.extend([
        (101.3, 103.0, 101.0, 102.8),
        (102.8, 102.9, 101.5, 101.8),
        (101.8, 102.0, 101.2, 101.5),
    ])
    swing_high = 103.0
    rows.append((102.5, swing_high + 0.2, 102.3, swing_high + 0.1))  # BOS bar
    return [_candle(*row) for row in rows]


def _replay_events(candles):
    sh, sl = _find_swings(candles)
    vh, vl = _filter_valid_swings(candles, sh, sl)
    sm, last_bar = _run_state_machine(candles, vh, vl)
    return sm, last_bar, analyze_structure_events(candles)


def test_apply_choch_resets_leg_flag():
    sm = _StructureStateMachine()
    sm.character = "BULLISH"
    sm.choch_fired_in_leg = True

    reason = sm.apply_choch("CHOCH_BEARISH")

    assert sm.character == "BEARISH"
    assert sm.choch_fired_in_leg is False
    assert sm.leg_index == 1
    assert sm.structure_phase == "TRANSITION"
    assert reason == "leg reset: BULLISH → BEARISH after CHOCH_BEARISH"


def test_second_choch_allowed_after_leg_reset():
    """After CHOCH_BEARISH resets leg, bearish structure can fire CHOCH_BULLISH."""
    sm = _StructureStateMachine()
    sm.apply_choch("CHOCH_BEARISH")
    assert sm.character == "BEARISH"
    assert sm.choch_fired_in_leg is False

    bos, choch, level, first, reasons = _resolve_structure_event(
        character=sm.character,
        choch_fired_in_leg=sm.choch_fired_in_leg,
        close_break_up=True,
        close_break_down=False,
        last_lh=65463.0,
        last_hl=None,
        last_swing_high=66000.0,
        last_swing_low=64000.0,
    )

    assert choch == "CHOCH_BULLISH"
    assert bos == "NONE"
    assert first is True
    assert level == 65463.0
    assert not any("suppressed" in r for r in reasons)


def test_bearish_choch_bullish_bos_sequence():
    candles = _build_bear_to_bull_bos_sequence()
    sm, last_bar, events = _replay_events(candles)

    assert events["structure_character"] == "BULLISH"
    assert events["structure_phase"] == "CONTINUATION"
    assert events["leg_index"] == 1
    assert last_bar["bos"] == "BOS_BULLISH"
    assert last_bar["break_validity"] == "BOS"
    assert events["bos"] == "BOS_BULLISH"
    assert sm.last_choch == "CHOCH_BULLISH"


def test_leg_index_in_output():
    candles = _build_bear_to_bull_bos_sequence()
    events = analyze_structure_events(candles)
    assert "leg_index" in events
    assert isinstance(events["leg_index"], int)
    assert events["leg_index"] == 1
    assert any(r.startswith("leg_index=") for r in events["event_reasons"])


def test_double_close_above_lh_after_choch_flips_bullish():
    rows = list(_bearish_base_pattern())
    lh = 101.0
    rows.append((100.5, lh + 0.2, 100.2, lh + 0.15))  # CHOCH bullish
    rows.append((101.2, lh + 0.3, 101.0, lh + 0.2))   # second break — bullish leg

    candles = [_candle(*r) for r in rows]
    sm, _, events = _replay_events(candles)

    assert sm.character == "BULLISH"
    assert events["leg_index"] == 1
    assert not any("CHOCH suppressed" in r for r in events["event_reasons"])


def main():
    test_apply_choch_resets_leg_flag()
    test_second_choch_allowed_after_leg_reset()
    test_bearish_choch_bullish_bos_sequence()
    test_leg_index_in_output()
    test_double_close_above_lh_after_choch_flips_bullish()
    print("All structure_events leg tests passed.")


if __name__ == "__main__":
    main()

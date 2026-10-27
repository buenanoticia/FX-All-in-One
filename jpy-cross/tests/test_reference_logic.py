"""Reference tests for JPY Cross v1.0.0 (inherited from USDJPY v1.1.1) (not a Pine compiler or TradingView runtime).

Run from the package folder:
    python3 -m unittest discover -s tests -v

Python models below intentionally mirror only small, named calculations.
They do not simulate the complete indicator, market data, fills or alerts.
"""
from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

PINE_FILE = Path(__file__).resolve().parents[1] / "FX_AllInOne_JPY_Cross.pine"
SOURCE = PINE_FILE.read_text(encoding="utf-8")
PIP = 0.01


def width_pips(
    atr_yen: float | None,
    mode: str,
    multiple: float = 2.5,
    fixed: float = 20.0,
    floor: float = 20.0,
    step: float = 0.1,
) -> float | None:
    if step <= 0:
        raise ValueError("step must be positive")
    raw = atr_yen / PIP * multiple if atr_yen is not None and atr_yen > 0 else None
    if mode == "fixed":
        selected = fixed
    elif mode == "floor":
        selected = max(raw, floor) if raw is not None else None
    elif mode == "atr":
        selected = raw
    else:
        raise ValueError("unknown mode")
    return None if selected is None else math.ceil(selected / step - 1e-9) * step


def timeframe_route(chart_seconds: int, atr_seconds: int) -> str:
    return "lower" if atr_seconds < chart_seconds else "higher" if atr_seconds > chart_seconds else "same"


def latest_ended(
    values: list[float | None], close_times: list[int | None], cutoff: int
) -> tuple[float | None, int | None]:
    if len(values) != len(close_times):
        raise ValueError("tuple arrays must have matching lengths")
    for value, end in reversed(list(zip(values, close_times))):
        if value is not None and end is not None and end <= cutoff:
            return value, end
    return None, None


def gran_regions(
    low: float, high: float, close: float, previous_close: float,
    ma: float, previous_ma: float, distance: float
) -> tuple[bool, bool, bool, bool]:
    buy2_region = (low < ma or previous_close < previous_ma) and close > ma
    sell2_region = (high > ma or previous_close > previous_ma) and close < ma
    buy3_region = low >= ma and low <= ma + distance and close >= ma and previous_close >= previous_ma
    sell3_region = high <= ma and high >= ma - distance and close <= ma and previous_close <= previous_ma
    return buy2_region, sell2_region, buy3_region, sell3_region


def wave_invalid(
    direction: int, phase: int, low: float, high: float,
    w0: float, w1: float, w2: float | None = None, w4: float | None = None
) -> bool:
    if not (0 < phase < 5):
        return False
    if direction == 1:
        return (
            low <= w0
            or (phase in (3, 4) and low <= w1)
            or (phase == 2 and w2 is not None and low < w2)
            or (phase == 4 and w4 is not None and low < w4)
        )
    if direction == -1:
        return (
            high >= w0
            or (phase in (3, 4) and high >= w1)
            or (phase == 2 and w2 is not None and high > w2)
            or (phase == 4 and w4 is not None and high > w4)
        )
    return False


def scrub(text: str) -> str:
    """Remove strings and // comments for simple bracket checks only."""
    result = []
    quoted = False
    escaped = False
    i = 0
    while i < len(text):
        c = text[i]
        if quoted:
            if c == "\n":
                raise ValueError("unescaped newline in string")
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
            result.append(" ")
            i += 1
        elif c == '"':
            quoted = True
            result.append(" ")
            i += 1
        elif text[i:i + 2] == "//":
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            result.extend(" " * (end - i))
            i = end
        else:
            result.append(c)
            i += 1
    if quoted:
        raise ValueError("unterminated string")
    return "".join(result)


class WidthTests(unittest.TestCase):
    def test_raw_atr_example(self):
        self.assertAlmostEqual(0.03084 / PIP * 2.5, 7.71)

    def test_atr_rounds_up_to_7_8(self):
        self.assertAlmostEqual(width_pips(0.03084, "atr"), 7.8)

    def test_fixed_20(self):
        self.assertAlmostEqual(width_pips(0.03084, "fixed"), 20.0)

    def test_fixed_25_yen(self):
        self.assertAlmostEqual(width_pips(None, "fixed", fixed=25.0) * PIP * 3000, 750.0)

    def test_floor_20(self):
        self.assertAlmostEqual(width_pips(0.03084, "floor"), 20.0)

    def test_floor_not_cap(self):
        self.assertAlmostEqual(width_pips(0.12, "floor"), 30.0)

    def test_missing_atr_mode(self):
        self.assertIsNone(width_pips(None, "atr"))

    def test_missing_floor_mode(self):
        self.assertIsNone(width_pips(None, "floor"))

    def test_missing_fixed_mode(self):
        self.assertAlmostEqual(width_pips(None, "fixed"), 20.0)

    def test_zero_atr_is_unavailable(self):
        self.assertIsNone(width_pips(0.0, "atr"))

    def test_integer_pip_step(self):
        self.assertEqual(width_pips(0.03084, "atr", step=1.0), 8.0)

    def test_exact_boundary_not_overrounded(self):
        self.assertAlmostEqual(width_pips(0.08, "atr"), 20.0)

    def test_3000_units_20_pips(self):
        self.assertAlmostEqual(20 * PIP * 3000, 600.0)

    def test_reference_spread_2_6(self):
        self.assertAlmostEqual(2.6 * PIP * 3000, 78.0)

    def test_reference_spread_8_2(self):
        self.assertAlmostEqual(8.2 * PIP * 3000, 246.0)

    def test_atr_width_7_8_yen(self):
        self.assertAlmostEqual(7.8 * PIP * 3000, 234.0)

    def test_width_formula_grid(self):
        for atr in (0.001, 0.03084, 0.04, 0.08, 0.12, 0.3):
            for step in (0.1, 0.5, 1.0):
                raw = atr / PIP * 2.5
                result = width_pips(atr, "atr", step=step)
                self.assertGreaterEqual(result + 1e-8, raw)
                self.assertLess(result - raw, step + 1e-8)


class TimeframeTests(unittest.TestCase):
    def test_1m_chart_5m_atr(self):
        self.assertEqual(timeframe_route(60, 300), "higher")

    def test_5m_chart_5m_atr(self):
        self.assertEqual(timeframe_route(300, 300), "same")

    def test_15m_chart_5m_atr(self):
        self.assertEqual(timeframe_route(900, 300), "lower")

    def test_1h_chart_5m_atr(self):
        self.assertEqual(timeframe_route(3600, 300), "lower")

    def test_1h_chart_4h_atr(self):
        self.assertEqual(timeframe_route(3600, 14400), "higher")

    def test_latest_ended_excludes_unfinished(self):
        self.assertEqual(latest_ended([0.02, 0.03], [300, 600], 450), (0.02, 300))

    def test_exact_end_is_eligible(self):
        self.assertEqual(latest_ended([0.02, 0.03], [300, 600], 600), (0.03, 600))

    def test_empty_array_has_no_fallback(self):
        self.assertEqual(latest_ended([], [], 600), (None, None))

    def test_before_first_end(self):
        self.assertEqual(latest_ended([0.02], [300], 250), (None, None))

    def test_missing_latest_value(self):
        self.assertEqual(latest_ended([0.02, None], [300, 600], 600), (0.02, 300))


class SignalTests(unittest.TestCase):
    def test_buy2_crosses_below_and_recovers(self):
        buy2, _, buy3, _ = gran_regions(99.9, 100.3, 100.2, 100.1, 100.0, 100.0, 0.3)
        self.assertTrue(buy2)
        self.assertFalse(buy3)

    def test_buy3_does_not_break_ma(self):
        buy2, _, buy3, _ = gran_regions(100.1, 100.4, 100.3, 100.2, 100.0, 100.0, 0.3)
        self.assertFalse(buy2)
        self.assertTrue(buy3)

    def test_previous_close_compared_to_previous_ma(self):
        buy2, _, _, _ = gran_regions(101.1, 102.2, 102.0, 100.5, 101.0, 100.0, 0.3)
        self.assertFalse(buy2)

    def test_sell2_crosses_above_and_recovers(self):
        _, sell2, _, sell3 = gran_regions(99.6, 100.1, 99.8, 99.8, 100.0, 100.0, 0.3)
        self.assertTrue(sell2)
        self.assertFalse(sell3)

    def test_sell3_stays_below(self):
        _, sell2, _, sell3 = gran_regions(99.6, 99.9, 99.7, 99.8, 100.0, 100.0, 0.3)
        self.assertFalse(sell2)
        self.assertTrue(sell3)

    def test_combined_setup_phase2_not_phase3(self):
        self.assertEqual([phase == 2 for phase in (1, 2, 3, 4, 5)], [False, True, False, False, False])

    def test_origin_wick_long(self):
        self.assertTrue(wave_invalid(1, 1, 99.9, 102, 100, 103))

    def test_origin_wick_short(self):
        self.assertTrue(wave_invalid(-1, 1, 98, 103.1, 103, 100))

    def test_overlap_long_equal_price(self):
        self.assertTrue(wave_invalid(1, 3, 103, 108, 100, 103, 101))

    def test_overlap_short_equal_price(self):
        self.assertTrue(wave_invalid(-1, 3, 95, 100, 103, 100, 102))

    def test_locked_wave2_break(self):
        self.assertTrue(wave_invalid(1, 2, 101.9, 105, 100, 104, 102))

    def test_valid_up_phase2(self):
        self.assertFalse(wave_invalid(1, 2, 102.5, 105, 100, 104, 102))

    def test_completed_phase_not_active_wick_check(self):
        self.assertFalse(wave_invalid(1, 5, 90, 110, 100, 103, 101, 104))

    def test_shortest_wave_comparison(self):
        self.assertTrue(2 < 3 and 2 < 4)
        self.assertFalse(3 < 3 and 3 < 4)


class SourceChecks(unittest.TestCase):
    def test_one_indicator_v6(self):
        self.assertTrue(SOURCE.startswith("//@version=6\n"))
        self.assertEqual(SOURCE.count("indicator("), 1)
        self.assertNotIn("strategy(", scrub(SOURCE))

    def test_no_malformed_decimal_pattern(self):
        self.assertNotIn('"#.1"', SOURCE)
        self.assertIn('str.tostring(value, "0.0")', SOURCE)

    def test_eight_alerts(self):
        self.assertEqual(SOURCE.count("alertcondition("), 8)

    def test_explicit_confirmation_flags(self):
        for name in ("granBuy1", "granBuy2", "granBuy3", "granSell1", "granSell2", "granSell3", "granExitLong", "granExitShort", "dowUpEvent", "dowDownEvent", "dowEndEvent"):
            self.assertRegex(SOURCE, rf"bool {name} = confirmed and ")
        self.assertIn("bool confirmed = barstate.isconfirmed", SOURCE)

    def test_lower_request_only_in_lower_branch(self):
        self.assertRegex(SOURCE, r"if atrSeconds < chartSeconds\n    \[atrValues, atrCloseTimes\] = request\.security_lower_tf")
        self.assertEqual(SOURCE.count("request.security_lower_tf("), 1)
        self.assertIn("ignore_invalid_timeframe=true", SOURCE)

    def test_higher_timeframe_offsets_both_values(self):
        self.assertIn("[ta.atr(atrLen)[1], time_close[1]]", SOURCE)
        self.assertEqual(SOURCE.count("lookahead=barmerge.lookahead_on"), 1)

    def test_no_original_fallback(self):
        self.assertNotIn("atr_calc", SOURCE)
        self.assertNotIn("atr5m", SOURCE)
        self.assertIn("float atrSource = na", SOURCE)

    def test_golden_phase_exact(self):
        for name in ("goldenSetupBuy", "goldenSetupSell"):
            line = next(line for line in SOURCE.splitlines() if line.startswith("bool " + name + " ="))
            self.assertIn("waveCount == 2", line)
            self.assertNotIn("waveCount == 3", line)

    def test_previous_ma_alignment(self):
        self.assertIn("close[1] < targetMA[1]", SOURCE)
        self.assertIn("close[1] > targetMA[1]", SOURCE)

    def test_actual_order_code_absent(self):
        clean = scrub(SOURCE)
        self.assertNotRegex(clean, r"\bstrategy\.(entry|exit|order|close)\(")
        self.assertNotIn("webhook", clean.lower())

    def test_manual_spread_not_a_signal_filter(self):
        signal_area = SOURCE[SOURCE.index("// ───────── 4."):SOURCE.index("// ───────── 5.")]
        self.assertNotIn("manualSpreadPips", signal_area)

    def test_pivot_default_is_confirmation_bar(self):
        self.assertRegex(SOURCE, r"labelsAtPivot = input\.bool\(false,")
        self.assertIn("labelsAtPivot ? pivotBar : bar_index", SOURCE)

    def test_state_reset_clears_direction_prices(self):
        block = SOURCE[SOURCE.index("if confirmed and waveInvalid\n"):SOURCE.index("// 初期値は")]
        for key in ("waveCount := 0", "waveDir := 0", "wavePivotBar := na"):
            self.assertIn(key, block)
        for i in range(6):
            self.assertIn(f"w{i}Price := na", block)

    def test_panel_rows_and_clear(self):
        rows = [int(n) for n in re.findall(r"f_row\(tb, (\d+),", SOURCE)]
        self.assertEqual(rows, list(range(16)))
        self.assertIn("table.clear(tb, 0, 0, 1, 15)", SOURCE)

    def test_script_and_txt_identical(self):
        self.assertEqual(PINE_FILE.read_bytes(), PINE_FILE.with_suffix(".txt").read_bytes())

    def test_old_marketing_claims_removed(self):
        for phrase in ("FOREX.com推奨", "FOREX.com方式", "最も期待値", "厳密分離", "推奨トレール幅"):
            self.assertNotIn(phrase, SOURCE)

    def test_brackets_strings_and_indentation(self):
        text = scrub(SOURCE)
        stack = []
        opening = "([{"
        closing = {")": "(", "]": "[", "}": "{"}
        for ch in text:
            if ch in opening:
                stack.append(ch)
            elif ch in closing:
                self.assertTrue(stack, "unmatched closing bracket")
                self.assertEqual(stack.pop(), closing[ch])
        self.assertEqual(stack, [])
        for line in SOURCE.splitlines():
            self.assertNotIn("\t", line)
            if line.strip():
                self.assertEqual((len(line) - len(line.lstrip(" "))) % 4, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

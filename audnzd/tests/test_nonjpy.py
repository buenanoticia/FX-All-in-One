"""Static checks and small Python reference calculations; NOT a Pine compiler/backtest."""
from pathlib import Path
import hashlib
import math
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = list(ROOT.glob("FX_AllInOne_*.pine"))
assert len(FILES) == 1, "Run within one dedicated pair folder."
PINE = FILES[0]
SRC = PINE.read_text(encoding="utf-8")
PAIR = PINE.stem.removeprefix("FX_AllInOne_")
BASE, QUOTE = {"NOKSEK": ("NOK", "SEK"), "AUDNZD": ("AUD", "NZD")}[PAIR]
HASHES = {'analysis': '42617e4f5a5d699f20e2da521578f7a08bc7708d626fa16628e087890e188a0a', 'atr_calculation': '6f5e0ea838a3d20b809f769fef47c8e3c9f5211d74081b450aa9a0dc79364ade', 'alerts': 'fbb268794d060893770329fd43bf150d4fe4abeefc04417d4621c08539b7d406'}

def block(start, end):
    return SRC[SRC.index(start):SRC.index(end)]

def width(atr, pip=0.0001, multiplier=2.5, mode="atr", fixed=20.0, floor=20.0, step=0.1):
    valid = atr is not None and atr > 0
    raw = atr / pip * multiplier if valid else None
    chosen = fixed if mode == "fixed" else max(raw, floor) if mode == "floor" and valid else raw
    return None if chosen is None else math.ceil(chosen / step - 1e-9) * step

def conversion(mode, auto=None, manual=0.0):
    value = auto if mode == "auto" else manual if mode == "manual" else None
    return value if value is not None and value > 0 else None

def yen(amount, rate):
    return amount * rate if amount is not None and rate is not None and rate > 0 else None

class SourceChecks(unittest.TestCase):
    def test_version_and_indicator(self):
        self.assertTrue(SRC.startswith("//@version=6\n"))
        self.assertEqual(len(re.findall(r"^indicator\(", SRC, re.M)), 1)
        self.assertNotIn("strategy(", SRC)
        self.assertIn(f'FX All-in-One Pro {PAIR} v1.0.0', SRC)

    def test_target_guard(self):
        self.assertIn(f'syminfo.basecurrency == "{BASE}" and syminfo.currency == "{QUOTE}"', SRC)
        self.assertIn('syminfo.type == "forex"', SRC)
        self.assertIn("if not isTargetPair", SRC)
        self.assertIn("not chart.is_standard or timeframe.isticks", SRC)

    def test_history_buffer_preserved(self):
        self.assertEqual(SRC.count("max_bars_back(time, 5000)"), 1)
        self.assertLess(SRC.index("max_bars_back(time, 5000)"), SRC.index("line.new("))
        self.assertIn("maxval=4900", SRC)

    def test_analysis_hash(self):
        b = block("// ───────── 1. 移動平均線", "// ───────── 5. ATR・固定幅")
        self.assertEqual(hashlib.sha256(b.encode()).hexdigest(), HASHES["analysis"])

    def test_atr_hash(self):
        b = block("float atrOnChart =", "// 手入力値は参考表示にのみ使用")
        self.assertEqual(hashlib.sha256(b.encode()).hexdigest(), HASHES["atr_calculation"])

    def test_alert_hash(self):
        b = block("// ───────── 7. アラート", "// ───────── 8. 状況パネル")
        self.assertEqual(hashlib.sha256(b.encode()).hexdigest(), HASHES["alerts"])
        self.assertEqual(len(re.findall(r"^alertcondition\(", SRC, re.M)), 8)

    def test_pip_and_units(self):
        self.assertIn("float pipSize = useManualPip ? manualPipSize : 0.0001", SRC)
        self.assertIn("manualPipSize = input.float(0.0001", SRC)
        self.assertIn("useManualPip = input.bool(false", SRC)
        self.assertIn("units = input.int(3000", SRC)
        self.assertNotIn("float pipSize = 0.01", SRC)

    def test_currency_dimensions(self):
        self.assertIn("float pipAmountQuote = pipSize * units", SRC)
        self.assertIn("float widthAmountQuote = not na(trailDist) ? trailDist * units : na", SRC)
        self.assertIn("pipAmountQuote * quoteToJPY", SRC)
        self.assertIn("widthAmountQuote * quoteToJPY", SRC)
        self.assertIn(f"1 {QUOTE} は何円か", SRC)

    def test_daily_rate_and_missing(self):
        self.assertIn('request.currency_rate(quoteCurrency, "JPY", ignore_invalid_currency=true)', SRC)
        self.assertIn("quoteToJPY > 0", SRC)
        self.assertIn("manualJPYRate > 0", SRC)
        self.assertIn("円換算不可（0円ではない）", SRC)
        self.assertNotIn("nz(quoteToJPY", SRC)
        self.assertNotIn("nz(autoJPYRate", SRC)

    def test_spread_not_assumed_free(self):
        self.assertIn("spreadConfigured = input.bool(false", SRC)
        self.assertIn("spreadConfigured ? selectedSpreadPips : na", SRC)
        self.assertIn("未設定（0コストではない）", SRC)
        self.assertIn("trailPips <= manualSpreadPips", SRC)
        self.assertNotIn("spEURSet", SRC)

    def test_table_bounds(self):
        rows = [int(v) for v in re.findall(r"f_row\(tb, (\d+),", SRC)]
        self.assertEqual(rows, list(range(19)))
        self.assertIn("table.new(tablePos, 2, 19,", SRC)
        self.assertIn("table.clear(tb, 0, 0, 1, 18)", SRC)
        tooltips = [int(v) for v in re.findall(r"table.cell_set_tooltip\(tb, 1, (\d+)", SRC)]
        self.assertTrue(all(0 <= x < 19 for x in tooltips))

    def test_text_copy_and_utf8(self):
        self.assertEqual(PINE.read_bytes(), PINE.with_suffix(".txt").read_bytes())
        self.assertNotIn("\ufffd", SRC)
        self.assertNotIn('"#.1"', SRC)

    def test_delimiters_outside_comments_strings(self):
        # Lexical balance only. This is explicitly not type checking or compilation.
        stack = []
        in_string = False
        escaped = False
        pairs = {")": "(", "]": "[", "}": "{"}
        for line in SRC.splitlines():
            i = 0
            while i < len(line):
                c = line[i]
                if in_string:
                    if escaped: escaped = False
                    elif c == "\\": escaped = True
                    elif c == '"': in_string = False
                else:
                    if line[i:i+2] == "//": break
                    if c == '"': in_string = True
                    elif c in "([{": stack.append(c)
                    elif c in ")]}":
                        self.assertTrue(stack, "Unmatched closing bracket")
                        self.assertEqual(stack.pop(), pairs[c])
                i += 1
            self.assertFalse(in_string, "Unexpected multiline quoted string")
        self.assertFalse(stack)

class ReferenceMath(unittest.TestCase):
    def test_one_pip_quote(self):
        self.assertAlmostEqual(3000 * 0.0001, 0.3)

    def test_twenty_pips_quote(self):
        self.assertAlmostEqual(3000 * 20 * 0.0001, 6.0)

    def test_other_widths_quote(self):
        for pips, expected in [(25,7.5),(50,15.0),(0.1,0.03)]:
            with self.subTest(pips=pips):
                self.assertAlmostEqual(3000 * pips * 0.0001, expected)

    def test_atr_rounding(self):
        self.assertAlmostEqual(width(0.00043), 10.8)
        self.assertAlmostEqual(width(0.0003084), 7.8)
        self.assertAlmostEqual(width(0.0008), 20.0)

    def test_fixed_and_floor_modes(self):
        self.assertAlmostEqual(width(0.0001, mode="fixed"), 20.0)
        self.assertAlmostEqual(width(0.0001, mode="floor"), 20.0)
        self.assertAlmostEqual(width(0.001, mode="floor"), 25.0)

    def test_atr_missing_or_zero(self):
        for atr in [None, 0.0]:
            self.assertIsNone(width(atr))
            self.assertIsNone(width(atr, mode="floor"))
            self.assertEqual(width(atr, mode="fixed"), 20.0)

    def test_manual_pip_override(self):
        self.assertAlmostEqual(width(0.00043, pip=0.001), 1.1)
        self.assertAlmostEqual(3000 * 20 * 0.001, 60.0)

    def test_hypothetical_yen_examples(self):
        # Arbitrary educational rates, not live rates.
        self.assertEqual(yen(6.0,14.0),84.0)
        self.assertEqual(yen(6.0,90.0),540.0)

    def test_conversion_modes(self):
        self.assertEqual(conversion("auto", auto=14.0, manual=99),14)
        self.assertEqual(conversion("manual", auto=14.0, manual=90),90)
        self.assertIsNone(conversion("off", auto=14.0, manual=90))

    def test_no_silent_fallback(self):
        self.assertIsNone(conversion("auto", auto=None, manual=90))
        self.assertIsNone(conversion("manual", auto=14, manual=0))
        self.assertIsNone(conversion("auto", auto=0))

    def test_no_zero_yen_on_missing(self):
        self.assertIsNone(yen(6,None))
        self.assertIsNone(yen(None,90))
        self.assertIsNone(yen(6,0))
        self.assertEqual(yen(0,90),0)

    def test_spread_cost(self):
        # Placeholder spread: the code does not claim it is current.
        self.assertAlmostEqual(3000 * 3.1 * 0.0001,0.93)

    def test_rounded_width_does_not_undershoot(self):
        for chosen in [0.1,1,1.001,7.71,10.75,20,25.123,200]:
            for step in [0.1,0.5,1.0]:
                actual=width(None, mode="fixed", fixed=chosen, step=step)
                self.assertGreaterEqual(actual+1e-8,chosen)
                self.assertLess(actual-chosen,step+1e-8)

if __name__ == "__main__":
    unittest.main(verbosity=2)

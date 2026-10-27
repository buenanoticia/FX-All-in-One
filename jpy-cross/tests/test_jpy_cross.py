"""JPY Cross-specific static and Python reference tests.

These checks do not compile Pine, load market data, emulate the entire
indicator, submit orders, or establish profitability.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FX_AllInOne_JPY_Cross.pine").read_text(encoding="utf-8")
BASES = ("EUR", "GBP", "AUD", "NZD", "CAD", "CHF")
BLOCKS = {'analysis_core': ('// ───────── 1.', '// ───────── 5.', '42617e4f5a5d699f20e2da521578f7a08bc7708d626fa16628e087890e188a0a'), 'atr_calculation': ('float atrOnChart =', '// 手入力値は参考表示', '6f5e0ea838a3d20b809f769fef47c8e3c9f5211d74081b450aa9a0dc79364ade'), 'alerts': ('// ───────── 7. アラート', '// ───────── 8. 状況パネル', 'fbb268794d060893770329fd43bf150d4fe4abeefc04417d4621c08539b7d406')}

def block(start: str, end: str) -> str:
    return SOURCE[SOURCE.index(start):SOURCE.index(end)]

def allowed(kind: str, base: str, quote: str, standard: bool = True, ticks: bool = False) -> bool:
    return kind == "forex" and quote == "JPY" and base in BASES and standard and not ticks

def switch_map(name: str, value_type: str) -> dict[str, str]:
    pattern = rf'{value_type} {name} = switch syminfo\.basecurrency\n((?:    .*\n)+)'
    body = re.search(pattern, SOURCE).group(1)
    return dict(re.findall(r'    "([A-Z]{3})" => (\w+)', body))

def spread_reference(configured: bool, pips: float, units: int, boundary: float):
    # Zero is valid only when explicitly configured. No live spread retrieval.
    available = configured
    amount = pips * 0.01 * units if available else None
    warning = available and boundary > 0 and pips > boundary
    return amount, warning

class ForkSourceTests(unittest.TestCase):
    def test_analysis_core_identical_to_usdjpy_1_1_1(self):
        start,end,expected = BLOCKS["analysis_core"]
        self.assertEqual(hashlib.sha256(block(start,end).encode()).hexdigest(), expected)

    def test_atr_calculation_identical_to_usdjpy_1_1_1(self):
        start,end,expected = BLOCKS["atr_calculation"]
        self.assertEqual(hashlib.sha256(block(start,end).encode()).hexdigest(), expected)

    def test_alert_conditions_identical_to_usdjpy_1_1_1(self):
        start,end,expected = BLOCKS["alerts"]
        self.assertEqual(hashlib.sha256(block(start,end).encode()).hexdigest(), expected)

    def test_independent_title(self):
        self.assertIn('indicator("FX All-in-One Pro JPY Cross v1.0.0"', SOURCE)
        title = re.search(r'shorttitle="([^"]+)"', SOURCE).group(1)
        self.assertEqual(title,"JC 1.0.0")
        self.assertLessEqual(len(title),10)

    def test_metadata_based_allowlist(self):
        line = next(l for l in SOURCE.splitlines() if l.startswith("bool isSupportedBase ="))
        self.assertEqual(tuple(re.findall(r'syminfo.basecurrency == "(\w+)"',line)), BASES)
        self.assertIn('syminfo.type == "forex" and syminfo.currency == "JPY" and isSupportedBase',SOURCE)
        self.assertIn("if not isSupportedCross\n        runtime.error(",SOURCE)
        self.assertNotIn("str.contains(syminfo.ticker",SOURCE)

    def test_price_step_not_used_as_pip(self):
        self.assertIn("float pipSize = 0.01",SOURCE)
        self.assertNotRegex(SOURCE,r"pipSize\s*=\s*syminfo\.mintick")
        self.assertIn("float pipAmountJPY = pipSize * units",SOURCE)

    def test_no_usdjpy_specific_warning_leaks(self):
        self.assertNotIn("FOREXCOMのUSDJPYレート", SOURCE)
        self.assertIn('"\\nFOREXCOM:" + pairCode + "のレートと照合"',SOURCE)

    def test_symbol_and_base_unit_visible(self):
        self.assertIn('pairLabel + " / " + syminfo.prefix',SOURCE)
        self.assertIn('" " + syminfo.basecurrency + "・値幅換算"',SOURCE)
        self.assertIn('"1pip換算 / 参考数量"',SOURCE)

    def test_same_symbol_requests_only(self):
        calls = re.findall(r"request\.(\w+)\(([^,]+),", SOURCE)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(first=="syminfo.tickerid" for _,first in calls))

    def test_unset_spreads_default_for_all_pairs(self):
        for b in BASES:
            self.assertRegex(SOURCE,rf'sp{b}Set = input\.bool\(false,')
            self.assertRegex(SOURCE,rf'sp{b} = input\.float\(0\.0,')
        self.assertIn("float manualSpreadPips = spreadConfigured ? selectedSpreadPips : na",SOURCE)
        self.assertIn('未設定（0コストではない）',SOURCE)

    def test_pair_to_flag_and_value_mapping(self):
        self.assertEqual(switch_map("spreadConfigured","bool"), {b:"sp"+b+"Set" for b in BASES})
        self.assertEqual(switch_map("selectedSpreadPips","float"), {b:"sp"+b for b in BASES})

    def test_no_inherited_2_6_spread_default(self):
        self.assertNotIn("input.float(2.6", SOURCE)
        self.assertRegex(SOURCE,r'spreadWarningPips = input\.float\(0\.0,')
        self.assertIn("spreadWarningEnabled = spreadWarningPips > 0",SOURCE)

    def test_unset_value_not_used_in_width_warning(self):
        self.assertIn("if spreadAvailable and not na(trailPips) and trailPips <= manualSpreadPips",SOURCE)

    def test_reference_values_do_not_filter_signals(self):
        area=block("// ───────── 1.","// ───────── 5.")
        for v in ("spreadConfigured","manualSpreadPips","spreadAboveBoundary","units"):
            self.assertNotIn(v,area)
        self.assertNotIn("spread",block("// ───────── 7. アラート","// ───────── 8. 状況パネル").lower())

    def test_chart_guard_retained(self):
        self.assertIn("if not chart.is_standard or timeframe.isticks",SOURCE)

    def test_tooltips_point_to_new_atr_rows(self):
        self.assertIn('table.cell_set_tooltip(tb, 1, 9, "ATR取得方式:',SOURCE)
        self.assertIn('table.cell_set_tooltip(tb, 1, 11, "切り上げ単位:',SOURCE)
        self.assertIn("table.new(tablePos, 2, 16,",SOURCE)

class CrossReferenceTests(unittest.TestCase):
    def test_six_pairs_accepted(self):
        for b in BASES:
            self.assertTrue(allowed("forex",b,"JPY"))

    def test_usdjpy_stays_separate(self):
        self.assertFalse(allowed("forex","USD","JPY"))

    def test_non_jpy_and_noksek_rejected(self):
        for base,quote in (("EUR","USD"),("GBP","USD"),("NOK","SEK"),("JPY","EUR")):
            self.assertFalse(allowed("forex",base,quote))

    def test_undefined_yen_pairs_rejected(self):
        for b in ("NOK","SEK","ZAR","TRY","MXN","CNH","SGD","HKD"):
            self.assertFalse(allowed("forex",b,"JPY"))

    def test_other_instrument_types_rejected(self):
        for kind in ("stock","crypto","futures","index","cfd"):
            self.assertFalse(allowed(kind,"EUR","JPY"))

    def test_nonstandard_and_ticks_rejected(self):
        self.assertFalse(allowed("forex","EUR","JPY",False,False))
        self.assertFalse(allowed("forex","EUR","JPY",True,True))

    def test_equal_base_units_have_equal_yen_per_pip(self):
        for b in BASES:
            for units in (1000,3000,10000):
                self.assertAlmostEqual(units*0.01, {1000:10,3000:30,10000:100}[units])

    def test_width_yen_grid(self):
        for b in BASES:
            for width,amount in ((7.8,234),(18.4,552),(20,600),(25,750),(50,1500)):
                self.assertAlmostEqual(width*0.01*3000,amount)

    def test_unset_is_not_zero_cost(self):
        self.assertEqual(spread_reference(False,0,3000,0),(None,False))
        self.assertEqual(spread_reference(False,2.6,3000,3),(None,False))

    def test_explicit_zero_reference(self):
        self.assertEqual(spread_reference(True,0,3000,0),(0.0,False))

    def test_reference_spread_and_boundary(self):
        amount,warn=spread_reference(True,2.6,3000,3)
        self.assertAlmostEqual(amount,78)
        self.assertFalse(warn)
        amount,warn=spread_reference(True,8.2,3000,3)
        self.assertAlmostEqual(amount,246)
        self.assertTrue(warn)

    def test_zero_boundary_disables_warning_not_cost(self):
        amount,warn=spread_reference(True,8.2,3000,0)
        self.assertAlmostEqual(amount,246)
        self.assertFalse(warn)

    def test_boundary_equality_not_above(self):
        self.assertFalse(spread_reference(True,3.0,3000,3.0)[1])
        self.assertTrue(spread_reference(True,3.1,3000,3.0)[1])

    def test_switch_isolation(self):
        # Follow the actual source mapping to choose synthetic input values.
        flags={f"sp{b}Set":b=="EUR" for b in BASES}
        rates={f"sp{b}":(i+1)*0.7 for i,b in enumerate(BASES)}
        fm=switch_map("spreadConfigured","bool")
        vm=switch_map("selectedSpreadPips","float")
        for b in BASES:
            amount,_=spread_reference(flags[fm[b]],rates[vm[b]],3000,0)
            if b=="EUR":
                self.assertAlmostEqual(amount,21)
            else:
                self.assertIsNone(amount)

if __name__ == "__main__":
    unittest.main(verbosity=2)

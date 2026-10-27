"""Static and Python reference checks for the historical-buffer hotfix.

These tests do NOT run Pine or emulate TradingView's drawing engine.
The bounded-offset model only checks the source's retention rules.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FX_AllInOne_USDJPY_v1_1_1.pine").read_text(encoding="utf-8")
BASELINE_SHA256 = "934a36aaef88461d0f88e907fbc0cb033e77640bf127203e52a6cd54f617150a"
BUFFER_BLOCK = """// v1.1.1: S/Rの過去座標描画は、内部でtime系列の履歴を参照します。
// srLookbackの上限4900本（境界を含む）をカバーするため、timeだけを事前確保します。
// 全系列の一括拡張や、探索期間・売買条件の変更は行いません。
max_bars_back(time, 5000)

"""


def retained_bars(current: int, lookback: int, pivot_bars: list[int]) -> list[int]:
    """Reference model of the existing strict-less-than eviction rule."""
    return [b for b in pivot_bars if b >= current - lookback]


def reference_buffer_read(offset: int, limit: int) -> int:
    """Simplified limit model, not the Pine runtime."""
    if offset < 0 or offset > limit:
        raise IndexError("reference model: historical buffer exceeded")
    return offset


class HistoryBufferHotfixTests(unittest.TestCase):
    def test_time_buffer_is_global_and_unique(self):
        declarations = re.findall(r"(?m)^max_bars_back\(time,\s*(\d+)\)$", SOURCE)
        self.assertEqual(declarations, ["5000"])
        self.assertLess(SOURCE.index("max_bars_back(time, 5000)"), SOURCE.index("if barstate.isfirst"))
        self.assertLess(SOURCE.index("max_bars_back(time, 5000)"), SOURCE.index("line.new("))

    def test_no_all_series_buffer_expansion(self):
        declaration = next(line for line in SOURCE.splitlines() if line.startswith("indicator("))
        self.assertNotIn("max_bars_back=", declaration)
        self.assertEqual(len(re.findall(r"(?m)^max_bars_back\(", SOURCE)), 1)

    def test_buffer_covers_existing_maximum_lookback(self):
        setting = next(line for line in SOURCE.splitlines() if line.startswith("srLookback ="))
        maximum = int(re.search(r"maxval=(\d+)", setting).group(1))
        buffer_size = int(re.search(r"(?m)^max_bars_back\(time, (\d+)\)", SOURCE).group(1))
        self.assertEqual(maximum, 4900)
        self.assertGreaterEqual(buffer_size, maximum)

    def test_existing_eviction_rule_is_still_in_source(self):
        self.assertIn(
            "while array.size(srBars) > 0 and array.get(srBars, 0) < bar_index - srLookback",
            SOURCE,
        )

    def test_reported_299_300_boundary_model(self):
        with self.assertRaises(IndexError):
            reference_buffer_read(300, 299)
        self.assertEqual(reference_buffer_read(300, 5000), 300)

    def test_inclusive_lookback_boundary_model(self):
        for lookback in (50, 299, 300, 301, 1000, 4900):
            with self.subTest(lookback=lookback):
                current = 6000
                points = [current-lookback-1, current-lookback, current-lookback+1, current]
                kept = retained_bars(current, lookback, points)
                self.assertEqual(kept[0], current-lookback)
                self.assertNotIn(current-lookback-1, kept)
                for point in kept:
                    reference_buffer_read(current-point, 5000)

    def test_aging_pivots_stay_within_reserved_history_model(self):
        # A new bar ages a retained pivot by one. Once it is outside lookback,
        # the existing prune rule removes it before the drawing block.
        for lookback in (50, 300, 4900):
            with self.subTest(lookback=lookback):
                old_pivot = 100
                for current in (old_pivot+lookback-1, old_pivot+lookback, old_pivot+lookback+1):
                    kept = retained_bars(current, lookback, [old_pivot, current-10])
                    for point in kept:
                        reference_buffer_read(current-point, 5000)
                    if current-old_pivot > lookback:
                        self.assertNotIn(old_pivot, kept)

    def test_pivot_label_past_offsets_fit_buffer(self):
        line = next(line for line in SOURCE.splitlines() if line.startswith("dowLen "))
        maximum = int(re.search(r"maxval=(\d+)", line).group(1))
        self.assertEqual(maximum, 100)
        self.assertIn("labelsAtPivot ? pivotBar : bar_index", SOURCE)
        self.assertLessEqual(maximum, 5000)

    def test_only_metadata_and_buffer_block_changed(self):
        self.assertEqual(SOURCE.count(BUFFER_BLOCK), 1)
        restored = SOURCE.replace(BUFFER_BLOCK, "", 1)
        restored = restored.replace('v1.1.1', 'v1.1.0').replace(
            'shorttitle="UJ 1.1.1"', 'shorttitle="AIO UJ 1.1"')
        self.assertEqual(hashlib.sha256(restored.encode("utf-8")).hexdigest(), BASELINE_SHA256)

    def test_revision_title_is_distinct_and_short(self):
        self.assertIn('indicator("FX All-in-One Pro USDJPY v1.1.1"', SOURCE)
        title = re.search(r'shorttitle="([^"]+)"', SOURCE).group(1)
        self.assertEqual(title, "UJ 1.1.1")
        self.assertLessEqual(len(title), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)

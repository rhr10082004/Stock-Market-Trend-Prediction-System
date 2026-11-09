import datetime as dt
import json
import unittest
from unittest.mock import patch

from api._lib import market as index


def example_series(symbol="SPY"):
    start = dt.datetime(2026, 8, 1, 14, tzinfo=dt.timezone.utc)
    bars = []
    for i in range(40):
        day = start + dt.timedelta(days=i)
        price = 100 + i * 0.25
        bars.append({"date": day.isoformat(), "open": price - .1, "high": price + .5,
                     "low": price - .4, "close": price, "volume": 1200000})
    return {"symbol": symbol, "meta": {"regularMarketPrice": 110, "chartPreviousClose": 109,
                                         "currency": "USD", "exchangeName": "NMS"}, "bars": bars}


class InputValidation(unittest.TestCase):
    def test_symbol_list_is_normalized_deduplicated_and_limited(self):
        self.assertEqual(index.checked_symbols(" spy,SPY,qqq "), ["SPY", "QQQ"])
        with self.assertRaises(index.ApiError):
            index.checked_symbols("SPY;DROP")

    def test_invalid_range_rejected_before_fetch(self):
        with self.assertRaisesRegex(index.ApiError, "Choose one"):
            index.dispatch("/api/history", {"symbols": ["SPY"], "range": ["max"]})

    def test_unknown_symbols_are_not_filled_with_samples(self):
        with patch.object(index, "read_spark", return_value={}):
            with self.assertRaisesRegex(index.ApiError, "No market history"):
                index.dispatch("/api/market", {"symbols": ["ZZZZ"]})


class Calculations(unittest.TestCase):
    def test_wilder_rsi_is_bounded(self):
        values = [float(i) for i in range(20)]
        self.assertEqual(index.rsi(values), 100.0)
        self.assertIsNone(index.rsi([1, 2, 3]))

    def test_daily_scan_returns_observed_closes_and_descriptive_tags(self):
        result = index.daily_setups(example_series())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 109.75)
        self.assertIn("20-day closing-high breakout", result["setups"])

    def test_history_shape_and_provider_label(self):
        with patch.object(index, "read_spark", return_value={"SPY": example_series()}):
            result = index.dispatch("/api/history", {"symbols": ["SPY"], "range": ["3mo"]})
        self.assertIn("unofficial", result["provider"])
        self.assertEqual(result["symbol"], "SPY")
        self.assertGreater(len(result["bars"]), 30)
        self.assertEqual(result["quote"]["price"], 110)

    def test_scan_has_no_recommendation_claim(self):
        with patch.object(index, "read_spark", return_value={"SPY": example_series()}):
            result = index.dispatch("/api/scan", {"symbols": ["SPY"]})
        self.assertEqual(result["scanned"], 1)
        self.assertIn("not buy or sell recommendations", result["note"])
        self.assertTrue(result["hits"])


if __name__ == "__main__":
    unittest.main()

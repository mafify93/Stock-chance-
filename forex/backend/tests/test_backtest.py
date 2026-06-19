"""Tests for the auto-trader backtester.

The key thing under test is honesty about cost: the backtester must charge the
full spread on every trade, so a wider spread can only ever reduce net P&L.
"""
import numpy as np
import pandas as pd

from app.autotrader.backtest import run_backtest, simulate_pair, summarize
from app.autotrader.config import AutoTraderConfig
from app.autotrader.engine import h1_blocks_trade


def _h1_frame(n: int = 300, slope: float = 0.0006, start: str = "2024-03-01 00:00") -> pd.DataFrame:
    """Synthetic H1 history with a steady drift (for the trend filter)."""
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    close = 1.1000 + np.cumsum(np.full(n, slope))
    return pd.DataFrame(
        {
            "Open": close - 0.0002,
            "High": close + 0.0006,
            "Low": close - 0.0006,
            "Close": close,
            "Volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def _trending_m5(n: int = 600, slope: float = 0.0008, start: str = "2024-03-04 07:00") -> pd.DataFrame:
    """A clean intraday uptrend across several London/NY sessions.

    Monday 2024-03-04 07:00 UTC onward (London open) so the session gate lets
    trades through.
    """
    idx = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    # Gentle upward drift with mild noise — produces EMA-cross buy signals.
    base = 1.1000 + np.cumsum(np.full(n, slope / 50))
    noise = np.sin(np.linspace(0, 60, n)) * 0.0006
    close = base + noise
    return pd.DataFrame(
        {
            "Open": close - 0.0001,
            "High": close + 0.0004,
            "Low": close - 0.0004,
            "Close": close,
            "Volume": np.full(n, 1000.0),
        },
        index=idx,
    )


class TestSimulatePair:
    def test_runs_and_returns_trades(self):
        cfg = AutoTraderConfig()
        cfg.session_filter = False  # take the trend out of session-gating
        df = _trending_m5()
        trades, ending_nav = simulate_pair("EUR_USD", df, cfg, spread_pips=1.0, starting_nav=1000.0)
        assert isinstance(trades, list)
        assert ending_nav > 0
        # Every trade's net pips must be exactly gross minus the spread.
        for t in trades:
            assert abs(t.net_pips - (t.gross_pips - 1.0)) < 0.05

    def test_wider_spread_never_helps(self):
        cfg = AutoTraderConfig()
        cfg.session_filter = False
        df = _trending_m5()
        _, nav_tight = simulate_pair("EUR_USD", df, cfg, spread_pips=0.5, starting_nav=1000.0)
        _, nav_wide = simulate_pair("EUR_USD", df, cfg, spread_pips=4.0, starting_nav=1000.0)
        # More spread cost can only reduce (or equal) the ending balance.
        assert nav_wide <= nav_tight

    def test_daily_trade_cap_respected(self):
        cfg = AutoTraderConfig()
        cfg.session_filter = False
        cfg.max_trades_per_day = 1
        df = _trending_m5(n=600)
        trades, _ = simulate_pair("EUR_USD", df, cfg, spread_pips=1.0, starting_nav=1000.0)
        by_day: dict = {}
        for t in trades:
            day = t.entry_time[:10]
            by_day[day] = by_day.get(day, 0) + 1
        assert all(c <= 1 for c in by_day.values())


class TestSummarize:
    def test_empty(self):
        stats = summarize("EUR_USD", [], 1000.0, 1000.0)
        assert stats.trades == 0
        assert stats.expectancy_pips == 0.0

    def test_expectancy_is_net_pips_over_trades(self):
        cfg = AutoTraderConfig()
        cfg.session_filter = False
        df = _trending_m5()
        trades, ending = simulate_pair("EUR_USD", df, cfg, spread_pips=1.0, starting_nav=1000.0)
        stats = summarize("EUR_USD", trades, 1000.0, ending)
        if stats.trades:
            assert abs(stats.expectancy_pips - stats.net_pips / stats.trades) < 0.05


class TestRunBacktest:
    def test_full_run_shape(self):
        cfg = AutoTraderConfig()
        cfg.session_filter = False
        candles = {"EUR_USD": _trending_m5(), "GBP_USD": _trending_m5(slope=0.0006)}
        spreads = {"EUR_USD": 1.0, "GBP_USD": 1.4}
        result = run_backtest(candles, cfg, spreads, starting_nav=1000.0)
        assert "overall" in result
        assert "per_pair" in result
        assert result["starting_nav"] == 1000.0
        assert len(result["per_pair"]) == 2
        assert result["overall"]["trades"] >= 0


class TestH1TrendFilter:
    def test_h1_blocks_trade_logic(self):
        # Counter-trend entries are blocked; aligned/neutral/no-data are allowed.
        assert h1_blocks_trade("DAY_BUY", -0.5) is True      # buy into a downtrend
        assert h1_blocks_trade("DAY_SELL", 0.5) is True      # sell into an uptrend
        assert h1_blocks_trade("DAY_BUY", 0.5) is False      # buy with uptrend
        assert h1_blocks_trade("DAY_SELL", -0.5) is False    # sell with downtrend
        assert h1_blocks_trade("DAY_BUY", 0.0) is False      # neutral H1
        assert h1_blocks_trade("DAY_BUY", None) is False     # no H1 data

    def test_filter_never_adds_trades(self):
        # On identical data, the H1 filter can only remove trades, never add.
        df = _trending_m5()
        h1 = _h1_frame()

        cfg_off = AutoTraderConfig()
        cfg_off.session_filter = False
        cfg_off.h1_trend_filter = False
        trades_off, _ = simulate_pair("EUR_USD", df, cfg_off, 1.0, 1000.0, h1_df=h1)

        cfg_on = AutoTraderConfig()
        cfg_on.session_filter = False
        cfg_on.h1_trend_filter = True
        trades_on, _ = simulate_pair("EUR_USD", df, cfg_on, 1.0, 1000.0, h1_df=h1)

        assert len(trades_on) <= len(trades_off)

    def test_no_h1_data_is_a_noop(self):
        # Filter on but no H1 frame supplied → behaves exactly like filter off.
        df = _trending_m5()

        cfg_off = AutoTraderConfig()
        cfg_off.session_filter = False
        cfg_off.h1_trend_filter = False
        trades_off, _ = simulate_pair("EUR_USD", df, cfg_off, 1.0, 1000.0)

        cfg_on = AutoTraderConfig()
        cfg_on.session_filter = False
        cfg_on.h1_trend_filter = True
        trades_on, _ = simulate_pair("EUR_USD", df, cfg_on, 1.0, 1000.0)

        assert len(trades_on) == len(trades_off)

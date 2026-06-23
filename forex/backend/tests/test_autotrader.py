"""Tests for auto-trader risk, config, and state modules."""
import asyncio

import pytest

from app.autotrader.risk import calculate_units, expected_value, fractional_kelly
from app.autotrader.config import AutoTraderConfig
from app.autotrader.state import BotState, TradeRecord


# ── calculate_units ───────────────────────────────────────────────────────────

class TestCalculateUnits:
    def test_eur_usd_basic(self):
        # $200 account, 1% risk, 20-pip stop, EUR/USD (pip_value=0.0001)
        # risk_amount = 200 * 0.01 = $2
        # units = 2 / (20 * 0.0001) = 2 / 0.002 = 1000
        units = calculate_units(nav=200, risk_pct=0.01, stop_pips=20,
                                pair="EUR_USD", spot_price=1.08)
        assert units == 1000

    def test_usd_jpy_uses_spot(self):
        # $200 account, 1% risk, 20-pip stop, USD/JPY at 150.0
        # pip_value = 0.01 / 150 ≈ 0.0000667
        # risk_amount = $2; units = 2 / (20 * 0.0000667) ≈ 1500
        units = calculate_units(nav=200, risk_pct=0.01, stop_pips=20,
                                pair="USD_JPY", spot_price=150.0)
        expected = int(2.0 / (20 * (0.01 / 150.0)))
        assert units == expected

    def test_higher_nav_scales_units(self):
        # Use stop=20 so risk/stop divides evenly: 2/(20*0.0001)=1000, 40/(20*0.0001)=20000
        units_200 = calculate_units(nav=200, risk_pct=0.01, stop_pips=20, pair="GBP_USD")
        units_4000 = calculate_units(nav=4000, risk_pct=0.01, stop_pips=20, pair="GBP_USD")
        assert units_4000 == units_200 * 20

    def test_tighter_stop_gives_more_units(self):
        units_tight = calculate_units(nav=200, risk_pct=0.01, stop_pips=10, pair="EUR_USD")
        units_wide = calculate_units(nav=200, risk_pct=0.01, stop_pips=20, pair="EUR_USD")
        assert units_tight > units_wide

    def test_degenerate_inputs_return_zero(self):
        assert calculate_units(nav=0, risk_pct=0.01, stop_pips=20, pair="EUR_USD") == 0
        assert calculate_units(nav=200, risk_pct=0, stop_pips=20, pair="EUR_USD") == 0
        assert calculate_units(nav=200, risk_pct=0.01, stop_pips=0, pair="EUR_USD") == 0
        assert calculate_units(nav=-100, risk_pct=0.01, stop_pips=20, pair="EUR_USD") == 0

    def test_minimum_one_unit(self):
        # Tiny nav + large stop should still return at least 1
        units = calculate_units(nav=1, risk_pct=0.001, stop_pips=100, pair="EUR_USD")
        assert units >= 1


# ── expected_value ────────────────────────────────────────────────────────────

class TestExpectedValue:
    def test_positive_ev_with_2r(self):
        # 40% win rate, 2:1 R/R: EV = 0.01*(0.40*2 - 0.60) = 0.01*0.20 = +0.002
        ev = expected_value(win_rate=0.40, rr_ratio=2.0, risk_pct=0.01)
        assert ev == pytest.approx(0.002)

    def test_breakeven_at_33pct_win_2r(self):
        # ~33.3% win rate breaks even at 2:1
        ev = expected_value(win_rate=1 / 3, rr_ratio=2.0, risk_pct=0.01)
        assert ev == pytest.approx(0.0, abs=1e-10)

    def test_negative_ev_below_breakeven(self):
        ev = expected_value(win_rate=0.30, rr_ratio=2.0, risk_pct=0.01)
        assert ev < 0

    def test_higher_rr_improves_ev(self):
        ev_2r = expected_value(win_rate=0.40, rr_ratio=2.0, risk_pct=0.01)
        ev_3r = expected_value(win_rate=0.40, rr_ratio=3.0, risk_pct=0.01)
        assert ev_3r > ev_2r


# ── fractional_kelly ──────────────────────────────────────────────────────────

class TestFractionalKelly:
    def test_returns_positive_for_positive_ev(self):
        fk = fractional_kelly(win_rate=0.50, rr_ratio=2.0)
        assert fk > 0

    def test_zero_for_zero_edge(self):
        # 33% win rate at 2:1 = zero edge
        fk = fractional_kelly(win_rate=1 / 3, rr_ratio=2.0)
        assert fk == pytest.approx(0.0, abs=1e-10)

    def test_clamped_at_zero_for_negative_ev(self):
        fk = fractional_kelly(win_rate=0.20, rr_ratio=2.0)
        assert fk == 0.0

    def test_quarter_kelly_fraction(self):
        # Full Kelly: f* = (W*R - (1-W)) / R = (0.5*2 - 0.5)/2 = 0.5/2 = 0.25
        # Quarter Kelly: 0.25 * 0.25 = 0.0625
        fk = fractional_kelly(win_rate=0.50, rr_ratio=2.0, fraction=0.25)
        assert fk == pytest.approx(0.0625)


# ── AutoTraderConfig ──────────────────────────────────────────────────────────

class TestAutoTraderConfig:
    def test_defaults(self):
        cfg = AutoTraderConfig()
        assert cfg.risk_pct == pytest.approx(0.01)
        assert cfg.rr_ratio == pytest.approx(2.0)
        assert cfg.max_positions == 2
        assert cfg.max_trades_per_day == 5
        assert cfg.session_filter is True
        assert "EUR_USD" in cfg.pairs

    def test_custom_values(self):
        cfg = AutoTraderConfig(risk_pct=0.02, max_positions=4)
        assert cfg.risk_pct == pytest.approx(0.02)
        assert cfg.max_positions == 4


# ── BotState ──────────────────────────────────────────────────────────────────

class TestBotState:
    def test_initial_state(self):
        state = BotState()
        assert state.running is False
        assert state.halted is False
        assert state.daily_pl == 0.0
        assert state.consecutive_losses == 0
        assert state.risk_scale == 1.0

    def test_open_trades_property(self):
        state = BotState()
        t1 = TradeRecord(pair="EUR_USD", side="long", units=1000,
                         entry=1.08, stop=1.078, target=1.084,
                         opened_at="2024-01-01T10:00:00", trade_id="T1", status="open")
        t2 = TradeRecord(pair="GBP_USD", side="short", units=500,
                         entry=1.27, stop=1.272, target=1.266,
                         opened_at="2024-01-01T11:00:00", trade_id="T2", status="closed")
        state.trades = [t1, t2]
        assert len(state.open_trades) == 1
        assert state.open_trades[0].trade_id == "T1"

    def test_base_url_practice(self):
        state = BotState()
        state.environment = "practice"
        assert "practice" in state.base_url

    def test_base_url_live(self):
        state = BotState()
        state.environment = "live"
        assert "fxtrade.oanda.com" in state.base_url

    def test_trade_record_fields(self):
        t = TradeRecord(pair="EUR_USD", side="long", units=1000,
                        entry=1.0800, stop=1.0780, target=1.0840,
                        opened_at="2024-01-01T10:00:00Z", trade_id="123", status="open")
        assert t.pair == "EUR_USD"
        assert t.status == "open"
        assert t.realized_pl is None
        assert t.partial_closed is False
        assert t.init_risk == 0.0


# ── Trade management: time-decay stop & init_risk anchoring ────────────────────

class TestTimeDecayStop:
    """The time-decay stop tightens a stale losing trade instead of closing it."""

    def _setup(self, monkeypatch, hours_open, mid, partial_closed=False):
        """Wire up bot_state with one open long EUR/USD trade and stub OANDA.

        Returns (trade, calls) where calls records every stop-loss update so the
        test can assert the new stop level. No market-close should ever fire.
        """
        from datetime import datetime, timedelta, timezone
        from app.autotrader import engine
        from app.autotrader.state import bot_state

        opened = datetime.now(timezone.utc) - timedelta(hours=hours_open)
        trade = TradeRecord(
            pair="EUR_USD", side="long", units=1000,
            entry=1.10000, stop=1.09800, target=1.10400,
            opened_at=opened.isoformat(), trade_id="T1", status="open",
            init_risk=0.00200,  # 20 pips
            partial_closed=partial_closed,
        )
        bot_state.running = True
        bot_state.token = "tok"
        bot_state.account_id = "acc"
        bot_state.environment = "practice"
        bot_state.trades = [trade]
        bot_state.config = AutoTraderConfig()

        calls = {"stop_updates": [], "closes": []}

        async def fake_to_thread(fn, *args, **kwargs):
            name = getattr(fn, "__name__", "")
            if name == "get_pricing":
                return {"EUR_USD": {"mid": mid}}
            if name == "update_trade_stop_loss":
                calls["stop_updates"].append(args[3])  # new SL price
                return {}
            if name == "close_position":
                calls["closes"].append(args)
                return {}
            return {}

        monkeypatch.setattr(engine.asyncio, "to_thread", fake_to_thread)
        return engine, trade, calls

    def test_no_tighten_before_decay_window(self, monkeypatch):
        # 1h open, max_trade_hours=3 → decay starts at 1.5h, so nothing yet.
        engine, trade, calls = self._setup(monkeypatch, hours_open=1.0, mid=1.09850)
        asyncio.run(engine.monitor_open_trades())
        assert calls["stop_updates"] == []
        assert calls["closes"] == []  # never market-closes

    def test_tightens_stop_when_stale_and_losing(self, monkeypatch):
        # 3h open (full decay), still red → stop pulled in to 25% of 20-pip risk
        # = 5 pips below entry → 1.09950. Never closes the position.
        engine, trade, calls = self._setup(monkeypatch, hours_open=3.0, mid=1.09850)
        asyncio.run(engine.monitor_open_trades())
        assert calls["closes"] == []
        assert len(calls["stop_updates"]) == 1
        assert calls["stop_updates"][0] == pytest.approx(1.09950, abs=1e-5)

    def test_no_decay_once_partial_closed(self, monkeypatch):
        # A trade that already banked partial profit is owned by break-even logic.
        engine, trade, calls = self._setup(
            monkeypatch, hours_open=3.0, mid=1.09850, partial_closed=True
        )
        asyncio.run(engine.monitor_open_trades())
        # mid is below entry so profit<0; partial_closed must suppress decay,
        # and there's no profit to trigger break-even either.
        assert calls["stop_updates"] == []
        assert calls["closes"] == []


class TestRunnerTrailing:
    """At >=1R profit the runner takes a partial and trails on ATR above BE."""

    def _setup(self, monkeypatch, mid, highest_high):
        from datetime import datetime, timedelta, timezone
        import pandas as pd
        from app.autotrader import engine
        from app.autotrader.state import bot_state

        now = datetime.now(timezone.utc)
        opened = now - timedelta(hours=1)
        trade = TradeRecord(
            pair="EUR_USD", side="long", units=2000,
            entry=1.10000, stop=1.09800, target=1.10400,
            opened_at=opened.isoformat(), trade_id="T1", status="open",
            init_risk=0.00200,  # 20 pips → 1R
        )
        bot_state.running = True
        bot_state.token = "tok"
        bot_state.account_id = "acc"
        bot_state.environment = "practice"
        bot_state.trades = [trade]
        bot_state.config = AutoTraderConfig()

        # Tight 1-pip-range candles after entry, with a designed swing high so the
        # ATR is small and the Chandelier trail lands above break-even.
        idx = [now - timedelta(minutes=5 * (30 - i)) for i in range(30)]
        closes = [1.10000 + 0.00010 * i for i in range(30)]
        df = pd.DataFrame(
            {
                "Open": closes,
                "High": [c + 0.00010 for c in closes[:-1]] + [highest_high],
                "Low": [c - 0.00010 for c in closes],
                "Close": closes,
                "Volume": [100] * 30,
            },
            index=pd.DatetimeIndex(idx),
        )

        calls = {"stop_updates": [], "partials": [], "closes": []}

        async def fake_to_thread(fn, *args, **kwargs):
            name = getattr(fn, "__name__", "")
            if name == "get_pricing":
                return {"EUR_USD": {"mid": mid}}
            if name == "get_candles":
                return df
            if name == "close_trade_partial":
                calls["partials"].append(args[3])  # units closed
                return {}
            if name == "update_trade_stop_loss":
                calls["stop_updates"].append(args[3])  # new SL
                return {}
            if name in ("close_position", "close_trade"):
                calls["closes"].append(args)
                return {}
            return {}

        monkeypatch.setattr(engine.asyncio, "to_thread", fake_to_thread)
        return engine, trade, calls

    def test_partial_then_trail_above_breakeven(self, monkeypatch):
        # mid = 1.5R profit; designed swing high 1.10400 with tight ranges.
        engine, trade, calls = self._setup(monkeypatch, mid=1.10300, highest_high=1.10400)
        asyncio.run(engine.monitor_open_trades())
        # Took a partial (half of 2000 units) and never market-closed.
        assert calls["partials"] == [1000]
        assert calls["closes"] == []
        # Two stop updates: early 0.5R breakeven fires first, then ATR trail.
        assert len(calls["stop_updates"]) == 2
        be_sl = calls["stop_updates"][0]
        trail_sl = calls["stop_updates"][1]
        assert be_sl == pytest.approx(1.10010, abs=1e-5)  # entry + 1 pip (breakeven)
        assert 1.10010 < trail_sl < 1.10400                # ATR trail above BE

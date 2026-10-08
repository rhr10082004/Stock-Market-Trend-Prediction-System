"""Yahoo Finance daily market data. No synthetic or bundled-price fallback."""
from functools import lru_cache

import pandas as pd

SYMBOLS = {"NIFTY50": "^NSEI"}
RANGES = {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y", "5y": "5y", "study": "max"}


class MarketDataUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=8)
def _download(symbol: str, period: str) -> pd.DataFrame:
    try:
        import yfinance as yf
        frame = yf.download(symbol, period=period, interval="1d", auto_adjust=True,
                            progress=False, threads=False, timeout=20)
    except Exception as exc:
        raise MarketDataUnavailable("Yahoo Finance could not be reached. Try again later.") from exc
    if frame is None or frame.empty:
        raise MarketDataUnavailable("Yahoo Finance returned no daily observations for NIFTY 50.")
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(c).lower().replace(" ", "_") for c in frame.columns]
    required = {"open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise MarketDataUnavailable("Market data provider returned an incomplete OHLC series.")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in frame:
            frame[col] = 0.0
    frame = frame[list(required | {"volume"})].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"]).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    if period == "max":
        frame = frame.loc["2010-01-01":]
    if frame.empty:
        raise MarketDataUnavailable("No observations are available for the requested date range.")
    return frame


def history(symbol="NIFTY50", period="1y"):
    if symbol != "NIFTY50" or period not in RANGES:
        raise ValueError("Supported series: NIFTY50; ranges: 1mo, 3mo, 6mo, 1y, 5y, study.")
    data = _download(SYMBOLS[symbol], RANGES[period]).copy()
    return data


def history_payload(symbol="NIFTY50", period="1y"):
    frame = history(symbol, period)
    rows = [{"date": ix.strftime("%Y-%m-%d"), "open": float(r.open), "high": float(r.high),
             "low": float(r.low), "close": float(r.close), "volume": float(r.volume)}
            for ix, r in frame.iterrows()]
    return {"symbol": symbol, "provider": "Yahoo Finance", "interval": "1d",
            "as_of": rows[-1]["date"], "data": rows}


def indicators(symbol="NIFTY50"):
    d = history(symbol, "1y")
    close = d.close
    delta = close.diff()
    gain, loss = delta.clip(lower=0).rolling(14).mean(), -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    values = {"SMA": close.rolling(20).mean().iloc[-1], "EMA": close.ewm(span=20, adjust=False).mean().iloc[-1],
              "RSI": (100 - 100 / (1 + rs)).iloc[-1], "MACD": (ema12 - ema26).iloc[-1],
              "Momentum": close.pct_change(10).iloc[-1],
              "Volatility": close.pct_change().rolling(20).std().iloc[-1] * (252 ** .5),
              "as_of": d.index[-1].strftime("%Y-%m-%d"), "provider": "Yahoo Finance"}
    return {k: (None if pd.isna(v) else float(v)) if k not in ("as_of", "provider") else v for k, v in values.items()}

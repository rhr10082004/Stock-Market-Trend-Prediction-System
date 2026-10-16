"""Observed daily market data from Yahoo Finance or the Groww Trading API."""
from datetime import date, datetime, timedelta
from functools import lru_cache
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

SYMBOLS = {"NIFTY50": "^NSEI"}
RANGES = {"1mo": 30, "3mo": 92, "6mo": 183, "1y": 366, "5y": 1827, "study": None}
GROWW_SYMBOLS = {"NIFTY50": "NSE-NIFTY"}
GROWW_STUDY_START = date(2020, 1, 1)  # Groww documents equity/index history from 2020.


class MarketDataUnavailable(RuntimeError):
    pass


def _clean(frame):
    if frame is None or frame.empty:
        raise MarketDataUnavailable("The market-data provider returned no observations.")
    frame = frame.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(c).lower().replace(" ", "_") for c in frame.columns]
    required = {"open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise MarketDataUnavailable("Market data provider returned an incomplete OHLC series.")
    if "volume" not in frame:
        frame["volume"] = 0.0
    frame = frame[list(required | {"volume"})].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"]).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    return frame


def _yahoo_download(symbol: str, period: str):
    try:
        import yfinance as yf
        frame = yf.download(symbol, period=period, interval="1d", auto_adjust=True,
                            progress=False, threads=False, timeout=20)
    except Exception as exc:
        raise MarketDataUnavailable("Yahoo Finance could not be reached. Try again later.") from exc
    return _clean(frame)


def _groww_request(start: date, end: date):
    token = os.getenv("GROWW_API_TOKEN", "").strip()
    if not token:
        raise MarketDataUnavailable("Groww is selected, but GROWW_API_TOKEN is not configured on the server.")
    params = {"exchange": "NSE", "segment": "CASH", "groww_symbol": GROWW_SYMBOLS["NIFTY50"],
              "start_time": f"{start:%Y-%m-%d} 00:00:00", "end_time": f"{end:%Y-%m-%d} 23:59:59",
              "candle_interval": "1day"}
    req = Request("https://api.groww.in/v1/historical/candles?" + urlencode(params), headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json", "X-API-VERSION": "1.0"})
    try:
        with urlopen(req, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise MarketDataUnavailable("Groww rejected the access token. Generate a fresh token and update the server environment.") from None
        raise MarketDataUnavailable(f"Groww historical data request failed (HTTP {exc.code}).") from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise MarketDataUnavailable("Groww historical data could not be reached. Try again later.") from None
    if body.get("status") != "SUCCESS":
        raise MarketDataUnavailable("Groww could not provide historical candles for NIFTY 50.")
    rows = body.get("payload", {}).get("candles", [])
    parsed = []
    for row in rows:
        if len(row) < 6:
            continue
        parsed.append((pd.to_datetime(row[0]), *row[1:6]))
    if not parsed:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    frame = pd.DataFrame(parsed, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    return frame


@lru_cache(maxsize=8)
def _download(symbol: str, period: str, provider: str, cache_date: str):
    if provider == "groww":
        today = datetime.now().date()
        end = today
        days = RANGES[period]
        start = max(GROWW_STUDY_START, today - timedelta(days=days)) if days is not None else GROWW_STUDY_START
        chunks = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=174), end)
            chunks.append(_groww_request(cursor, chunk_end))
            cursor = chunk_end + timedelta(days=1)
        if not chunks:
            raise MarketDataUnavailable("Groww has no history for the requested range.")
        return _clean(pd.concat(chunks)).loc[pd.Timestamp(start):pd.Timestamp(end)]
    if provider != "yfinance":
        raise MarketDataUnavailable("MARKET_DATA_PROVIDER must be 'groww' or 'yfinance'.")
    yahoo_period = "max" if period == "study" else {"1mo":"1mo", "3mo":"3mo", "6mo":"6mo", "1y":"1y", "5y":"5y"}[period]
    frame = _yahoo_download(symbol, yahoo_period)
    if period == "study":
        frame = frame.loc["2010-01-01":]
    return frame


def history(symbol="NIFTY50", period="1y"):
    if symbol != "NIFTY50" or period not in RANGES:
        raise ValueError("Supported series: NIFTY50; ranges: 1mo, 3mo, 6mo, 1y, 5y, study.")
    provider = os.getenv("MARKET_DATA_PROVIDER", "yfinance").strip().lower()
    data = _download(SYMBOLS[symbol], period, provider, datetime.now().date().isoformat()).copy()
    return data


def history_payload(symbol="NIFTY50", period="1y"):
    frame = history(symbol, period)
    rows = [{"date": ix.strftime("%Y-%m-%d"), "open": float(r.open), "high": float(r.high),
             "low": float(r.low), "close": float(r.close), "volume": float(r.volume)}
            for ix, r in frame.iterrows()]
    provider = "Groww Trading API" if os.getenv("MARKET_DATA_PROVIDER", "yfinance").strip().lower() == "groww" else "Yahoo Finance"
    return {"symbol": symbol, "provider": provider, "interval": "1d",
            "as_of": rows[-1]["date"], "data": rows}


def indicators(symbol="NIFTY50"):
    d = history(symbol, "1y")
    close = d.close
    delta = close.diff()
    gain, loss = delta.clip(lower=0).rolling(14).mean(), -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    provider = "Groww Trading API" if os.getenv("MARKET_DATA_PROVIDER", "yfinance").strip().lower() == "groww" else "Yahoo Finance"
    values = {"SMA": close.rolling(20).mean().iloc[-1], "EMA": close.ewm(span=20, adjust=False).mean().iloc[-1],
              "RSI": (100 - 100 / (1 + rs)).iloc[-1], "MACD": (ema12 - ema26).iloc[-1],
              "Momentum": close.pct_change(10).iloc[-1],
              "Volatility": close.pct_change().rolling(20).std().iloc[-1] * (252 ** .5),
              "as_of": d.index[-1].strftime("%Y-%m-%d"), "provider": provider}
    return {k: (None if pd.isna(v) else float(v)) if k not in ("as_of", "provider") else v for k, v in values.items()}

import os
import time
import threading
from pathlib import Path
import numpy as np
import pandas as pd

SYMBOLS = {"RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS", "INFY": "INFY.NS", "HDFCBANK": "HDFCBANK.NS", "ICICIBANK": "ICICIBANK.NS", "SBIN": "SBIN.NS", "ITC": "ITC.NS", "LT": "LT.NS"}

_history_cache = {}
_history_lock = threading.Lock()

def history(symbol, period="1y"):
    key=(symbol,period)
    now=time.monotonic()
    with _history_lock:
        cached=_history_cache.get(key)
        if cached and now-cached[0] < 900:
            return cached[1].copy(), cached[2]
    frame,label=_load_history(symbol,period)
    with _history_lock:
        _history_cache[key]=(now,frame.copy(),label)
    return frame,label

def _load_history(symbol, period="1y"):
    if symbol not in SYMBOLS:
        raise ValueError("Unsupported stock symbol")
    try:
        import yfinance as yf
        frame = yf.download(SYMBOLS[symbol], period=period, interval="1d", progress=False, auto_adjust=True, threads=False)
        if not frame.empty:
            if isinstance(frame.columns, pd.MultiIndex): frame.columns = frame.columns.get_level_values(0)
            frame = frame.rename(columns={c: c.title() for c in frame.columns})
            frame = frame[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(frame) >= 50:
                frame.index = pd.to_datetime(frame.index).tz_localize(None)
                frame.index.name = "Date"
                return frame, "Market data via Yahoo Finance"
    except Exception:
        pass
    # Bundled, deterministic illustrative fixture; it is not exchange history.
    fixture=Path(__file__).resolve().parents[1]/"data"/"demo_sample.csv"
    frame=pd.read_csv(fixture,parse_dates=["Date"]).set_index("Date")
    factor=1+(list(SYMBOLS).index(symbol)*.04)
    frame[["Open","High","Low","Close"]]=frame[["Open","High","Low","Close"]]*factor
    n={"1mo":23,"3mo":66,"6mo":130,"1y":280}.get(period,280)
    frame=frame.tail(n)
    frame.index.name="Date"
    return frame, "DEMO DATA MODE — Using illustrative sample data (not live market data)"

def indicators(frame):
    d = frame.copy()
    c = d.Close
    d["Daily Return"] = c.pct_change()
    d["SMA"] = c.rolling(20).mean()
    d["EMA"] = c.ewm(span=20, adjust=False).mean()
    delta = c.diff(); gain = delta.clip(lower=0).rolling(14).mean(); loss = -delta.clip(upper=0).rolling(14).mean()
    d["RSI"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    d["MACD"] = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["Momentum"] = c.pct_change(10)
    d["Volatility"] = d["Daily Return"].rolling(20).std() * np.sqrt(252)
    return d.dropna()


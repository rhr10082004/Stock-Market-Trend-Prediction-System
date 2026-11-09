"""Small serverless market-data API. Yahoo Finance is unofficial and may delay or rate-limit data."""
import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo


UA = "Mozilla/5.0 (compatible; NorthstarMarketDesk/1.0)"
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z]{1,2})?$")
DEFAULT_SYMBOLS = ["SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA", "TSLA"]
RANGES = {"1mo", "3mo", "6mo", "1y"}


class ApiError(Exception):
    pass


def checked_symbols(raw):
    symbols = []
    for item in (raw or "").split(","):
        sym = item.strip().upper()
        if not sym:
            continue
        if not SYMBOL_RE.fullmatch(sym):
            raise ApiError("Use valid US ticker symbols, separated by commas.")
        if sym not in symbols:
            symbols.append(sym)
    return symbols[:20] or DEFAULT_SYMBOLS


def yahoo_symbol(symbol):
    return symbol.replace(".", "-")


def read_spark(symbols, period="3mo", interval="1d"):
    params = urllib.parse.urlencode({"symbols": ",".join(yahoo_symbol(x) for x in symbols), "range": period, "interval": interval})
    last_error = "Market data provider is temporarily unavailable. Try again shortly."
    for host in ("https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com"):
        req = urllib.request.Request(host + "/v7/finance/spark?" + params, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                doc = json.loads(response.read().decode("utf-8"))
            spark = doc.get("spark") or {}
            if spark.get("error"):
                raise ApiError("Yahoo Finance could not return these symbols.")
            out = {}
            for result in spark.get("result") or []:
                responses = result.get("response") or []
                if not responses:
                    continue
                item = responses[0]
                meta = item.get("meta") or {}
                ysym = (result.get("symbol") or meta.get("symbol") or "").upper()
                symbol = ysym.replace("-", ".")
                timestamps = item.get("timestamp") or []
                quote = (((item.get("indicators") or {}).get("quote") or [{}])[0])
                bars = []
                closes = quote.get("close") or []
                opens = quote.get("open") or []
                highs = quote.get("high") or []
                lows = quote.get("low") or []
                volumes = quote.get("volume") or []
                for i, stamp in enumerate(timestamps):
                    close = closes[i] if i < len(closes) else None
                    if close is None:
                        continue
                    day = dt.datetime.fromtimestamp(stamp, dt.timezone.utc).astimezone(ZoneInfo("America/New_York"))
                    bars.append({"date": day.isoformat(), "close": float(close),
                                 "open": opens[i] if i < len(opens) else None,
                                 "high": highs[i] if i < len(highs) else None,
                                 "low": lows[i] if i < len(lows) else None,
                                 "volume": volumes[i] if i < len(volumes) else None})
                if bars:
                    out[symbol] = {"symbol": symbol, "meta": meta, "bars": bars}
            return out
        except urllib.error.HTTPError as exc:
            last_error = "Market data provider returned HTTP %s." % exc.code
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = "Could not reach the market data provider (%s)." % type(exc).__name__
    raise ApiError(last_error)


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = [max(0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    losses = [max(0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    return 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss else 100.0


def daily_setups(item):
    bars = item["bars"]
    if len(bars) < 30:
        return None
    closes = [bar["close"] for bar in bars]
    # Exclude today's still-forming candle during the US cash session.
    now = dt.datetime.now(ZoneInfo("America/New_York"))
    last_bar_day = dt.datetime.fromisoformat(bars[-1]["date"]).astimezone(ZoneInfo("America/New_York")).date()
    if last_bar_day == now.date() and (now.hour, now.minute) < (16, 0):
        bars = bars[:-1]
        closes = closes[:-1]
    if len(closes) < 30:
        return None
    current = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    prev_ma20 = sum(closes[-21:-1]) / 20
    strength = rsi(closes)
    prior_strength = rsi(closes[:-1])
    setups = []
    if current > max(closes[-21:-1]):
        setups.append("20-day closing-high breakout")
    run = closes[-6] / closes[-16] - 1
    range5 = (max(closes[-5:]) - min(closes[-5:])) / current
    if run > 0.10 and range5 < 0.05:
        setups.append("bull flag")
    if closes[-2] < prev_ma20 and current > ma20:
        setups.append("reclaimed 20-day average")
    if strength is not None and strength < 30:
        setups.append("RSI oversold")
    if prior_strength is not None and prior_strength < 30 and current > closes[-2]:
        setups.append("oversold bounce")
    return {"symbol": item["symbol"], "price": current, "date": bars[-1]["date"], "rsi": strength, "setups": setups}


def quote_card(item):
    meta, bars = item["meta"], item["bars"]
    price = meta.get("regularMarketPrice") or bars[-1]["close"]
    previous = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not previous and len(bars) > 1:
        previous = bars[-2]["close"]
    change = price - previous if previous else 0
    pct = change / previous * 100 if previous else 0
    return {"symbol": item["symbol"], "name": meta.get("longName") or meta.get("shortName") or item["symbol"],
            "price": round(float(price), 4), "change": round(float(change), 4), "changePct": round(float(pct), 3),
            "currency": meta.get("currency") or "USD", "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "US market",
            "marketTime": meta.get("regularMarketTime"), "lastBar": bars[-1]["date"],
            "volume": meta.get("regularMarketVolume"), "bars": bars}


def dispatch(path, query):
    if path.endswith("/health"):
        return {"status": "ok", "provider": "Yahoo Finance public chart data", "paperOnly": True}
    if not any(path.endswith("/" + route) for route in ("market", "history", "scan")):
        raise ApiError("Unknown API endpoint.")
    symbols = checked_symbols(query.get("symbols", [""])[0])
    period = query.get("range", ["3mo"])[0]
    if period not in RANGES:
        raise ApiError("Choose one of: 1mo, 3mo, 6mo, 1y.")
    data = read_spark(symbols, period=period)
    missing = [s for s in symbols if s not in data]
    cards = [quote_card(data[s]) for s in symbols if s in data]
    if not cards:
        raise ApiError("No market history was returned for those symbols.")
    if path.endswith("/market"):
        return {"provider": "Yahoo Finance (unofficial; data may be delayed)", "asOf": dt.datetime.now(dt.timezone.utc).isoformat(), "quotes": cards, "missing": missing}
    if path.endswith("/history"):
        requested = symbols[0]
        if requested not in data:
            raise ApiError("No history was returned for %s." % requested)
        item = data[requested]
        q = quote_card(item)
        return {"provider": "Yahoo Finance (unofficial; data may be delayed)", "symbol": requested, "quote": {k: v for k, v in q.items() if k != "bars"}, "bars": item["bars"]}
    if path.endswith("/scan"):
        scans = [daily_setups(data[s]) for s in symbols if s in data]
        hits = [row for row in scans if row and row["setups"]]
        return {"provider": "Yahoo Finance (unofficial; data may be delayed)", "asOf": dt.datetime.now(dt.timezone.utc).isoformat(), "hits": hits,
                "scanned": len(scans), "missing": missing, "note": "Chart conditions for review, not buy or sell recommendations."}
    raise ApiError("Unknown API endpoint.")


class handler(BaseHTTPRequestHandler):
    route = None

    def do_GET(self):
        try:
            parsed = urllib.parse.urlsplit(self.path)
            result = dispatch(self.route or parsed.path, urllib.parse.parse_qs(parsed.query))
            self.respond(200, result)
        except ApiError as exc:
            self.respond(400, {"error": str(exc)})
        except Exception:
            self.respond(500, {"error": "The market request failed. Please retry."})

    def respond(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=180")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

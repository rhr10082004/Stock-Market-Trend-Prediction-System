import os, re, jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from .market import SYMBOLS, history_payload, indicators, history, MarketDataUnavailable
from .model import train_and_predict
from . import store

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
CORS(app, resources={r"/api/*": {"origins": [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]}})
SECRET = os.getenv("JWT_SECRET", "")

def token_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not token or not SECRET: return jsonify(error="Please sign in to continue"), 401
        try: g.user_id = int(jwt.decode(token, SECRET, algorithms=["HS256"])["sub"])
        except (jwt.PyJWTError, ValueError, KeyError): return jsonify(error="Your session expired. Please sign in again"), 401
        return fn(*args, **kwargs)
    return wrapped

@app.get("/api/health")
def health():
    try: db=store.health()
    except Exception: return jsonify(status="degraded",market_data="Yahoo Finance daily",database="unavailable"),503
    return jsonify(status="ok",market_data="Yahoo Finance daily",database=db,app_mode="production")

@app.get("/api/stocks")
def stocks(): return jsonify(stocks=[{"symbol":"NIFTY50","name":"NIFTY 50","provider_symbol":"^NSEI"}],provider="Yahoo Finance",interval="1d")

@app.get("/api/history/<symbol>")
def get_history(symbol):
    period=request.args.get("range","1y")
    try:
        data=history_payload(symbol.upper(),period)
        data["data"]=[{"date":x["date"],"close":x["close"]} for x in data["data"]]
        return jsonify(data)
    except ValueError as e: return jsonify(error=str(e)),400
    except MarketDataUnavailable as e: return jsonify(error=str(e)),503
    except Exception: return jsonify(error="Historical market data is temporarily unavailable. Please retry."),503

@app.get("/api/indicators/<symbol>")
def get_indicators(symbol):
    try: return jsonify(symbol=symbol.upper(),indicators=indicators(symbol.upper()))
    except ValueError as e: return jsonify(error=str(e)),400
    except MarketDataUnavailable as e: return jsonify(error=str(e)),503
    except Exception: return jsonify(error="Technical indicators are temporarily unavailable. Please retry."),503

@app.post("/api/auth/register")
def register():
    b=request.get_json(silent=True) or {}; name=str(b.get("name","")).strip(); email=str(b.get("email","")).strip().lower(); password=str(b.get("password",""))
    if len(name)<2 or len(name)>120: return jsonify(error="Enter a name between 2 and 120 characters"),400
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email): return jsonify(error="Enter a valid email address"),400
    if len(password)<8: return jsonify(error="Password must be at least 8 characters"),400
    if not SECRET: return jsonify(error="Authentication is not configured. Set JWT_SECRET."),503
    try: uid=store.create_user(name,email,password)
    except ValueError as e: return jsonify(error=str(e)),409
    except Exception: return jsonify(error="Account could not be created. Check persistent database configuration."),503
    return _session(uid,name,email)

@app.post("/api/auth/login")
def login():
    b=request.get_json(silent=True) or {}; email=str(b.get("email","")).strip().lower(); password=str(b.get("password",""))
    try: u=store.authenticate(email,password)
    except Exception: return jsonify(error="Persistent authentication service is unavailable"),503
    if not u: return jsonify(error="Email or password is incorrect"),401
    if not SECRET: return jsonify(error="Authentication is not configured. Set JWT_SECRET."),503
    return _session(u["id"],u["name"],u["email"])

def _session(uid,name,email):
    token=jwt.encode({"sub":str(uid),"exp":datetime.now(timezone.utc)+timedelta(hours=12)},SECRET,algorithm="HS256")
    return jsonify(token=token,user={"name":name,"email":email},mode=store.mode_label())

@app.post("/api/auth/logout")
@token_required
def logout(): return jsonify(message="Signed out")

@app.post("/api/predict")
@token_required
def predict():
    body=request.get_json(silent=True) or {}; symbol=str(body.get("symbol","NIFTY50")).upper()
    if symbol!="NIFTY50": return jsonify(error="Only the NIFTY50 index is supported"),400
    try:
        frame=history(symbol,"study")
        result=train_and_predict(frame); result["symbol"]=symbol
        store.save_prediction(g.user_id,result)
        return jsonify(result)
    except ValueError as e: return jsonify(error=str(e)),422
    except MarketDataUnavailable as e: return jsonify(error=str(e)),503
    except Exception: return jsonify(error="Forecast could not be generated. Verify the provider and persistent database, then retry."),503

@app.get("/api/model-performance")
@token_required
def performance():
    symbol=request.args.get("symbol","NIFTY50").upper()
    if symbol!="NIFTY50": return jsonify(error="Only the NIFTY50 index is supported"),400
    try:
        from .market import history
        r=train_and_predict(history(symbol,"study"))
        return jsonify({k:r[k] for k in ("metrics","dm_tests","diagnostics","volatility_forecast","backtest","test_period","model","provider","as_of")})
    except Exception: return jsonify(error="Model evaluation is unavailable. Check market-data connectivity and history."),503

@app.get("/api/predictions")
@token_required
def get_predictions():
    try: return jsonify(predictions=store.predictions(g.user_id),mode=store.mode_label())
    except Exception: return jsonify(error="Persistent prediction history is unavailable"),503

@app.errorhandler(413)
def too_large(_): return jsonify(error="Request is too large"),413
@app.errorhandler(404)
def not_found(_): return jsonify(error="Endpoint not found"),404
@app.errorhandler(500)
def server_error(_): return jsonify(error="Unexpected server error"),500

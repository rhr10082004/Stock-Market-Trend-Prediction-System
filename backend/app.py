import os, re, jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from .market import SYMBOLS, history, indicators
from .model import train_and_predict
from . import store

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=64*1024
origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:5173").split(",")]
CORS(app,resources={r"/api/*":{"origins":origins}},supports_credentials=False)
SECRET=os.getenv("JWT_SECRET","")

def token_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        token=request.headers.get("Authorization","").removeprefix("Bearer ")
        if not token or not SECRET: return jsonify(error="Please sign in to continue"),401
        try: g.user_id=int(jwt.decode(token,SECRET,algorithms=["HS256"])["sub"])
        except jwt.PyJWTError: return jsonify(error="Your session expired. Please sign in again"),401
        return fn(*args,**kwargs)
    return wrapped

def payload(): return jsonify({"mode":store.mode_label(),"data_mode":"demo" if os.getenv("APP_MODE","demo").lower()=="demo" else "production"})

@app.get("/api/health")
def health(): return jsonify(status="ok",mode=store.mode_label())

@app.get("/api/stocks")
def stocks(): return jsonify(stocks=list(SYMBOLS),mode=store.mode_label())

@app.get("/api/history/<symbol>")
def get_history(symbol):
    symbol=symbol.upper()
    try:
        period=request.args.get("range","1y"); period=period if period in {"1mo","3mo","6mo","1y"} else "1y"
        df,label=history(symbol,period)
        return jsonify(symbol=symbol,mode=label,app_mode=store.mode_label(),data=[{"date":str(i.date()),"close":round(float(r.Close),2)} for i,r in df.iterrows()])
    except ValueError as e: return jsonify(error=str(e)),400
    except Exception as e: return jsonify(error=str(e)),503

@app.get("/api/indicators/<symbol>")
def get_indicators(symbol):
    try:
        df,mode=history(symbol.upper(),"1y"); d=indicators(df); r=d.iloc[-1]
        return jsonify(symbol=symbol.upper(),mode=mode,indicators={k:round(float(r[k]),4) for k in ["SMA","EMA","RSI","MACD","Momentum","Volatility"]})
    except ValueError as e: return jsonify(error=str(e)),400
    except Exception as e: return jsonify(error=str(e)),503

@app.post("/api/auth/register")
def register():
    b=request.get_json(silent=True) or {}; name=str(b.get("name","")).strip(); email=str(b.get("email","")).strip().lower(); password=str(b.get("password", ""))
    if len(name)<2 or len(name)>120: return jsonify(error="Enter a name between 2 and 120 characters"),400
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email): return jsonify(error="Enter a valid email address"),400
    if len(password)<8: return jsonify(error="Password must be at least 8 characters"),400
    try: uid=store.create_user(name,email,password)
    except ValueError as e: return jsonify(error=str(e)),409
    except Exception: return jsonify(error="Account could not be created. Check database configuration."),503
    return _session(uid,name,email)

@app.post("/api/auth/login")
def login():
    b=request.get_json(silent=True) or {}; email=str(b.get("email","")).strip().lower(); password=str(b.get("password", ""))
    try: u=store.authenticate(email,password)
    except Exception: return jsonify(error="Authentication service is unavailable"),503
    if not u: return jsonify(error="Email or password is incorrect"),401
    return _session(u["id"],u["name"],u["email"])

def _session(uid,name,email):
    if not SECRET: return jsonify(error="Authentication is not configured. Set JWT_SECRET."),503
    t=jwt.encode({"sub":str(uid),"exp":datetime.now(timezone.utc)+timedelta(hours=12)},SECRET,algorithm="HS256")
    return jsonify(token=t,user={"name":name,"email":email},mode=store.mode_label())

@app.post("/api/auth/logout")
@token_required
def logout(): return jsonify(message="Signed out")

@app.post("/api/predict")
@token_required
def predict():
    b=request.get_json(silent=True) or {}; symbol=str(b.get("symbol", "")).upper()
    try:
        df,mode=history(symbol,"1y"); result=train_and_predict(df); result["symbol"]=symbol; result["data_mode"]=mode; result["app_mode"]=store.mode_label()
        result["created_at"]=datetime.now(timezone.utc).isoformat()
        store.save_prediction(g.user_id,result)
        return jsonify(result)
    except ValueError as e: return jsonify(error=str(e)),400
    except Exception: return jsonify(error="Prediction could not be generated. Verify market data and database settings."),503

@app.get("/api/model-performance")
@token_required
def performance():
    symbol=request.args.get("symbol","RELIANCE").upper()
    try: df,mode=history(symbol,"1y"); r=train_and_predict(df); return jsonify(metrics=r["metrics"],mode=mode,symbol=symbol)
    except Exception: return jsonify(error="Model evaluation is unavailable for this stock"),503

@app.get("/api/predictions")
@token_required
def get_predictions():
    try: return jsonify(predictions=store.predictions(g.user_id),mode=store.mode_label())
    except Exception: return jsonify(error="Prediction history is unavailable"),503

@app.errorhandler(413)
def too_large(_): return jsonify(error="Request is too large"),413
@app.errorhandler(404)
def not_found(_): return jsonify(error="Endpoint not found"),404
@app.errorhandler(500)
def server_error(_): return jsonify(error="Unexpected server error"),500


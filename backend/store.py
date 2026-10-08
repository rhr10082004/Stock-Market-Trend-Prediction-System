"""Small persistence layer: MySQL in production, clearly labeled volatile demo store otherwise."""
import os, sqlite3, threading
from werkzeug.security import generate_password_hash, check_password_hash

_lock = threading.Lock()
_demo_users, _demo_predictions = {}, []
_mysql_unavailable = False

def _mysql():
    global _mysql_unavailable
    if os.getenv("APP_MODE", "demo").lower() == "demo":
        return None
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith("mysql"):
        return None
    import pymysql
    from urllib.parse import urlparse, unquote
    u = urlparse(url.replace("mysql+pymysql://", "mysql://", 1))
    try:
        db=pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username or ""), password=unquote(u.password or ""), database=u.path.lstrip("/"), cursorclass=pymysql.cursors.DictCursor, autocommit=True, connect_timeout=3)
        _mysql_unavailable=False
        return db
    except Exception:
        _mysql_unavailable=True
        return None

def mode_label():
    if os.getenv("APP_MODE", "demo").lower() == "demo": return "DEMO MODE — DATA MAY NOT PERSIST"
    if _mysql_unavailable: return "DEMO MODE — MySQL unavailable; DATA MAY NOT PERSIST"
    if os.getenv("DATABASE_URL", "").startswith("mysql"): return "MySQL configured — connection checked when used"
    return "DEMO MODE — MySQL is not configured; DATA MAY NOT PERSIST"

def create_user(name, email, password):
    ph = generate_password_hash(password)
    db = _mysql()
    if db:
        try:
            with db.cursor() as c:
                c.execute("INSERT INTO users(name,email,password_hash) VALUES(%s,%s,%s)", (name,email,ph)); return c.lastrowid
        except Exception as e:
            if "Duplicate" in str(e): raise ValueError("An account with that email already exists")
            raise
        finally: db.close()
    with _lock:
        if email in _demo_users: raise ValueError("An account with that email already exists")
        uid = len(_demo_users)+1; _demo_users[email] = {"id":uid,"name":name,"email":email,"password_hash":ph}; return uid

def authenticate(email, password):
    db = _mysql()
    if db:
        try:
            with db.cursor() as c: c.execute("SELECT * FROM users WHERE email=%s", (email,)); u=c.fetchone()
        finally: db.close()
    else: u = _demo_users.get(email)
    return u if u and check_password_hash(u["password_hash"], password) else None

def save_prediction(uid, row):
    db = _mysql()
    if db:
        try:
            with db.cursor() as c: c.execute("INSERT INTO predictions(user_id,stock_symbol,prediction,confidence,model) VALUES(%s,%s,%s,%s,%s)", (uid,row["symbol"],row["trend"],row["confidence"],row["model"]))
        finally: db.close()
    else:
        with _lock: _demo_predictions.append({**row,"user_id":uid,"created_at":row.get("created_at")})

def predictions(uid):
    db=_mysql()
    if db:
        try:
            with db.cursor() as c: c.execute("SELECT stock_symbol AS symbol,prediction AS trend,confidence,model,created_at FROM predictions WHERE user_id=%s ORDER BY created_at DESC LIMIT 200",(uid,)); return c.fetchall()
        finally: db.close()
    return [p for p in reversed(_demo_predictions) if p["user_id"]==uid]


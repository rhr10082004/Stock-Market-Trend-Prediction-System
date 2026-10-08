"""Persistent SQLite (local) or MySQL (hosted) data store. No in-memory account fallback."""
import os, sqlite3
from urllib.parse import urlparse, unquote
from werkzeug.security import generate_password_hash, check_password_hash

def _connect():
    url = os.getenv("DATABASE_URL", "sqlite:///stockai.db")
    if url.startswith("sqlite:///"):
        if os.getenv("VERCEL", "").lower() == "1":
            raise RuntimeError("Hosted deployments require a persistent MySQL database.")
        path = url[len("sqlite:///"):]
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS predictions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id),stock_symbol TEXT NOT NULL,prediction TEXT NOT NULL,confidence REAL,model TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        return db, "sqlite"
    if url.startswith("mysql"):
        import pymysql
        u = urlparse(url.replace("mysql+pymysql://", "mysql://", 1))
        db = pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username or ""),
            password=unquote(u.password or ""), database=u.path.lstrip("/"), autocommit=True,
            connect_timeout=5, cursorclass=pymysql.cursors.DictCursor)
        return db, "mysql"
    raise RuntimeError("DATABASE_URL must use sqlite:/// or mysql://")

def mode_label():
    return "Persistent SQLite" if os.getenv("DATABASE_URL", "sqlite:///stockai.db").startswith("sqlite") else "Persistent MySQL"

def _execute(db, kind, sql, params=()):
    if kind == "sqlite": return db.execute(sql.replace("%s", "?"), params)
    c=db.cursor(); c.execute(sql, params); return c

def create_user(name,email,password):
    db,kind=_connect()
    try:
        cur=_execute(db,kind,"INSERT INTO users(name,email,password_hash) VALUES(%s,%s,%s)",(name,email,generate_password_hash(password)))
        uid=cur.lastrowid
        if kind=="sqlite": db.commit()
        return uid
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower(): raise ValueError("An account with that email already exists")
        raise
    finally: db.close()

def authenticate(email,password):
    db,kind=_connect()
    try:
        row=_execute(db,kind,"SELECT id,name,email,password_hash FROM users WHERE email=%s",(email,)).fetchone()
        if not row: return None
        u=dict(row)
        return u if check_password_hash(u["password_hash"],password) else None
    finally: db.close()

def save_prediction(uid,row):
    db,kind=_connect()
    try:
        ret=float(row.get("forecast_return",0)); trend="UP" if ret>.001 else "DOWN" if ret<-.001 else "SIDEWAYS"
        _execute(db,kind,"INSERT INTO predictions(user_id,stock_symbol,prediction,confidence,model) VALUES(%s,%s,%s,%s,%s)",
                 (uid,row["symbol"],trend,None,row["model"]))
        if kind=="sqlite": db.commit()
    finally: db.close()

def predictions(uid):
    db,kind=_connect()
    try:
        return [dict(r) for r in _execute(db,kind,"SELECT stock_symbol AS symbol,prediction AS trend,confidence,model,created_at FROM predictions WHERE user_id=%s ORDER BY created_at DESC LIMIT 200",(uid,)).fetchall()]
    finally: db.close()

def health():
    db,kind=_connect()
    try: db.close(); return {"status":"connected","type":kind}
    except Exception: raise

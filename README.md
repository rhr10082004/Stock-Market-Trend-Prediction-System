# StockAI — NIFTY 50 Forecast Research

StockAI retrieves observed NIFTY 50 daily OHLCV history from Yahoo Finance and compares one-session-ahead return forecasts. It does not substitute bundled prices when the provider fails. The application is for educational research, not investment advice.

## What it includes

- NIFTY 50 daily chart, SMA, EMA, RSI, MACD, momentum and annualized volatility.
- Chronological expanding-window evaluation with monthly refits and a 252-session out-of-sample window.
- Available estimators: Random Forest, Support Vector Regression, AR(1) persistence benchmark; ARIMA(1,0,1) and XGBoost are added when optional packages are installed. The best candidate is selected by actual test RMSE.
- Return MAE/RMSE, close-price MAE/RMSE/MAPE, directional accuracy, pairwise one-step Diebold–Mariano tests, and a simplified strategy simulation with an explicit 10 bp turnover cost.
- ADF, Jarque–Bera, Ljung–Box and ARCH diagnostics when `statsmodels` is installed; optional GARCH(1,1) next-session volatility estimate when `arch` is installed.
- Hashed passwords, signed 12-hour bearer tokens, protected forecast/history endpoints, and persistent account scoped history.

## Stack and structure

React + Vite + Recharts frontend; Flask REST API; Pandas, NumPy and scikit-learn analysis; Yahoo Finance daily data; SQLite locally or MySQL in hosted deployments. `api/index.py` is the Vercel Python entry point.

## Local setup

1. Install Python 3.11+ and Node.js 18+.
2. In this directory run `python -m venv .venv`, activate it, then `pip install -r requirements.txt`.
3. Optional extra estimators and full diagnostics: `pip install -r requirements-research.txt`.
4. Copy `.env.example` to `.env`; set a unique `JWT_SECRET` and configure `DATABASE_URL`.
5. Start Flask with `python -m flask --app backend.app run --port 5000`.
6. In another terminal run `npm install` and `npm run dev`.

The local default is persistent SQLite (`sqlite:///stockai.db`), not an in-memory demo account. For MySQL, set `DATABASE_URL=mysql+pymysql://user:password@host:3306/stockai` and apply `database/schema.sql`. Keep `.env` and credentials out of Git. `VITE_API_URL` points the browser to Flask (usually `http://localhost:5000`).

## Analysis notes

Features at session *t* use only data observable through *t*. The target is the close-to-close return at *t+1*. The last 252 usable labeled observations are held out; model refits occur every 21 sessions and training only sees labels available at each refit. Forecast model choice uses observed RMSE, not a fixed preferred model. MAPE is reported on forecast close prices; return MAPE is intentionally omitted because daily returns can be near zero. DM p-values use squared error with a one-session horizon. The backtest is simplified and omits slippage, taxes, market impact, and execution constraints. Metrics do not imply future performance.

Yahoo Finance is an external daily-data provider; observations can be delayed or revised. The study history starts in 2010 and extends to the latest session Yahoo returns. If external data is unavailable, requests return an error rather than sample data. Hosted Vercel functions reject SQLite and require the configured persistent MySQL database; local SQLite is durable on the developer machine. Optional ARIMA/XGBoost/GARCH and full diagnostics are identified as unavailable when their dependencies are not installed. LSTM forecasting is not currently implemented; GARCH is used only for volatility, not price direction.

## API

- `GET /api/health`, `GET /api/stocks`
- `GET /api/history/NIFTY50?range=1mo|3mo|6mo|1y|5y|study`
- `GET /api/indicators/NIFTY50`
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`
- `POST /api/predict` with `{ "symbol": "NIFTY50" }`
- `GET /api/model-performance?symbol=NIFTY50`, `GET /api/predictions`

Forecasts, performance and history require `Authorization: Bearer <token>`. Market history and technical indicators are public.

## Verify and deploy

Run `npm run build` and `python -m unittest discover -s tests -v`. Vercel serves the Vite build and exposes Flask through `api/index.py`. Set `JWT_SECRET`, a reachable MySQL `DATABASE_URL`, and exact allowed `CORS_ORIGINS` in the Vercel project. Yahoo Finance reachability and serverless execution limits must be checked in the target deployment; no hosted deployment is claimed by this repository.

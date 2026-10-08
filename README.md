# StockAI

Educational stock trend exploration built with React, Flask and scikit-learn. StockAI uses historical observations to calculate technical features, compares Logistic Regression and Random Forest on a chronological holdout, and reports the evaluated model's output with its probability score. It is not investment advice.

## Features

- Responsive dashboard with supported NSE symbols, historical closing-price chart and SMA, EMA, RSI and annualized volatility cards.
- Five-session UP / DOWN / SIDEWAYS classifier; both candidate models are evaluated chronologically and selected by holdout macro F1.
- Prediction history scoped to the authenticated user.
- Hashed passwords, signed bearer tokens, parameterized SQL and JSON API errors.
- MySQL persistence for production; volatile in-memory demo mode is clearly labeled.
- Yahoo Finance history when available. Demo mode shows a deterministic illustrative fixture and labels it as non-live sample data.
- A deterministic rule-based fallback is labeled `BASELINE DEMO MODEL` if sklearn training is unavailable; its metrics come from the chronological holdout.
- In-process caches limit repeated market downloads and avoid retraining against unchanged data.

## Stack and structure

- `frontend/`: React, Vite, Recharts, Lucide and responsive CSS.
- `backend/`: Flask REST API, market data service, sklearn pipeline and storage adapter.
- `api/index.py`: Vercel Python function entry point.
- `database/schema.sql`: MySQL user and prediction tables.
- `ml/`, `models/`, `data/`: reserved locations for model/data artifacts; no credentials or generated models are committed.

## Local setup

1. Python 3.11+ and Node.js 18+ are recommended.
2. Create a virtual environment, activate it and run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, set a unique `JWT_SECRET`, then load it into your shell.
4. In one terminal run `python -m flask --app backend.app run --port 5000` from this folder.
5. In another terminal run `npm install` and `npm run dev`. Set `VITE_API_URL=http://localhost:5000` in the frontend environment when using Vite's dev server.

The default `APP_MODE=demo` enables clearly identified demo persistence. Demo accounts and their history live only in server memory and disappear when the process restarts. Set `APP_MODE=production`, configure `DATABASE_URL`, and create the schema with `database/schema.sql` for MySQL persistence. Production mode also requires a valid `JWT_SECRET`. `CORS_ORIGINS` is a comma-separated allowlist.

## ML approach

Indicators use trailing windows only. The target compares close at time *t* with close five trading sessions later: above +1% is UP, below -1% is DOWN, and the middle band is SIDEWAYS. Rows without enough forward data or feature history are excluded. The earliest 80% of observations trains each model and the latest 20% evaluates them; observations are never shuffled. Model choice uses actual holdout macro F1. The selected model is refit on labeled history before the latest row is scored. Confidence is the model's class probability, not calibrated certainty. Feature importance is shown only for Random Forest and does not establish causation.

## API

- `GET /api/stocks`
- `GET /api/history/<symbol>?range=1mo|3mo|6mo|1y`
- `GET /api/indicators/<symbol>`
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`
- `POST /api/predict` with `{ "symbol": "RELIANCE" }`
- `GET /api/model-performance?symbol=RELIANCE`
- `GET /api/predictions`

All endpoints except market-data reads require `Authorization: Bearer <token>` when marked private in the UI; auth/logout, predict, performance and history are protected.

## Vercel

Import this folder as its own Vercel project. Configure `APP_MODE=production`, `JWT_SECRET`, `DATABASE_URL`, and `CORS_ORIGINS` in Vercel project environment variables. Configure the Python runtime dependencies from `requirements.txt`; `api/index.py` exposes Flask as a serverless function and Vite outputs the static UI to `dist`. Verify the resulting deployment and managed MySQL reachability before treating it as production ready. The in-memory demo store is not durable across serverless invocations, and external market-data availability depends on provider access and function limits.

## Limitations

Demo fallback values are illustrative, deterministic values and are not exchange observations. Yahoo Finance access is best effort and may be delayed, unavailable, or subject to provider terms. Demo persistence is in-memory and may not persist across Vercel serverless invocations. No deployment has been verified. The interface does not promise predictive performance, and the model is a learning demonstration rather than a trading system.


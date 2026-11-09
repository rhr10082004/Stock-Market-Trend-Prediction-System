# Northstar Market Desk

A compact web dashboard adapted from ideas in the [Day Trader skill toolkit](https://github.com/Jakeschincariol/day-trader-skill). It combines a watchlist, historical price charts, daily chart-condition scans, and a position-risk planner. It does not place trades.

## Stack

- React, Vite, Recharts, Lucide
- Python 3.12 standard-library API, compatible with Vercel Functions
- Yahoo Finance public chart data; it is unofficial and may be delayed, revised, rate-limited, or unavailable

## Local setup

Requirements: Node.js 20+ and Python 3.12+.

```powershell
npm install
npm run dev
```

In a second terminal:

```powershell
python dev_server.py
```

Open http://127.0.0.1:5173. The API listens at http://127.0.0.1:8000. The app does not include bundled or generated quote samples; provider failures appear as errors.

## API

- `GET /api/health`
- `GET /api/market?symbols=SPY,QQQ,AAPL`
- `GET /api/history?symbols=SPY&range=1mo|3mo|6mo|1y`
- `GET /api/scan?symbols=SPY,QQQ,AAPL`

Symbols are limited to US ticker formats. Scanner conditions use completed daily closes and are descriptive chart conditions, not trade recommendations.

## Deploy to Vercel

Import this directory as the project root. Vercel uses `vercel.json`, `.python-version`, `npm run build`, and `dist/`. There are no credentials required for the public data endpoints. A Vercel account with permission to create a project and deployment is required.

## Safety and limits

- The risk planner is local browser math. It estimates whole shares using the entered stop and loss limit, with conservative position and order caps.
- No order API, user account, broker login, or trading token is used.
- Groww is not supported by this US-market app. Do not put a broker key in frontend environment variables or chat.
- Yahoo Finance is an unofficial provider. Prices may be stale and are not guaranteed executable quotes.
- Local watchlist preferences stay in browser `localStorage`; no user information is sent to an application database.

## Attribution

Daily pattern names and calculation logic are adapted from the MIT-licensed `trader-scanner` in [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill). See `THIRD_PARTY_NOTICES.md`.

"""One-session-ahead NIFTY 50 return forecasting with chronological walk-forward tests."""
import numpy as np
import pandas as pd
import hashlib, copy

_CACHE = {}

FEATURES = ["return", "range", "sma_gap", "ema_gap", "rsi", "macd", "momentum", "volatility", "volume_change"]


def _features(frame, inference=False):
    d = frame.copy()
    c = d.close
    ret = c.pct_change()
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    delta = c.diff()
    gain, loss = delta.clip(lower=0).rolling(14).mean(), -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    d["return"] = ret
    d["range"] = (d.high - d.low) / c
    d["sma_gap"] = c / c.rolling(20).mean() - 1
    d["ema_gap"] = c / c.ewm(span=20, adjust=False).mean() - 1
    d["rsi"] = 100 - 100 / (1 + rs)
    d["macd"] = (ema12 - ema26) / c
    d["momentum"] = c.pct_change(10)
    d["volatility"] = ret.rolling(20).std()
    d["volume_change"] = d.volume.pct_change().replace([np.inf, -np.inf], np.nan).clip(-5, 5)
    d["target"] = ret.shift(-1)
    d=d.replace([np.inf, -np.inf], np.nan)
    return d.dropna(subset=FEATURES if inference else FEATURES + ["target"])


def _metrics(actual, predicted, close):
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    a, p = np.asarray(actual), np.asarray(predicted)
    nz = np.abs(a) > 1e-9
    price_actual=np.asarray(close)*(1+a); price_pred=np.asarray(close)*(1+p)
    return {"return_mae": float(mean_absolute_error(a, p)), "return_rmse": float(np.sqrt(mean_squared_error(a, p))),
            "price_mae": float(mean_absolute_error(price_actual, price_pred)),
            "price_rmse": float(np.sqrt(mean_squared_error(price_actual, price_pred))),
            "price_mape_percent": float(np.mean(np.abs((price_actual-price_pred)/price_actual))*100),
            "directional_accuracy": float(np.mean(np.sign(a) == np.sign(p)))}


def _walk_forward(d):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR
    from threadpoolctl import threadpool_limits
    x, y = d[FEATURES], d.target
    test_start = max(252, len(d) - 252)
    if test_start < 180 or len(d) - test_start < 20:
        raise ValueError("At least 200 clean daily observations are needed for walk-forward evaluation.")
    models = {
        "Random Forest": RandomForestRegressor(n_estimators=80, max_depth=5, min_samples_leaf=5, max_features=.8, random_state=19, n_jobs=1),
        "Support Vector Regression": make_pipeline(StandardScaler(), SVR(C=0.5, epsilon=.003, kernel="rbf")),
        "AR(1) return benchmark": None,
    }
    predictions, actual = {k: [] for k in models}, y.iloc[test_start:].to_numpy()
    # Refit each model every 21 sessions on only information available at that date.
    try:
        from statsmodels.tsa.arima.model import ARIMA
        models["ARIMA(1,0,1)"] = "arima"
    except ImportError:
        pass
    try:
        from xgboost import XGBRegressor
        models["XGBoost"] = XGBRegressor(n_estimators=100, max_depth=2, learning_rate=.035, subsample=.85,
                                               colsample_bytree=.8, objective="reg:squarederror", n_jobs=1, verbosity=0, random_state=19)
    except ImportError:
        pass
    with threadpool_limits(limits=1):
        for start in range(test_start, len(d), 21):
            stop = min(start + 21, len(d))
            for name, model in models.items():
                if name == "AR(1) return benchmark":
                    pred = np.repeat(float(y.iloc[:start].iloc[-1]), stop-start)
                elif model == "arima":
                    try:
                        fitted = ARIMA(y.iloc[:start], order=(1, 0, 1), trend="c").fit()
                        pred = np.asarray(fitted.forecast(stop-start), dtype=float)
                    except Exception:
                        pred = np.repeat(float(y.iloc[:start].mean()), stop-start)
                else:
                    model.fit(x.iloc[:start], y.iloc[:start])
                    pred = model.predict(x.iloc[start:stop])
                predictions[name].extend(np.asarray(pred).tolist())
    metrics = {name: _metrics(actual, vals, d.close.iloc[test_start:].to_numpy()) for name, vals in predictions.items()}
    return x, y, predictions, actual, metrics


def _diagnostics(returns):
    out = {}
    try:
        from statsmodels.tsa.stattools import adfuller
        out["adf_return_pvalue"] = float(adfuller(returns, autolag="AIC")[1])
        from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
        out["ljung_box_10_pvalue"] = float(acorr_ljungbox(returns, lags=[10], return_df=True)["lb_pvalue"].iloc[0])
        out["arch_lm_pvalue"] = float(het_arch(returns, nlags=10)[1])
        from scipy.stats import jarque_bera
        out["jarque_bera_pvalue"] = float(jarque_bera(returns).pvalue)
    except ImportError:
        out["diagnostics_status"] = "Install statsmodels for ADF, Ljung-Box and ARCH diagnostics."
    return out


def _garch_forecast(returns):
    try:
        from arch import arch_model
        model=arch_model(np.asarray(returns)*100, mean="Zero", vol="GARCH", p=1, q=1, rescale=False)
        fit=model.fit(disp="off", show_warning=False)
        variance=float(fit.forecast(horizon=1, reindex=False).variance.iloc[-1,0])
        return {"model":"GARCH(1,1)","next_session_volatility_percent":float(np.sqrt(max(0,variance))),"status":"fitted"}
    except ImportError:
        return {"model":"GARCH(1,1)","status":"unavailable","reason":"Install arch from requirements-research.txt"}
    except Exception:
        return {"model":"GARCH(1,1)","status":"fit_failed"}


def _dm_tests(actual, predictions):
    from scipy import stats
    names = list(predictions)
    result = []
    for i, a in enumerate(names):
        for b in names[i+1:]:
            diff = (np.asarray(actual)-predictions[a])**2 - (np.asarray(actual)-predictions[b])**2
            denom = diff.std(ddof=1) / np.sqrt(len(diff)) if len(diff) > 1 else 0
            stat = float(diff.mean()/denom) if denom else 0.0
            p = float(2*stats.t.sf(abs(stat), max(1, len(diff)-1)))
            result.append({"model_a": a, "model_b": b, "dm_statistic": stat, "p_value": p,
                           "loss": "squared error; one-session horizon"})
    return result


def train_and_predict(frame):
    key=hashlib.sha256(pd.util.hash_pandas_object(frame,index=True).values.tobytes()).hexdigest()
    if key in _CACHE: return copy.deepcopy(_CACHE[key])
    d = _features(frame)
    x, y, predictions, actual, metrics = _walk_forward(d)
    chosen = min(metrics, key=lambda k: metrics[k]["return_rmse"])
    # Final model fit uses every fully observed target; forecasts the next trading session.
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR
    from threadpoolctl import threadpool_limits
    latest = _features(frame, inference=True)
    latest_x = latest[FEATURES].iloc[[-1]]
    if chosen == "Random Forest":
        model = RandomForestRegressor(n_estimators=80, max_depth=5, min_samples_leaf=5, max_features=.8, random_state=19, n_jobs=1)
    elif chosen == "Support Vector Regression":
        model = make_pipeline(StandardScaler(), SVR(C=.5, epsilon=.003, kernel="rbf"))
    elif chosen == "XGBoost":
        from xgboost import XGBRegressor
        model = XGBRegressor(n_estimators=100, max_depth=2, learning_rate=.035, subsample=.85, colsample_bytree=.8,
                             objective="reg:squarederror", n_jobs=1, verbosity=0, random_state=19)
    elif chosen == "ARIMA(1,0,1)":
        from statsmodels.tsa.arima.model import ARIMA
        model = None
    else:
        model = None
    with threadpool_limits(limits=1):
        if model is not None:
            model.fit(x, y); forecast_return = float(model.predict(latest_x)[0])
        elif chosen == "ARIMA(1,0,1)":
            forecast_return = float(ARIMA(y, order=(1,0,1), trend="c").fit().forecast(1).iloc[0])
        else:
            forecast_return = float(y.iloc[-1])
    last_close = float(frame.close.iloc[-1])
    chosen_prediction = np.asarray(predictions[chosen])
    # Trading simulation: one-session exposure when forecast direction is non-zero;
    # 10 bp charged whenever position changes. This is a research assumption.
    positions = np.sign(chosen_prediction)
    turnover = np.abs(np.diff(np.r_[0.0, positions]))
    net = positions * actual - turnover * .001
    wealth = np.cumprod(1 + net)
    drawdown = wealth / np.maximum.accumulate(wealth) - 1
    backtest = {"transaction_cost_bps_per_turnover": 10, "net_total_return": float(wealth[-1]-1),
                "annualized_sharpe": float(np.sqrt(252)*net.mean()/net.std(ddof=1)) if len(net)>1 and net.std(ddof=1)>0 else 0,
                "maximum_drawdown": float(drawdown.min()), "sessions": int(len(net))}
    diag = _diagnostics(d["return"].to_numpy())
    result={"symbol": "NIFTY50", "provider": "Yahoo Finance", "as_of": frame.index[-1].strftime("%Y-%m-%d"),
            "horizon": "one trading session", "model": chosen, "forecast_return": forecast_return,
            "forecast_close": last_close * (1 + forecast_return), "metrics": metrics,
            "dm_tests": _dm_tests(actual, predictions), "diagnostics": diag,
            "volatility_forecast": _garch_forecast(d["return"].to_numpy()), "backtest": backtest,
            "feature_importance": ([{"feature": f, "importance": float(v)} for f,v in sorted(zip(FEATURES, model.feature_importances_), key=lambda z:z[1], reverse=True)] if chosen == "Random Forest" else []),
            "test_period": {"from": d.index[-len(actual)].strftime("%Y-%m-%d"), "to": d.index[-1].strftime("%Y-%m-%d"), "sessions": int(len(actual))},
            "note": "Forecast estimates are uncertain; evaluation is historical and does not imply future performance."}
    if len(_CACHE)>8: _CACHE.clear()
    _CACHE[key]=copy.deepcopy(result)
    return result

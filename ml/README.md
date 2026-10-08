# Machine-learning pipeline

The training and evaluation implementation lives in `backend/model.py`. It builds trailing technical features, creates the five-session threshold target, splits chronologically, compares Logistic Regression and Random Forest, and calculates holdout metrics. If sklearn training is unavailable, the deterministic baseline is labeled explicitly and evaluated against the same holdout.


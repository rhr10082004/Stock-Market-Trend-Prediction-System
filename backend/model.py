import numpy as np
import pandas as pd
import hashlib
import copy
from .market import indicators

FEATURES = ["Open","High","Low","Close","Volume","Daily Return","SMA","EMA","RSI","MACD","Momentum","Volatility"]
LABELS = ["DOWN","SIDEWAYS","UP"]

_result_cache={}

def train_and_predict(frame):
    raw=pd.util.hash_pandas_object(frame,index=True).values.tobytes()
    key=hashlib.sha256(raw).hexdigest()
    if key in _result_cache:
        return copy.deepcopy(_result_cache[key])
    result=_train_and_predict(frame)
    if len(_result_cache)>32:
        _result_cache.clear()
    _result_cache[key]=copy.deepcopy(result)
    return result

def _train_and_predict(frame):
    d=indicators(frame)
    # Labels are known only after five trading sessions; remove the final unlabeled rows.
    future=d.Close.shift(-5)/d.Close-1
    d["target"]=np.select([future < -0.01, future > 0.01],[0,2],default=1)
    d=d.iloc[:-5].dropna()
    if len(d)<40: raise ValueError("Not enough cleaned observations to evaluate a prediction")
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return _baseline(d,frame)
    if len(d)<80:
        return _baseline(d,frame)
    split=int(len(d)*.8); X=d[FEATURES]; y=d.target.astype(int)
    models={"Logistic Regression":make_pipeline(StandardScaler(),LogisticRegression(max_iter=1000,class_weight="balanced")),"Random Forest":RandomForestClassifier(n_estimators=180,max_depth=6,min_samples_leaf=4,class_weight="balanced",random_state=17)}
    metrics={}; fitted={}
    try:
        for name,m in models.items():
            m.fit(X.iloc[:split],y.iloc[:split]); pred=m.predict(X.iloc[split:]); p,r,f,_=precision_recall_fscore_support(y.iloc[split:],pred,labels=[0,1,2],average="macro",zero_division=0)
            metrics[name]={"accuracy":round(float(accuracy_score(y.iloc[split:],pred)),4),"precision":round(float(p),4),"recall":round(float(r),4),"f1":round(float(f),4),"confusion_matrix":confusion_matrix(y.iloc[split:],pred,labels=[0,1,2]).tolist()}
            fitted[name]=m
    except Exception:
        return _baseline(d,frame)
    chosen=max(metrics,key=lambda k:metrics[k]["f1"])
    # Refit on all available labeled rows before the next-session inference.
    fitted[chosen].fit(X,y)
    latest=indicators(frame).iloc[[-1]][FEATURES]
    model=fitted[chosen]; idx=int(model.predict(latest)[0]); probs=model.predict_proba(latest)[0]; classes=list(model.classes_)
    result={"trend":LABELS[idx],"confidence":round(float(probs[classes.index(idx)]),4),"model":chosen,"metrics":metrics,"as_of":str(frame.index[-1].date()),"horizon":"5 trading sessions","target_rule":"UP if 5-session return > +1%; DOWN if below -1%; otherwise SIDEWAYS"}
    if chosen=="Random Forest": result["importance"]=[{"feature":f,"importance":round(float(v),4)} for f,v in sorted(zip(FEATURES,model.feature_importances_),key=lambda x:x[1],reverse=True)[:8]]
    else: result["importance"]=[]
    return result

def _rule(row):
    momentum=float(row["Momentum"]); rsi=float(row["RSI"])
    if momentum > .01 and rsi < 75: return 2
    if momentum < -.01 and rsi > 25: return 0
    return 1

def _baseline(d,frame):
    y=d.target.astype(int).tolist(); split=max(1,int(len(d)*.8)); actual=y[split:]
    predicted=[_rule(d.iloc[i]) for i in range(split,len(d))]
    matrix=[[sum(1 for a,p in zip(actual,predicted) if a==i and p==j) for j in range(3)] for i in range(3)]
    precision=[]; recall=[]; f1=[]
    for i in range(3):
        tp=matrix[i][i]; fp=sum(matrix[k][i] for k in range(3) if k!=i); fn=sum(matrix[i][k] for k in range(3) if k!=i)
        p=tp/(tp+fp) if tp+fp else 0; r=tp/(tp+fn) if tp+fn else 0
        precision.append(p); recall.append(r); f1.append(2*p*r/(p+r) if p+r else 0)
    metrics={"Baseline Demo Model":{"accuracy":round(sum(1 for a,p in zip(actual,predicted) if a==p)/len(actual),4),"precision":round(sum(precision)/3,4),"recall":round(sum(recall)/3,4),"f1":round(sum(f1)/3,4),"confusion_matrix":matrix}}
    latest=indicators(frame).iloc[-1]; trend_index=_rule(latest); score=min(.95,.55+min(abs(float(latest["Momentum"])),.08)*3)
    return {"trend":LABELS[trend_index],"confidence":round(score,4),"confidence_kind":"heuristic baseline score","model":"BASELINE DEMO MODEL","metrics":metrics,"as_of":str(frame.index[-1].date()),"horizon":"5 trading sessions","target_rule":"UP if 5-session return > +1%; DOWN if below -1%; otherwise SIDEWAYS","importance":[]}


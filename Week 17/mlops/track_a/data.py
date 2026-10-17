"""Load Telco churn data and inject reproducible synthetic drift."""
from pathlib import Path
from urllib.request import urlretrieve
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
DATA_PATH=ROOT/"data"/"telco_churn.csv"
URLS=["https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv","https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/main/data/Telco-Customer-Churn.csv"]
TARGET="Churn"
NUMERIC_FEATURES=["tenure","MonthlyCharges","TotalCharges"]
CATEGORICAL_FEATURES=["gender","SeniorCitizen","Partner","Dependents","PhoneService","MultipleLines","InternetService","OnlineSecurity","OnlineBackup","DeviceProtection","TechSupport","StreamingTV","StreamingMovies","Contract","PaperlessBilling","PaymentMethod"]
FEATURES=NUMERIC_FEATURES+CATEGORICAL_FEATURES

def load_dataset(path=None):
    path=Path(path) if path else DATA_PATH
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True); errors=[]
        for url in URLS:
            try:
                urlretrieve(url,path)
                if path.stat().st_size>10000: break
                path.unlink(missing_ok=True)
            except Exception as exc:
                errors.append(str(exc)); path.unlink(missing_ok=True)
        if not path.exists(): raise RuntimeError("Download failed. Place a permitted Telco churn CSV at data/telco_churn.csv. "+" ".join(errors))
    df=pd.read_csv(path); missing=sorted(set(FEATURES+[TARGET])-set(df.columns))
    if missing: raise ValueError(f"Missing dataset columns: {missing}")
    df=df.copy(); df["TotalCharges"]=pd.to_numeric(df["TotalCharges"].astype(str).str.strip(),errors="coerce")
    for col in df.select_dtypes(include=["object"]).columns: df[col]=df[col].map(lambda x:x.strip() if isinstance(x,str) else x)
    df=df.dropna(subset=NUMERIC_FEATURES+[TARGET]); df=df[df[TARGET].isin(["Yes","No"])].reset_index(drop=True)
    df["SeniorCitizen"]=df["SeniorCitizen"].astype(str)
    return df[FEATURES+[TARGET]]

def inject_synthetic_drift(frame,seed=17):
    if frame.empty: raise ValueError("Cannot inject drift into empty data")
    current=frame.copy().reset_index(drop=True); rng=np.random.default_rng(seed)
    current["MonthlyCharges"]=(current["MonthlyCharges"]+rng.normal(12,5,len(current))).clip(lower=0)
    current["Contract"]=rng.choice(["Month-to-month","One year","Two year"],len(current),p=[.78,.14,.08])
    idx=current.index[current[TARGET]=="No"].to_numpy(); count=min(len(idx),max(1,round(len(current)*.04)))
    if count: current.loc[rng.choice(idx,count,replace=False),TARGET]="Yes"
    return current

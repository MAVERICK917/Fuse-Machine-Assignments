"""FastAPI wrapper for the registered MLflow Production model."""
import os
import pandas as pd
import mlflow
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel,Field
from mlops.track_a.data import FEATURES
NAME=os.getenv("MLFLOW_MODEL_NAME","telco-churn-classifier"); URI=os.getenv("MLFLOW_TRACKING_URI","sqlite:///mlflow.db"); app=FastAPI(title="Week 17 Telco Churn API"); _model=None
class PredictionRequest(BaseModel): records:list[dict]=Field(min_length=1,max_length=500)
def get_model():
 global _model
 if _model is None: mlflow.set_tracking_uri(URI); _model=mlflow.pyfunc.load_model(f"models:/{NAME}/Production")
 return _model
@app.get("/health")
def health(): return {"status":"ok","model":NAME,"stage":"Production"}
@app.post("/predict")
def predict(payload:PredictionRequest):
 frame=pd.DataFrame(payload.records); missing=sorted(set(FEATURES)-set(frame.columns))
 if missing: raise HTTPException(status_code=422,detail=f"Missing feature columns: {missing}")
 try:
  values=get_model().predict(frame[FEATURES]); return {"model":NAME,"predictions":[{"prediction":str(v),"churn":str(v)=="Yes"} for v in values]}
 except Exception as exc: raise HTTPException(status_code=503,detail=f"Registered model unavailable: {exc}") from exc

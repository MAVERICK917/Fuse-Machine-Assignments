"""Train, compare, track and register three churn models."""
import json,os
from pathlib import Path
import joblib,mlflow,mlflow.sklearn,pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score,roc_auc_score,ConfusionMatrixDisplay,RocCurveDisplay,classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from mlops.track_a.data import CATEGORICAL_FEATURES,FEATURES,NUMERIC_FEATURES,TARGET,load_dataset
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"reports"/"track_a"
URI=os.getenv("MLFLOW_TRACKING_URI","sqlite:///mlflow.db"); EXP="week17-track-a-telco-churn"; NAME="telco-churn-classifier"
def pipeline(estimator):
    num=Pipeline([("imputer",SimpleImputer(strategy="median")),("scale",StandardScaler())]); cat=Pipeline([("imputer",SimpleImputer(strategy="most_frequent")),("onehot",OneHotEncoder(handle_unknown="ignore"))])
    prep=ColumnTransformer([("numeric",num,NUMERIC_FEATURES),("categorical",cat,CATEGORICAL_FEATURES)])
    return Pipeline([("preprocess",prep),("classifier",estimator)])
def configs():
    return [("logistic_regression",LogisticRegression(C=.5,class_weight="balanced",max_iter=1500,solver="liblinear"),{"family":"LogisticRegression","C":.5,"class_weight":"balanced"}),("random_forest_shallow",RandomForestClassifier(n_estimators=160,max_depth=8,min_samples_leaf=3,class_weight="balanced",random_state=17,n_jobs=-1),{"family":"RandomForestClassifier","n_estimators":160,"max_depth":8,"min_samples_leaf":3}),("random_forest_deep",RandomForestClassifier(n_estimators=260,max_depth=14,min_samples_leaf=2,class_weight="balanced_subsample",random_state=17,n_jobs=-1),{"family":"RandomForestClassifier","n_estimators":260,"max_depth":14,"min_samples_leaf":2})]
def train(data_csv=None):
    mlflow.set_tracking_uri(URI); mlflow.set_experiment(EXP); OUT.mkdir(parents=True,exist_ok=True); df=load_dataset(data_csv)
    xtr,xte,ytr,yte=train_test_split(df[FEATURES],df[TARGET],test_size=.25,random_state=17,stratify=df[TARGET]); rows=[]
    for name,estimator,params in configs():
        model=pipeline(estimator)
        with mlflow.start_run(run_name=name) as run:
            mlflow.set_tags({"track":"A","dataset":"IBM Telco Customer Churn"}); mlflow.log_params({k:str(v) for k,v in params.items()}); mlflow.log_params({"seed":17,"test_fraction":.25})
            model.fit(xtr,ytr); pred=model.predict(xte); classes=list(model.named_steps["classifier"].classes_); prob=model.predict_proba(xte)[:,classes.index("Yes")]
            metrics={"accuracy":float(accuracy_score(yte,pred)),"precision":float(precision_score(yte,pred,pos_label="Yes",zero_division=0)),"recall":float(recall_score(yte,pred,pos_label="Yes",zero_division=0)),"f1":float(f1_score(yte,pred,pos_label="Yes",zero_division=0)),"roc_auc":float(roc_auc_score((yte=="Yes").astype(int),prob))}; mlflow.log_metrics(metrics)
            d=OUT/name; d.mkdir(parents=True,exist_ok=True); (d/"classification_report.json").write_text(json.dumps(classification_report(yte,pred,output_dict=True,zero_division=0),indent=2))
            fig,ax=plt.subplots(figsize=(5,4)); ConfusionMatrixDisplay.from_predictions(yte,pred,labels=["No","Yes"],display_labels=["No churn","Churn"],ax=ax,colorbar=False); fig.tight_layout(); fig.savefig(d/"confusion_matrix.png",dpi=140); plt.close(fig)
            fig,ax=plt.subplots(figsize=(5,4)); RocCurveDisplay.from_predictions((yte=="Yes").astype(int),prob,ax=ax); fig.tight_layout(); fig.savefig(d/"roc_curve.png",dpi=140); plt.close(fig)
            joblib.dump(model,d/"model.joblib"); mlflow.sklearn.log_model(model,artifact_path="model",signature=infer_signature(xtr.head(4),model.predict(xtr.head(4))),input_example=xtr.head(2)); mlflow.log_artifacts(str(d),artifact_path="evaluation")
            rows.append({"model":name,"run_id":run.info.run_id,**metrics,**params})
    table=pd.DataFrame(rows).sort_values(["f1","roc_auc","recall"],ascending=False); table.to_csv(OUT/"model_comparison.csv",index=False); best=table.iloc[0]
    version=mlflow.register_model(f"runs:/{best['run_id']}/model",NAME); client=MlflowClient(tracking_uri=URI)
    client.transition_model_version_stage(NAME,version.version,stage="Staging",archive_existing_versions=True); client.transition_model_version_stage(NAME,version.version,stage="Production",archive_existing_versions=True)
    meta={"model_name":NAME,"version":str(version.version),"winning_run_id":str(best.run_id),"selection_rule":"highest F1, then ROC-AUC, then recall","metrics":{k:float(best[k]) for k in ["accuracy","precision","recall","f1","roc_auc"]}}
    (OUT/"registered_model.json").write_text(json.dumps(meta,indent=2))
    with mlflow.start_run(run_name="model-comparison"):
        mlflow.log_params({"selected_model":str(best.model),"selection_rule":meta["selection_rule"]}); mlflow.log_metrics({"winner_"+k:v for k,v in meta["metrics"].items()}); mlflow.log_artifact(str(OUT/"model_comparison.csv")); mlflow.log_artifact(str(OUT/"registered_model.json"))
    print(table.to_string(index=False)); print(f"Registered {NAME} v{version.version}: Staging -> Production"); return table
if __name__=="__main__":
 import argparse
 p=argparse.ArgumentParser(); p.add_argument("--data-csv"); train(p.parse_args().data_csv)

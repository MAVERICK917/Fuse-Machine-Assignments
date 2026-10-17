"""Run Evidently drift detection and log custom drift deltas."""
import json,os
from pathlib import Path
import mlflow
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report
from mlops.track_a.data import TARGET,inject_synthetic_drift,load_dataset
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"reports"/"track_a"
def monitor(data_csv=None):
 df=load_dataset(data_csv).sample(frac=1,random_state=17).reset_index(drop=True); split=int(.7*len(df)); ref=df.iloc[:split].copy(); cur=inject_synthetic_drift(df.iloc[split:].copy(),1701); OUT.mkdir(parents=True,exist_ok=True)
 report=Report(metrics=[DataDriftPreset()]); report.run(reference_data=ref,current_data=cur); html=OUT/"evidently_drift_report.html"; report.save_html(str(html))
 m={"reference_rows":len(ref),"current_rows":len(cur),"reference_churn_rate":float((ref[TARGET]=="Yes").mean()),"current_churn_rate":float((cur[TARGET]=="Yes").mean()),"churn_rate_delta":float((cur[TARGET]=="Yes").mean()-(ref[TARGET]=="Yes").mean()),"reference_monthly_charges_mean":float(ref.MonthlyCharges.mean()),"current_monthly_charges_mean":float(cur.MonthlyCharges.mean()),"monthly_charges_mean_delta":float(cur.MonthlyCharges.mean()-ref.MonthlyCharges.mean()),"reference_month_to_month_share":float((ref.Contract=="Month-to-month").mean()),"current_month_to_month_share":float((cur.Contract=="Month-to-month").mean()),"month_to_month_share_delta":float((cur.Contract=="Month-to-month").mean()-(ref.Contract=="Month-to-month").mean()),"engineered_drift":["MonthlyCharges","Contract",TARGET],"interpretation":"Synthetic drift deliberately injected; investigate source pipelines, contract mix and calibration before production rollout."}
 js=OUT/"custom_drift_metrics.json"; js.write_text(json.dumps(m,indent=2)); mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI","sqlite:///mlflow.db")); mlflow.set_experiment("week17-track-a-telco-churn")
 with mlflow.start_run(run_name="evidently-synthetic-drift"):
  mlflow.set_tags({"track":"A","drift_data":"synthetic"}); mlflow.log_params({"reference_fraction":.7,"split_seed":17,"drift_seed":1701}); mlflow.log_metrics({k:m[k] for k in ["churn_rate_delta","monthly_charges_mean_delta","month_to_month_share_delta"]}); mlflow.log_artifact(str(html)); mlflow.log_artifact(str(js))
 print(json.dumps(m,indent=2)); return m
if __name__=="__main__":
 import argparse
 p=argparse.ArgumentParser(); p.add_argument("--data-csv"); monitor(p.parse_args().data_csv)

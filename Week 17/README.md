# Week 17 — MLOps

This project implements both tracks in `W17_MLOps_Assignment.pdf`. The Week 15/16 assistant source is expected under `backend/` and `frontend/` (see setup below). In your repository, copy the contents of `Week16/` into this folder before committing so the Week 16 agent remains part of the submission.

## Setup

Use Python 3.12 and uv. From this directory, first bring in the existing Week 16 code and create the lockfile with network access:

```bash
./scripts/carry_forward_week16.sh ../Week16
uv lock
uv sync
cp backend/.env.example backend/.env  # optional offline; needed for live providers
```

`uv.lock` is generated from the project dependency constraints on your machine and should be committed. This environment could not resolve it because outbound package downloads are blocked.

## Track A — Telco churn

```bash
uv run python -m mlops.track_a.train
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000
uv run python -m mlops.track_a.monitor
uv run uvicorn mlops.track_a.serve:app --host 127.0.0.1 --port 8000
```

Training downloads the IBM Telco churn sample if available; alternatively place a permitted dataset at `data/telco_churn.csv`. It compares logistic regression and two random-forest configurations using a stratified held-out split. Every run logs hyperparameters, accuracy, precision, recall, F1, ROC-AUC, model, classification report, confusion matrix and ROC curve. The generated `reports/track_a/model_comparison.csv` provides the side-by-side comparison. The highest-F1 model (ROC-AUC then recall as tie-breakers) is registered and moved through Staging and Production. Use actual run metrics in your final write-up; results are generated locally and are not fabricated in this repo.

The monitor uses a 70/30 reference/current split and deliberately shifts MonthlyCharges, Contract and a small share of Churn labels. It creates an Evidently HTML report, logs it to MLflow and writes custom drift deltas. This is synthetic drift, not live production monitoring.

API: `GET /health`; `POST /predict` with `{"records": [{...customer features...}]}`. Train/register first.

## Track B — agentic AI MLOps

```bash
uv run python -m mlops.track_b.evaluate
uv run python -m backend.app.evaluation.harness
```

Three prompts are stored in `mlops/track_b/prompts/`. The evaluator calls the Week 16 `run_question_agent` loop with deterministic scripted planners and tool stubs in offline mode, logs per-case metrics and full JSON traces, and writes comparison CSV/HTML outputs. This measures loop/control-flow regression, not live LLM answer quality. For provider-backed evaluation, configure `backend/.env` and run `uv run python -m mlops.track_b.evaluate --mode live`; this can incur API or local inference costs.

Optional LLM-as-judge evaluation: create a CSV with `response` and `reference_answer` columns, set `OPENAI_API_KEY`, then run `uv run python -m mlops.track_b.evidently_judge --responses path/to/responses.csv`. It checks reference correctness and information preservation, saves the verdict CSV and an HTML report.

## Outputs

- MLflow local store: `mlflow.db`
- Track A reports: `reports/track_a/`
- Track B reports: `reports/track_b/`
- Full traces: `reports/traces/`
- Tests: `uv run pytest -q`

Airflow is optional and is not implemented. After running both tracks, add measured comparison values and your interpretation to this README.

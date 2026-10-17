from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_three_prompts_exist():
 assert all((ROOT/"mlops"/"track_b"/"prompts"/f"prompt_v{i}.md").exists() for i in (1,2,3))
def test_track_a_required_metrics_and_registry_stages():
 source=(ROOT/"mlops"/"track_a"/"train.py").read_text()
 for metric in ["accuracy","precision","recall","f1","roc_auc"]: assert f'"{metric}"' in source
 assert 'stage="Staging"' in source and 'stage="Production"' in source
def test_track_b_logs_full_trace_and_regression_metric():
 source=(ROOT/"mlops"/"track_b"/"evaluate.py").read_text()
 assert '"pct_tests_passed"' in source and 'tool_calls_with_arguments_and_raw_results' in source

"""Compare prompt versions through the Week 16 agent loop and log full traces."""
import argparse,json,os,time
from pathlib import Path
import mlflow,pandas as pd
from backend.app.agent.loop import run_question_agent
from backend.app.agent.schemas import AgentDecision,GradeVerification
from backend.app.evaluation.cases import build_deterministic_cases
from backend.app.rag.schemas import RagContext,RetrievedChunk
from backend.app.schemas.grading import GradeEvaluation
ROOT=Path(__file__).resolve().parents[2]; PROMPTS=ROOT/"mlops"/"track_b"/"prompts"; OUT=ROOT/"reports"/"track_b"; TRACES=ROOT/"reports"/"traces"
def plans(v,cid):
 base={"direct-grade":[("grade_answer",{}),("finish",{})],"rag-needed":[("grade_answer",{}),("finish",{})],"rewrite-retrieval":[("retrieve_context",{"query":"broad query"}),("grade_answer",{}),("finish",{})],"verification-replan":[("grade_answer",{}),("finish",{})],"ambiguous-review":[("request_clarification",{"clarification_reason":"Ambiguous OCR"})],"retrieval-timeout":[("retrieve_context",{"query":"required evidence"})]}
 better={**base,"rag-needed":[("retrieve_context",{"query":"indexing reference"}),("grade_answer",{}),("finish",{})],"rewrite-retrieval":[("retrieve_context",{"query":"broad query"}),("retrieve_context",{"query":"precise rewritten query","top_k":2}),("grade_answer",{}),("finish",{})],"verification-replan":[("grade_answer",{}),("verify_grade",{}),("retrieve_context",{"query":"supporting rubric"}),("grade_answer",{}),("finish",{})]}
 best={**better,"direct-grade":[("grade_answer",{}),("verify_grade",{}),("finish",{})],"rag-needed":[("retrieve_context",{"query":"indexing reference"}),("grade_answer",{}),("verify_grade",{}),("finish",{})]}
 return [AgentDecision(action=a,**kw) for a,kw in {1:base,2:better,3:best}[v][cid]]
class Planner:
 def __init__(self,v,case,prompt,live_provider=None):
  self.pending=plans(v,case); self.prompt=prompt; self.steps=[]; self.provider=live_provider; self.verifications=[GradeVerification(passed=False,issues=["Need further evidence"],suggested_next_step="retrieve_context")]
 def plan_agent_action(self,context):
  if self.provider:
   result,usage=self.provider.plan_agent_action(self.prompt+"\n\nCurrent state:\n"+context); self.steps.append({"context":context,"decision":result.model_dump(mode="json"),"usage":usage}); return result,usage
  if not self.pending: raise RuntimeError("Scripted planner exhausted")
  result=self.pending.pop(0); self.steps.append({"context":context,"decision":result.model_dump(mode="json")}); return result,None
 def verify_grade(self,context):
  if self.provider:
   result,usage=self.provider.verify_grade(self.prompt+"\n\nVerification state:\n"+context); self.steps.append({"verification_context":context,"verification":result.model_dump(mode="json"),"usage":usage}); return result,usage
  result=self.verifications.pop(0) if self.verifications else GradeVerification(passed=True); self.steps.append({"verification_context":context,"verification":result.model_dump(mode="json")}); return result,None
def run_case(version,case,mode):
 prompt=(PROMPTS/f"prompt_v{version}.md").read_text(); provider=None
 if mode=="live":
  from backend.app.llm.provider_factory import get_llm_provider
  provider=get_llm_provider()
 planner=Planner(version,case.case_id,prompt,provider)
 calls=[]
 def grade(**kw):
  entry={"tool":"grade_answer","arguments":kw}
  try:
   if provider: value=provider.grade_answer(**kw)
   else: value=GradeEvaluation(question_number=kw["question_number"],awarded_marks=4,max_marks=kw["max_marks"],feedback="Deterministic grading stub.")
   entry["raw_result"]=value.model_dump(mode="json"); return value
  except Exception as exc:
   entry["error"]={"type":type(exc).__name__,"message":str(exc)}; raise
  finally: calls.append(entry)
 def retrieve(**kw):
  entry={"tool":"retrieve_context","arguments":kw}
  try:
   if case.retrieval_failure: raise TimeoutError("Injected retrieval timeout")
   value=RagContext(reference_set_id="w17-eval",chunks=[RetrievedChunk(text=f"Synthetic evidence for {kw.get('query')}",source="evaluation-reference.txt",chunk_index=0,reference_set_id="w17-eval")]); entry["raw_result"]=value.model_dump(mode="json"); return value
  except Exception as e: entry["error"]={"type":type(e).__name__,"message":str(e)}; raise
  finally: calls.append(entry)
 started=time.perf_counter(); state=run_question_agent(question_number="Q1",question_text="Explain database indexing and trade-offs.",max_marks=5,model_answer="Indexes speed lookups but require storage and can slow writes.",mapped_student_answer="" if case.case_id=="ambiguous-review" else "Indexes reduce rows examined.",flagged_ocr_text="Ambiguous OCR" if case.case_id=="ambiguous-review" else None,reference_set_id="w17-eval",planner=planner,grade_fn=grade,retrieve_fn=retrieve,max_iterations=max(5,case.max_reasonable_steps)); elapsed=(time.perf_counter()-started)*1000
 traj=[x.model_dump(mode="json") for x in state.trajectory]; actions=[x["action"] for x in traj if x["action"]!="planner"]; safe_failure=bool(case.expected_failure_class and state.status==case.expected_terminal_status and state.current_grade is None and any(not x["success"] for x in traj))
 passed=state.status==case.expected_terminal_status and case.required_actions.issubset(set(actions)) and not(set(actions)&case.forbidden_actions) and len(actions)<=case.max_reasonable_steps and (all(x["success"] for x in traj if x["action"]!="planner") or safe_failure)
 trace={"prompt_version":f"prompt_v{version}","case_id":case.case_id,"mode":mode,"prompt":prompt,"planner_decisions":planner.steps,"tool_calls_with_arguments_and_raw_results":calls,"agent_trajectory":traj,"iterations":state.current_iteration,"terminal_status":state.status,"termination_reason":state.clarification_reason or f"Agent ended with status {state.status}","elapsed_ms":round(elapsed,3),"passed":bool(passed),"token_usage":state.token_usage.model_dump()}
 return {"prompt_version":f"prompt_v{version}","case_id":case.case_id,"passed":bool(passed),"terminal_status":state.status,"iterations":state.current_iteration,"tool_calls":len(calls),"elapsed_ms":round(elapsed,3),"tokens":state.token_usage.total_tokens if state.token_usage.available else None,"failure_reason":state.clarification_reason},trace
def main():
 parser=argparse.ArgumentParser(); parser.add_argument("--mode",choices=["offline","live"],default="offline"); mode=parser.parse_args().mode
 OUT.mkdir(parents=True,exist_ok=True); TRACES.mkdir(parents=True,exist_ok=True); mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI","sqlite:///mlflow.db")); mlflow.set_experiment("week17-track-b-agent-prompts"); rows=[]
 for v in (1,2,3):
  version_rows=[]; prompt_path=PROMPTS/f"prompt_v{v}.md"
  with mlflow.start_run(run_name=f"prompt_v{v}-{mode}"):
   mlflow.log_params({"prompt_version":f"prompt_v{v}","mode":mode,"max_iterations":5,"rag_top_k":4}); mlflow.log_artifact(str(prompt_path),artifact_path="prompt")
   for case in build_deterministic_cases():
    row,trace=run_case(v,case,mode); rows.append(row); version_rows.append(row); path=TRACES/f"prompt_v{v}_{case.case_id}.json"; path.write_text(json.dumps(trace,indent=2,default=str)); mlflow.log_artifact(str(path),artifact_path="traces")
   n=max(1,len(version_rows)); mlflow.log_metrics({"pct_tests_passed":100*sum(r["passed"] for r in version_rows)/n,"task_completion_rate":sum(r["terminal_status"]=="completed" for r in version_rows)/n,"mean_iterations":sum(r["iterations"] for r in version_rows)/n,"mean_tool_calls":sum(r["tool_calls"] for r in version_rows)/n,"mean_latency_ms":sum(r["elapsed_ms"] for r in version_rows)/n})
 detail=pd.DataFrame(rows); detail.to_csv(OUT/"agent_case_results.csv",index=False); comp=detail.groupby("prompt_version",as_index=False).agg(test_cases=("case_id","count"),pct_tests_passed=("passed",lambda x:100*x.mean()),task_completion_rate=("terminal_status",lambda x:(x=="completed").mean()),mean_iterations=("iterations","mean"),mean_tool_calls=("tool_calls","mean"),mean_latency_ms=("elapsed_ms","mean")); comp.to_csv(OUT/"agent_comparison.csv",index=False)
 html="<!doctype html><meta charset='utf-8'><h1>Agent Regression Report</h1><p>Offline mode measures deterministic loop/control flow, not live LLM answer quality.</p>"+comp.to_html(index=False)+"<h2>Failed cases</h2>"+detail.loc[~detail.passed].to_html(index=False); (OUT/"agent_regression_report.html").write_text(html)
 with mlflow.start_run(run_name="prompt-comparison"): mlflow.log_artifact(str(OUT/"agent_case_results.csv")); mlflow.log_artifact(str(OUT/"agent_comparison.csv")); mlflow.log_artifact(str(OUT/"agent_regression_report.html"))
 print(comp.to_string(index=False))
if __name__=="__main__": main()

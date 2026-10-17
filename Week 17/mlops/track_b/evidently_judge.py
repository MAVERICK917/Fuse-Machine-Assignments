"""Reference-based LLM judge for response/reference CSV pairs, with HTML output."""
import argparse,os,json
from pathlib import Path
import pandas as pd
from openai import OpenAI
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"reports"/"track_b"
def run(path):
 if not os.getenv("OPENAI_API_KEY"): raise RuntimeError("Set OPENAI_API_KEY to run the LLM judge")
 df=pd.read_csv(path)
 if not {"response","reference_answer"}.issubset(df.columns): raise ValueError("CSV requires response,reference_answer columns")
 client=OpenAI(); results=[]
 for row in df.itertuples(index=False):
  checks={}
  for name,criterion in [("reference_correctness","Does the candidate contradict the reference?"),("information_preservation","Does the candidate omit important reference information?")]:
   answer=client.chat.completions.create(model=os.getenv("EVIDENTLY_LLM_MODEL","gpt-4o-mini"),temperature=0,response_format={"type":"json_object"},messages=[{"role":"system","content":"You are a strict binary evaluator. Return JSON only: {pass:boolean,reason:string}. Equivalent wording is acceptable."},{"role":"user","content":f"Criterion: {criterion}\nReference: {row.reference_answer}\nCandidate: {row.response}"}])
   checks[name]=json.loads(answer.choices[0].message.content)
  results.append({"response":row.response,"reference_answer":row.reference_answer,**checks})
 OUT.mkdir(parents=True,exist_ok=True); out=OUT/"evidently_llm_judge_results.csv"; pd.DataFrame(results).to_csv(out,index=False)
 html="<!doctype html><meta charset='utf-8'><h1>LLM-as-a-judge regression checks</h1><p>Checks: reference correctness and information preservation. Review verdicts and reasoning manually.</p>"+pd.DataFrame(results).to_html(index=False); hp=OUT/"evidently_llm_judge_report.html"; hp.write_text(html); return hp
def main():
 p=argparse.ArgumentParser(); p.add_argument("--responses",required=True); print(run(p.parse_args().responses))
if __name__=="__main__": main()

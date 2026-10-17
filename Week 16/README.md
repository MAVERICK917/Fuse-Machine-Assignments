# AI-Assisted Answer Sheet Grading System

## Overview

This is a production-style FastAPI and Streamlit application that automatically grades scanned student answer sheets. It takes the original notebook prototype and restructures it into a backend API, then builds on it with Gemini structured grading, OCR, semantic answer routing, true RAG backed by ChromaDB, reliability safeguards, and a straightforward web interface for teachers.

## Features

- Upload exam/model-answer files along with student answer-sheet PDFs.
- Read handwritten answers with TrOCR.
- Match OCR answer segments to the right questions using all-MiniLM-L6-v2 sentence embeddings.
- Optionally load rubric or reference documents into ChromaDB.
- Fetch question-specific RAG context at grading time.
- Grade with Gemini using prompt engineering, configurable temperature / top_p, function calling, and Pydantic-validated structured output.
- Retry external LLM calls, and switch from Gemini to a local vLLM endpoint when it makes sense.
- Apply rate limits to the costly API endpoints.
- Run batch grading through asynchronous API handlers, with capped OCR and LLM concurrency.
- Save grading results in SQLite.
- Offer a Streamlit frontend for teacher workflows.
- Run locally or through Docker Compose.

## Architecture

The system architecture and the Week 16 agentic loop are described here:

[View Architecture Diagram](docs/architecture.md)

## Current AI Pipeline

```
exam/model answer/reference docs
  → text extraction
  → RAG chunking
  → all-MiniLM-L6-v2 embeddings
  → persistent ChromaDB
  → student PDF OCR with TrOCR
  → semantic answer-to-question mapping
  → question-aware RAG retrieval
  → Gemini structured grading with function calling
  → retry and Gemini-to-vLLM fallback
  → GradeEvaluation validation
  → SQLite persistence
```

## Semantic Mapping vs. RAG

Semantic mapping decides which exam question each piece of OCR text from a student's answer sheet most likely belongs to. It brings in no outside knowledge.

RAG serves a different purpose: supporting the grading step. The official exam/model answers and any optional rubric or reference documents are split into chunks, embedded, stored in ChromaDB, looked up by `reference_set_id`, and handed to the LLM as supporting context.

## Technology Stack

- FastAPI, Pydantic, Uvicorn
- Streamlit
- Gemini via the Google Gen AI SDK
- vLLM via its OpenAI-compatible HTTP API
- TrOCR via Transformers/PyTorch
- SentenceTransformers and scikit-learn
- ChromaDB persistent vector storage
- SQLite
- Docker and Docker Compose

## Project Structure

```
backend/app/api/          FastAPI route handlers
backend/app/core/         configuration and rate limiting
backend/app/database/     SQLite helper functions
backend/app/llm/          Gemini, vLLM, Ollama, retry, fallback, tools
backend/app/rag/          ingestion, vector store, retrieval
backend/app/services/     OCR, parsing, embeddings, grading workflow
frontend/app.py           Streamlit teacher interface
docs/architecture.md      architecture diagram
docs/week15-checklist.md  requirements scorecard
tests/                    pytest suite
```

## Environment Variables

Copy the example file, then fill in your local values:

```bash
cp backend/.env.example backend/.env
```

Put your Gemini key in `backend/.env`:

```
GEMINI_API_KEY=
```

Key settings:

```
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.6-flash
LLM_TEMPERATURE=0.2
LLM_TOP_P=0.9
LLM_RETRY_ATTEMPTS=3
ENABLE_VLLM_FALLBACK=true
VLLM_BASE_URL=http://localhost:8001/v1
VLLM_MODEL=TinyLlama/TinyLlama-1.1B-Chat-v1.0
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW_SECONDS=60
OCR_CONCURRENCY=1
LLM_CONCURRENCY=3
CHROMA_PATH=../data/chroma
```

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Poppler is needed for PDF conversion. On Ubuntu/Debian, install it with:

```bash
sudo apt-get install poppler-utils
```

If Poppler is not on your PATH, point `POPPLER_PATH` at it in `backend/.env`.

## Gemini API Key Setup

1. Copy `backend/.env.example` to `backend/.env`.
2. Enter your key after `GEMINI_API_KEY=`.
3. Leave `LLM_PROVIDER=gemini` as it is.
4. The model used is whatever `GEMINI_MODEL` specifies.

The real key must stay on your machine only. Never place it in the README, tests, Docker Compose file, or source code.

## Running the Backend

```bash
.venv/bin/uvicorn backend.app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

## Running the Streamlit Frontend

```bash
BACKEND_URL=http://127.0.0.1:8000 .venv/bin/streamlit run frontend/app.py
```

Open the Streamlit URL, upload the exam/model-answer file, optionally ingest rubric or reference files, then upload the student answer-sheet PDFs and begin grading.

## Running vLLM

The backend talks to vLLM through its OpenAI-compatible endpoint.

```bash
python -m vllm.entrypoints.openai.api_server \
  --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --host 0.0.0.0 \
  --port 8001
```

Running vLLM inference locally in full needs a suitable GPU with enough VRAM, plus time to download the model. This repository provides the integration and the Docker Compose service. Do not state that vLLM inference works unless that service has actually produced a response in your own environment.

## Running Tests

```bash
.venv/bin/python -m compileall backend frontend tests
.venv/bin/python -m pytest -q
```

## Docker

```bash
docker compose up --build
```

Compose launches:

- backend on port 8000
- frontend on port 8501
- vllm on host port 8001
- persistent volumes for the app and the Hugging Face cache

Docker Compose takes its substitution values from shell variables or a root-level `.env` file. It does not read `backend/.env`, because `docker compose config` expands `env_file` values and could print secrets to the terminal.

## API Endpoints

```
GET  /api/health
POST /api/rag/ingest
POST /api/grading/evaluate
```

`POST /api/rag/ingest` takes an exam/model-answer file plus optional reference files, and returns a `reference_set_id`.

`POST /api/grading/evaluate` takes an exam/model-answer file, one or more student PDFs, and an optional `reference_set_id`.

## Reliability

- **Retry:** Calls to external LLMs are retried using bounded exponential backoff.
- **Fallback:** Gemini is the primary provider; once retries are exhausted, retryable external errors cause a switch to vLLM.
- **Rate limiting:** Costly endpoints respond with HTTP 429 once the configured request limit is exceeded.
- **Graceful errors:** Invalid uploads return 400, and dependency failures return 503 where relevant. Unexpected failures return safe 500 responses that do not leak secrets.

## Performance

- Async API handlers stop expensive requests from blocking the event loop.
- OCR and semantic mapping run in worker threads with bounded concurrency.
- LLM grading calls are also capped, so the number of simultaneous provider calls never grows unchecked.
- The TrOCR and SentenceTransformer models are cached and reused by the service loaders.
- ChromaDB retrieval keeps context small through `RAG_TOP_K`.

### ONNX Decision

ONNX was evaluated but isn't needed for this implementation:

- This application cannot convert hosted Gemini to ONNX.
- Local generative LLM inference is already optimized through vLLM, which provides PagedAttention and request batching.
- TrOCR stays a Transformers/PyTorch model in this project.
- SentenceTransformer inference is already reused and bounded.

For these reasons, ONNX conversion is recorded as not applicable to the final assignment implementation.

## Deployment Instructions

For a local Docker deployment:

```bash
cp backend/.env.example backend/.env
# fill in backend/.env for direct backend runs
# for Compose, also export GEMINI_API_KEY or create an ignored root .env
docker compose up --build
```

For a VPS or server deployment:

1. Install Docker and Docker Compose.
2. Copy the project onto the server.
3. Create `backend/.env` from `backend/.env.example`.
4. Set `GEMINI_API_KEY`, model names, paths, and limits.
5. Make sure the server has a GPU with enough VRAM if vLLM will do real local inference.
6. Run `docker compose up --build -d`.
7. If the app will be publicly reachable, put a reverse proxy such as Nginx or Caddy in front of ports 8000 and 8501.

A cloud deployment could reuse the same container layout, though this submission does not require any cloud-specific setup.

## Limitations

- The TrOCR model weights must be downloaded and cached before the first complete OCR runtime check.
- Verifying vLLM at runtime needs enough GPU/VRAM and time to download the model.
- The in-process rate limiter works for a single backend process; a distributed deployment should use shared storage such as Redis.
- OCR accuracy depends on how clear the scan and the handwriting are.
- Local files such as `grades.db` and `data/student_pdfs/s1.pdf` may hold real historical data rather than synthetic data, and Git ignores them.

---

# Week 16 Work

## Context Engineering Technique

On every pass, the planner receives a compact context pack: the question, the reference answer, the mapped student answer, any flagged OCR text, up to four retrieved chunks, the latest grade or verification result, and a brief list of recent actions. The complete trajectory remains in `AgentState`, so the model doesn't get the whole history resent each time.

## Agentic Pattern

Each question gets its own agent. The agent picks one of five actions: `retrieve_context`, `grade_answer`, `verify_grade`, `request_clarification`, or `finish`. Python executes the chosen action, updates that question's state, and asks the planner for the next step. The loop stops when the agent finishes, requests review, encounters a tool error, or reaches `AGENT_MAX_ITERATIONS` (default 5). Nothing forces a retrieve-then-grade order.

The Week 15 components that already worked, such as uploads, parsing, OCR, answer mapping, and database access, are reused as they were. Week 16 only replaces the per-question decision step, which previously retrieved once and graded once.

## Evaluation Harness

The evaluation code is intentionally small and kept local in `backend/app/evaluation/`. It runs six scripted cases through `run_question_agent` and records each final outcome, the actions selected, the path length, any failures, and token information. Results are written to `docs/evaluation-results.md`. These cases make no calls to an external model, so the LLM token count is zero.

## Skill vs. Agent

Here, a skill is one of the project's fixed capabilities: OCR, answer mapping, retrieval, mark validation, or database persistence. The agent is the component that, after looking at the current result, decides which capability to use next. It has no ability to write to SQLite or to call arbitrary Python functions.

## Token and Cost Accounting

`AgentState.token_usage` tracks input, output, and total token counts for each question. Usage data is read from Gemini's usage metadata and from the OpenAI-compatible `usage` object returned by vLLM whenever they are available, including during grading retries and fallback calls. Every trajectory entry stores the usage for its own action. Ollama doesn't expose comparable counts here, so those values are marked unavailable. No dollar cost has been added, because there was no live provider run and no pricing data to base one on.

## Failure Injection Test

In the `retrieval-timeout` case, the harness forces the retrieval function to raise a `TimeoutError`. The agent logs the failed call and returns `manual_review`; it neither fabricates evidence, nor calls grading, nor inserts a final grade row. This was classified as a soft failure, since the problem stayed contained.

## Tool vs. Agent Boundary

The model is limited to choosing from the short action list and supplying arguments that get validated. Python runs the tools and takes care of errors, limits, and terminal states. Writing grades to SQLite is done by the application, never by the model. A question routed to manual review keeps that status and receives no artificial final grade row.

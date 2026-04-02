---
title: SRE Incident Environment
emoji: "🔧"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
license: mit
tags:
  - openenv
  - fastapi
  - simulation
  - sre
  - benchmarking
---

# SRE Incident Environment

An OpenEnv-compatible simulation environment for SRE incident response, benchmarking, and agent evaluation.

This project models realistic production incidents with partial observability, dependency cascades, deterministic grading, replay export, and browser-based human and AI workflows. It is designed for:

- training and evaluating autonomous agents
- benchmarking provider/model behavior on operational tasks
- rehearsing incident response workflows in a safe environment
- comparing human and AI incident handling side by side

## Highlights

- Deterministic incident simulator with typed `Observation`, `Action`, and `Reward` models
- Multi-step operational workflow: triage, investigation, mitigation, validation, diagnosis
- Three difficulty tiers: `easy`, `medium`, `hard`
- Human-in-the-loop browser console with separate `Tasks`, `Session`, `Runtime`, and `AI Control` views
- Replay persistence, benchmark history, and session comparison
- Scripted and provider-driven baselines for OpenAI-compatible runtimes
- Strong local validation with API and environment test coverage

## Why This Project Exists

Most agent evaluations focus on static question answering or narrow tool use. Real operational work is different: responders must investigate incomplete evidence, avoid red herrings, choose safe mitigations, validate recovery, and explain the root cause clearly.

This environment turns those behaviors into a repeatable benchmark surface for both humans and AI systems.

## Demo Surface

The frontend exposes four dedicated views:

- `Tasks`: browse tiered scenarios and choose seeded incident variants
- `Session`: inspect live service state, read telemetry, and execute operator actions
- `Runtime`: run built-in baselines, inspect replays, and compare benchmark outputs
- `AI Control`: configure provider, model, API key, and base URL directly in the browser for AI-driven runs

## Core Capabilities

### Incident Model

- realistic service topology with dependency relationships
- hidden versions and dependencies that must be discovered
- change events, rollout clues, config drift, traces, and runbook hints
- deterministic scoring and solvability rules

### Action Surface

- `read_logs(service, lines)`
- `check_metrics(service, window_seconds)`
- `ping_service(service)`
- `inspect_deploy(service)`
- `query_traces(service)`
- `check_runbook(service)`
- `diff_config(service)`
- `drain_traffic(service)`
- `failover_region(service)`
- `restart_service(service)`
- `rollback_deploy(service, target_version)`
- `scale_up(service, replicas)`
- `check_dependencies(service)`
- `submit_diagnosis(root_cause_service, root_cause_category, fix_description)`

### Difficulty Tiers

- `easy`: single-root incidents with lower ambiguity
- `medium`: dependency cascades and more misleading symptoms
- `hard`: concurrent faults, red herrings, and stricter recovery validation

## Repository Structure

```text
.
├── api/        # FastAPI endpoints and runtime orchestration
├── env/        # simulator core, scenarios, services, baseline runner
├── frontend/   # browser UI
├── graders/    # deterministic grading helpers
├── scripts/    # regression and submission checks
├── server/     # app entrypoint
└── tests/      # API and environment tests
```

## Architecture

### Main Components

- `env/`
  The simulation engine, incident catalog, service-state modeling, scoring, seeded variants, and baseline execution logic.
- `api/`
  The FastAPI layer exposing environment reset/step/state plus replay, benchmark, and AI runtime endpoints.
- `frontend/`
  A browser-based command console for human sessions, telemetry inspection, replay viewing, and AI provider control.
- `tests/`
  Contract and behavior tests covering the environment and API layers.

### Runtime Model

The environment exposes a structured loop:

1. `reset`
2. observe current state
3. `step` with an action
4. receive updated observation and reward
5. validate recovery
6. submit diagnosis

## Supported Services

- `api-gateway`
- `auth-service`
- `user-service`
- `payment-service`
- `db-postgres`
- `cache-redis`

## Quickstart

### Requirements

- Python `3.12+`
- `pip`

### Local Setup

```bash
cd /home/ziyan01/VScode
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### Run the Application

```bash
cd /home/ziyan01/VScode
.venv/bin/python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

### Run the Baseline CLI

```bash
cd /home/ziyan01/VScode
.venv/bin/python baseline.py
```

## Frontend Usage

### Human Workflow

1. Open the `Tasks` tab and select a scenario
2. Switch to `Session`
3. Start a seeded session
4. Investigate logs, metrics, dependencies, traces, and deploy state
5. Apply remediation and validate recovery
6. Submit diagnosis and inspect results

### AI Workflow

1. Open `AI Control`
2. Choose a provider
3. Enter model and optional runtime credentials
4. Run:
   - AI baseline on the selected task
   - full benchmark across scenarios
   - AI vs human comparison for the active session

## Configuration

### Baseline Providers

The project supports:

- `scripted`
- `openai`
- `gemini`
- `openrouter`
- `groq`
- `cerebras`
- custom OpenAI-compatible providers

For the frontend, provider settings can be passed request-by-request from the `AI Control` page. For CLI usage, standard environment variables are supported.

### Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `BASELINE_PROVIDER` | No | Default provider override. |
| `BASELINE_MODEL` | No | Global model override for CLI-driven runs. |
| `OPENAI_API_KEY` | OpenAI only | OpenAI API key. |
| `OPENAI_BASELINE_MODEL` | OpenAI only | OpenAI model name. |
| `GEMINI_API_KEY` | Gemini only | Gemini API key. |
| `GEMINI_BASELINE_MODEL` | Gemini only | Gemini model name. |
| `GEMINI_BASE_URL` | No | Optional Gemini-compatible base URL override. |
| `OPENROUTER_API_KEY` | OpenRouter only | OpenRouter API key. |
| `OPENROUTER_BASELINE_MODEL` | OpenRouter only | OpenRouter model name. |
| `OPENROUTER_BASE_URL` | No | Optional OpenRouter base URL override. |
| `GROQ_API_KEY` | Groq only | Groq API key. |
| `GROQ_BASELINE_MODEL` | Groq only | Groq model name. |
| `GROQ_BASE_URL` | No | Optional Groq base URL override. |
| `CEREBRAS_API_KEY` | Cerebras only | Cerebras API key. |
| `CEREBRAS_BASELINE_MODEL` | Cerebras only | Cerebras model name. |
| `<CUSTOM>_API_KEY` | Custom provider | API key for custom provider. |
| `<CUSTOM>_BASELINE_MODEL` | Custom provider | Model name for custom provider. |
| `<CUSTOM>_BASE_URL` | No | Optional base URL for custom provider. |
| `SESSION_TTL_SECONDS` | No | Session expiration window for in-memory API state. |
| `MAX_ACTIVE_SESSIONS` | No | Maximum number of active in-memory sessions. |

## API Overview

### Core Environment Endpoints

- `POST /reset`
- `POST /step`
- `GET /state/{session_id}`
- `GET /tasks`
- `POST /grader`

### OpenEnv Aliases

- `POST /openenv/reset`
- `POST /openenv/step`
- `GET /openenv/state/{session_id}`
- `GET /openenv/tasks`
- `POST /openenv/grader`
- `GET /openenv/baseline`

### Benchmarking and Replay

- `GET /baseline`
- `GET /benchmark`
- `GET /benchmark/history`
- `GET /benchmark/history/{benchmark_id}`
- `GET /replay/{session_id}`
- `GET /sessions`
- `GET /compare/{session_id}`

### Frontend AI Runtime Endpoints

- `POST /runtime/baseline`
- `POST /runtime/benchmark`
- `POST /runtime/compare`

OpenEnv metadata is defined in [`openenv.yaml`](./openenv.yaml).

## Development

### Run Tests

```bash
cd /home/ziyan01/VScode
.venv/bin/python -m unittest discover -s tests -v
```

### Run Validation Scripts

```bash
cd /home/ziyan01/VScode
.venv/bin/python scripts/submission_check.py
.venv/bin/python scripts/benchmark_regression_check.py
```

### Package Metadata

The Python package metadata lives in [`pyproject.toml`](./pyproject.toml). The main script entrypoint is:

```bash
server = "server.app:main"
```

## Evaluation Semantics

The environment scores more than final diagnosis correctness. High-performing runs should:

- investigate before remediation
- identify the actual root service, not just the symptom surface
- use acceptable or correct mitigation/fix actions
- validate recovery explicitly
- submit a correct diagnosis with a meaningful fix description

This makes the benchmark useful for analyzing operational decision quality, not only end-state correctness.

## Security Notes

- Do not commit API keys or `.env` files
- Prefer browser request-scoped credentials or local environment variables
- Treat replay and benchmark artifacts as generated outputs
- This project is a simulator, not a production control plane

## Limitations

- Incident realism is intentionally bounded for determinism and repeatability
- Provider-driven baselines depend on external model quality and quota availability
- Scripted baselines are useful references, but should not be treated as optimal human playbooks
- The environment is designed for evaluation and training, not production automation

## Deployment Notes

For Hugging Face Spaces:

- the repository includes front matter metadata at the top of this README
- the application serves the browser UI from `/`
- the default application port is `8000`

For GitHub:

- this README is intended to function as both the project landing page and the developer quickstart
- screenshots, demo GIFs, or benchmark snapshots can be added later without restructuring the document

## License

MIT. See [`LICENSE`](./LICENSE).

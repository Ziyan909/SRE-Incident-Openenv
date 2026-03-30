---
title: SRE Incident Environment
emoji: ":wrench:"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
license: mit
tags:
  - openenv
---

# SRE Incident Environment

OpenEnv-compatible simulation environment for SRE incident response. This project is designed for training and evaluating agents on realistic, multi-step operational workflows: triage, investigation, mitigation, validation, and diagnosis.

## Overview

This environment models production-style service incidents with partial observability, dependency cascades, and deterministic grading.

Core characteristics:

- Real-world domain: on-call SRE operations
- Structured interface: `reset`, `step`, `state`
- Typed contracts: Pydantic `Observation`, `Action`, `Reward`
- Deterministic evaluation: score in `[0.0, 1.0]` with dense reward signals
- Benchmarking support: scripted and provider-driven baselines

## Key Capabilities

- Multi-tier difficulty: Easy, Medium, Hard
- Service dependency modeling and hidden evidence
- Rich operational actions (logs, metrics, traces, rollback, scale, failover)
- Replay persistence and benchmark history
- API-first architecture with browser UI

## System Architecture

High-level components:

- `env/`: simulator core, incidents, baseline runner, domain models
- `api/`: FastAPI endpoints for reset/step/state/grader/baseline/benchmark
- `graders/`: deterministic tier graders
- `frontend/`: browser UI
- `tests/`: API and environment behavior tests
- `scripts/`: submission and regression checks

## Domain Model

### Service Set

- `api-gateway`
- `auth-service`
- `user-service`
- `payment-service`
- `db-postgres`
- `cache-redis`

### Action Space

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

### Tiering

- Easy: single-root incidents
- Medium: cascades and higher ambiguity
- Hard: concurrent faults and red herrings

## Getting Started

### Prerequisites

- Python 3.12+
- `pip`

### Local Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### Run API Server

```bash
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```

Then open `http://127.0.0.1:8000`.

### Run Baseline CLI

```bash
.venv/bin/python baseline.py
```

## Configuration

When no provider key is configured, baseline CLI prompts for:

- OpenAI
- Gemini
- Add another provider (custom OpenAI-compatible)
- Later (scripted mode)

No default model is injected for OpenAI or Gemini. A model must be provided.

### Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `BASELINE_PROVIDER` | No | Provider override (`scripted`, `openai`, `gemini`, or custom provider name). |
| `BASELINE_MODEL` | No | Global model override for current run. |
| `OPENAI_API_KEY` | OpenAI only | API key for OpenAI baseline. |
| `OPENAI_BASELINE_MODEL` | OpenAI only | Model name for OpenAI baseline. |
| `GEMINI_API_KEY` | Gemini only | API key for Gemini baseline. |
| `GEMINI_BASELINE_MODEL` | Gemini only | Model name for Gemini baseline. |
| `GEMINI_BASE_URL` | No | Optional Gemini OpenAI-compatible base URL override. |
| `<CUSTOM>_API_KEY` | Custom provider | API key for custom provider. |
| `<CUSTOM>_BASELINE_MODEL` | Custom provider | Model name for custom provider. |
| `<CUSTOM>_BASE_URL` | No | Optional base URL for custom provider. |
| `SESSION_TTL_SECONDS` | No | Session expiration window for API state. |
| `MAX_ACTIVE_SESSIONS` | No | Upper bound for in-memory active sessions. |

## API Surface

Primary endpoints:

- `POST /reset`
- `POST /step`
- `GET /state/{session_id}`
- `GET /tasks`
- `POST /grader`
- `GET /baseline`
- `GET /benchmark`
- `GET /benchmark/history`
- `GET /benchmark/history/{benchmark_id}`
- `GET /replay/{session_id}`
- `GET /sessions`
- `GET /compare/{session_id}`

OpenEnv metadata is defined in `openenv.yaml`.

## Quality Gates

Run before release:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/submission_check.py
.venv/bin/python scripts/benchmark_regression_check.py
```

## Security Notes

- Do not commit API keys or `.env` files.
- Use environment variables for provider credentials.
- Generated artifacts and local scratch files are excluded via `.gitignore`.

## Limitations

- This is a simulation benchmark, not a production control plane.
- Baseline quality depends on provider/model behavior and API quotas.
- Scripted baseline can bias strategy if used as a training target.

## License

MIT (see `LICENSE`).

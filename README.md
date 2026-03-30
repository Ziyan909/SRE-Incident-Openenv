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

An OpenEnv-compatible benchmark where an agent plays on-call SRE, diagnoses realistic production incidents, and is graded on both correctness and operational quality.

## Why This Is Competitive

This project targets a real high-value workflow: production incident response.

Most benchmarks reward single-shot answers. This one rewards investigation quality under uncertainty:

- partial observability hides key facts until the right checks are run,
- incidents drift when root causes are not fixed,
- hard mode includes concurrent faults and misleading signals,
- recovery must be explicitly validated before a solution is accepted.

The result is closer to real ops decision-making than toy puzzle environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [API Contract](#api-contract)
- [Repository Layout](#repository-layout)
- [Validation and Quality Gates](#validation-and-quality-gates)
- [Docker](#docker)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)

## Judge TL;DR

- Domain: On-call SRE diagnosis and remediation.
- Interface: Browser UI plus JSON API.
- Quality controls: Deterministic graders, seeded variants, hidden holdouts, replay export.
- Evaluation depth: Dense rewards plus analytics (mitigation speed, evidence quality, blast-radius control, recovery certainty, action efficiency).
- Reproducibility: Stable scenario templates, explicit seeds, persisted run artifacts.

## Environment Design

### Services

- api-gateway
- auth-service
- user-service
- payment-service
- db-postgres
- cache-redis

Each service can be healthy, degraded, or down. Hidden dependencies create realistic cascades.

### Difficulty Tiers

- Easy: Single-service incidents with one clear root cause.
- Medium: Dependency cascades, rollout mistakes, deadlock-style failures.
- Hard: Primary root cause plus secondary concurrent fault and noisy red herrings.

### Scenario Families

- OOM crash loops
- bad deploy and config regressions
- dependency cascades
- cache and auth memory-pressure incidents
- database deadlocks
- gateway canary and edge-policy failures

### Action Space

- read_logs(service, lines)
- check_metrics(service, window_seconds)
- ping_service(service)
- inspect_deploy(service)
- query_traces(service)
- check_runbook(service)
- diff_config(service)
- drain_traffic(service)
- failover_region(service)
- restart_service(service)
- rollback_deploy(service, target_version)
- scale_up(service, replicas)
- check_dependencies(service)
- submit_diagnosis(root_cause_service, root_cause_category, fix_description)

## What Makes The Benchmark Hard

- Versions begin unknown until inspection.
- Dependency graphs are hidden until explicitly checked.
- Metrics are present but not fully trustworthy until targeted investigation.
- Trace/rollout signals provide clues but can mislead.
- Hard mode requires explicit recovery ping before final diagnosis counts.
- Unresolved incidents can degrade additional services over time.

## Current Baseline Snapshot

Scripted baseline results from this repository:

- Canonical /baseline tier runs: Easy 0.95, Medium 0.95, Hard 0.35
- Full benchmark (15 templates, seeds_per_scenario=2): overall average 0.84, overall solve rate 83%
- Tier averages in that benchmark run: Easy 0.91, Medium 0.93, Hard 0.68

Interpretation:

- Easy/Medium are strong and stable.
- Hard remains intentionally challenging and prevents trivial overfitting.

## Prerequisites

- Python 3.12+
- `pip`
- Optional: Docker 24+ for containerized runs

## Quickstart

### Local API server (2-3 minutes)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000

### Run baseline CLI

```bash
.venv/bin/python baseline.py
```

## API Contract

- POST /reset: start a session and return initial observation
- POST /step: apply one action
- GET /state/{session_id}: fetch current observation + result summary
- GET /tasks: list task catalog
- GET /sessions: list persisted replay sessions
- POST /grader: replay action sequence against fresh environment
- GET /baseline: run scripted or model-driven baseline
- GET /benchmark: run full public + holdout benchmark
- GET /benchmark/history: list persisted benchmark reports
- GET /benchmark/history/{benchmark_id}: read one report
- GET /replay/{session_id}: export full replay trace
- GET /compare/{session_id}: compare human session vs baselines

## Repository Layout

- env/: simulator, models, scenarios, benchmark runner
- graders/: deterministic tier graders
- api/: FastAPI app and endpoints
- frontend/: browser incident console
- tests/: API and environment regression tests
- scripts/: submission and benchmark regression checks
- artifacts/: persisted replay and benchmark outputs
- baseline.py: deterministic and provider-backed baseline client
- openenv.yaml: OpenEnv metadata for discovery/validation

## Validation and Quality Gates

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/submission_check.py
.venv/bin/python scripts/benchmark_regression_check.py
```

## Configuration

### Baseline provider setup

When you run the baseline CLI and no API key is configured, it will prompt you to choose OpenAI, Gemini, Add Another Provider, or Later.

- Choosing OpenAI or Gemini will ask for both API key and model name.
- Choosing Add Another Provider lets you register a custom provider name with API key and model name (plus optional base URL), then it appears in provider selection.
- Choosing Later will continue with the scripted baseline.
- No default model is applied for OpenAI or Gemini; you must set one.

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `BASELINE_PROVIDER` | No | Provider override (`scripted`, `openai`, `gemini`, or custom provider name). |
| `BASELINE_MODEL` | No | Global model override for current run. |
| `OPENAI_API_KEY` | OpenAI only | API key for OpenAI baseline provider. |
| `OPENAI_BASELINE_MODEL` | OpenAI only | Model name for OpenAI provider (required when using OpenAI). |
| `GEMINI_API_KEY` | Gemini only | API key for Gemini baseline provider. |
| `GEMINI_BASELINE_MODEL` | Gemini only | Model name for Gemini provider (required when using Gemini). |
| `GEMINI_BASE_URL` | No | Optional base URL override for Gemini OpenAI-compatible endpoint. |
| `<CUSTOM>_API_KEY` | Custom provider | API key for custom provider added via CLI. |
| `<CUSTOM>_BASELINE_MODEL` | Custom provider | Model name for custom provider. |
| `<CUSTOM>_BASE_URL` | No | Optional OpenAI-compatible base URL for custom provider. |

OpenAI:

```bash
export OPENAI_API_KEY=your_key_here
export OPENAI_USE_REAL_BASELINE=1
export OPENAI_BASELINE_MODEL=gpt-4o-mini
.venv/bin/python baseline.py
```

Gemini:

```bash
export GEMINI_API_KEY=your_key_here
export GEMINI_USE_REAL_BASELINE=1
export GEMINI_BASELINE_MODEL=gemini-2.0-flash
.venv/bin/python baseline.py
```

## Docker

```bash
docker build -t sre-incident-env .
docker run --rm -p 8000:8000 sre-incident-env
```

Quick smoke check:

```bash
curl http://127.0.0.1:8000/tasks
curl -X POST http://127.0.0.1:8000/reset -H 'content-type: application/json' -d '{"tier":"easy","seed":0}'
```

## Limitations

- Simulation benchmark, not production control plane.
- Scripted baselines can still bias agent strategy.
- Provider baseline quality depends on model output discipline and API quotas.

## Troubleshooting

- `bash: syntax error near unexpected token '('`
Cause: a numbered menu line like `2. openai (default)` was typed directly into shell.
Fix: run the CLI command first (`.venv/bin/python baseline.py`), then enter menu choices only when prompted by the program.

- CLI waits for input in CI/non-interactive runs
Fix: run with scripted baseline or set provider/model env vars ahead of time.

- Provider authentication/model errors
Fix: verify API key and model name; baseline returns these errors in JSON under `result.error` without crashing.

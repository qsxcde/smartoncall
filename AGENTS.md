# AGENTS.md

This file provides guidance to the AI agent when working with code in this repository.

## Project Overview

SmartOncall - an intelligent on-call agent built with LangGraph + FastAPI.

## Environment

- Python >= 3.12, managed by `uv`
- Root `.venv/` is the active virtual environment (created by `uv venv --python 3.12`)
- `apps/backend/.venv/` is a stale/secondary venv - do NOT use it
- Install/sync deps: `uv sync` (from project root)
- Env vars: copy `apps/backend/.env.example` to `.env`; requires `LLM_KEY`, `LLM_NAME`, `LLM_URL`, `LLM_TEMPERATURE`

## Commands

```bash
uv sync                          # install dependencies
uv run uvicorn smartoncall.main:app --reload --app-dir apps/backend/src  # dev server
```

## Architecture Decisions

- Package directory and import name are both `smartoncall` (all lowercase)
- `pyproject.toml` at root manages all deps; no separate requirements.txt
- Agent tools (`tools/`) are LLM-callable actions via `@tool`; `utils/` are internal helpers only
- Agent state flows through LangGraph `StateGraph`; nodes are pure functions `(state) -> state`

## Observability

- All logging uses `structlog` with JSON output; never use `print()` or stdlib `logging` directly
- Every request gets a `request_id` via `RequestContextMiddleware` (reads `X-Request-ID` header or generates UUID)
- Use `structlog.get_logger()` in all modules; bind contextual fields (user_id, email) per request
- Sensitive fields (password, verification codes, tokens) must NEVER appear in logs
- Auth events (register, login success/failure, token refresh, logout) must always be logged

## Gotchas

- Do NOT set `UV_PYTHON` env var - it previously pointed to a deleted miniconda install

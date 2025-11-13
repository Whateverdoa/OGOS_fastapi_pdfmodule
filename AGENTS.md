# Repository Guidelines

## Project Structure & Module Organization
- `main.py`: FastAPI app entrypoint and router wiring.
- `app/api/endpoints/`: HTTP routes (e.g., `pdf.py`).
- `app/core/`: core logic (`pdf_processor.py`, `pdf_analyzer.py`, `shape_generators.py`, `config.py`).
- `app/utils/`: pure helpers for PDF/spot-color/winding logic.
- `app/models/`: Pydantic schemas.
- `docs/`: specs (see `winding_routing_specification.md`).
- `examplecode/`: sample PDFs/JSON for manual testing.

## Build, Test, and Development Commands
- Local (UV): `uv sync` to install deps; `uv run uvicorn main:app --reload` to run at `http://localhost:8000`.
- Docker (dev): `make dev` (hot-reload at `http://localhost:8001`); `make build-dev` to rebuild.
- Docker (prod): `make prod` to start; `make build` to build.
- Common: `make up|down|logs|shell` for compose lifecycle.
- Manual API tests: use `test_main.http` or `curl` examples from `README.md`.

## Coding Style & Naming Conventions
- Python 3.10+; follow PEP 8; 4-space indentation; add type hints.
- Naming: snake_case for files/functions, PascalCase for classes, Pydantic models in `app/models/`.
- Keep route handlers thin; put business logic in `app/core/` and helpers in `app/utils/`.
- Configuration via `app/core/config.py` (pydantic-settings). Do not hardcode envs.
- No formatter configured in repo; keep lines reasonably short and imports grouped (stdlib, third-party, local).

## Testing Guidelines
- Preferred: pytest with tests under `tests/` named `test_*.py`.
- Until tests exist, exercise endpoints via `test_main.http` or `curl`.
- In Docker, `make test` runs `python -m pytest` inside the app container.
- Include tests for new logic (core/utils) and sample payloads for API changes.

## Commit & Pull Request Guidelines
- Commits: imperative, concise, scoped (e.g., "Add analyzer error handling").
- PRs: include summary, motivation, linked issue, how to test (commands/HTTP samples), and expected outputs. Attach small before/after PDFs when relevant.
- Update docs/README when changing endpoints, configs, or behavior.

## Security & Configuration Tips
- Copy `.env.example` to `.env`; keep secrets out of VCS.
- Respect `MAX_FILE_SIZE` and validate file types; never trust client data.
- Avoid committing large binaries; use `examplecode/` only for small samples.

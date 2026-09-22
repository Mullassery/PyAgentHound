# Contributing to PyAgentHound

Thank you for considering contributing! We welcome contributions of all kinds.

## Getting Started

### Prerequisites
- Python 3.10+
- pip or uv

### Development Setup

```bash
git clone https://github.com/Mullassery/PyAgentHound.git
cd PyAgentHound

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -e ".[dev]"
```

### Running checks

```bash
pytest tests/
ruff check pyagenthound/ tests/
mypy pyagenthound/
```

All three are enforced in CI (`.github/workflows/ci.yml`).

## Code Style

- PEP 8 via `ruff format`.
- Type hints throughout; `mypy` runs in CI.
- No comments explaining *what* code does — only *why*, when the reasoning isn't
  obvious from the code itself.

## Project structure

See [`docs/architecture.md`](docs/architecture.md) for the domain model, storage/API
contracts, and the design of components that don't exist yet. Please read
[`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) before proposing a feature from a later
phase — it explains what's intentionally not built yet and why, so PRs don't
duplicate in-progress design work.

## Pull Requests

1. Open an issue first for non-trivial changes, so design gets discussed before code.
2. Add tests for new behavior. No test should depend on a real external LLM API.
3. Update `ROADMAP_HONEST.md` if your change moves something from "not built" to
   "built" (or vice versa) — keeping that file accurate is a project norm, not
   optional cleanup.
4. Keep PRs scoped to one phase/feature at a time.

## Reporting Bugs

Open a GitHub issue with: what you expected, what happened, a minimal repro trace if
possible, and your Python version / OS.

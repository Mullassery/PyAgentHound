# Quickstart

```bash
pip install -e ".[dev]"     # until published to PyPI
pyagenthound init
python examples/minimal_trace.py
pyagenthound inspect <trace_id>   # trace_id is printed by the example
pyagenthound analyze <trace_id>   # findings + ranked root-cause hypotheses
```

That's the whole loop: instrument → capture → inspect → analyze, entirely local, no
server required.

## With the API server

```bash
pyagenthound serve   # http://localhost:8787, docs at /docs
```

Then point the SDK at it instead of writing straight to local SQLite:

```python
from pyagenthound import AgentHound

hound = AgentHound(endpoint="http://localhost:8787")
with hound.trace("my-request") as trace:
    with trace.span("llm") as span:
        span.set_attribute("model", "gpt-4o")
```

```bash
curl http://localhost:8787/api/traces
curl http://localhost:8787/api/traces/<trace_id>
curl http://localhost:8787/api/traces/<trace_id>/graph
curl -X POST http://localhost:8787/api/traces/<trace_id>/analyze
curl http://localhost:8787/api/traces/<trace_id>/root-cause
```

## What's not here yet

No web UI, no historical baselines (so root-cause confidence only uses 2 of its 4
documented components), no replay, no evaluation — see `../ROADMAP_HONEST.md` for
exactly what's built vs. planned.

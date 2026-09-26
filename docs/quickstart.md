# Quickstart

```bash
pip install -e ".[dev]"     # until published to PyPI
pyagenthound init
python examples/minimal_trace.py
pyagenthound inspect <trace_id>   # trace_id is printed by the example
pyagenthound analyze <trace_id>   # findings + ranked root-cause hypotheses
pyagenthound replay <trace_id> --set 'retrieval.documents=[]'   # try a fix, see if it clears
```

That's the whole loop: instrument → capture → inspect → analyze → replay, entirely
local, no server required.

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
curl "http://localhost:8787/api/traces?name=my-request"   # only traces of this workflow
curl http://localhost:8787/api/traces/<trace_id>
curl http://localhost:8787/api/traces/<trace_id>/graph
curl -X POST http://localhost:8787/api/traces/<trace_id>/analyze
curl http://localhost:8787/api/traces/<trace_id>/root-cause
curl -X POST http://localhost:8787/api/traces/<trace_id>/replay \
  -H 'Content-Type: application/json' \
  -d '{"overrides": {"<span_id>": {"documents": []}}}'
```

If a prior successful execution with the same `trace` name exists in the same
database, `analyze`/`root-cause` automatically diff against it (model/prompt/
retriever/tools/latency/tokens/execution path) and factor that into the root-cause
confidence — see `../docs/architecture.md` section 6. `replay` refuses (`409`) to
override a non-`READ_ONLY` span unless the request also sets `"allow_unsafe": true`
— see section 13.

## What's not here yet

No web UI, no evaluation — see `../ROADMAP_HONEST.md` for exactly what's built vs.
planned.

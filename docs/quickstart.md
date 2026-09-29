# Quickstart

```bash
pip install -e ".[dev]"     # until published to PyPI
pyagenthound init
python examples/minimal_trace.py
pyagenthound inspect <trace_id>   # trace_id is printed by the example
pyagenthound analyze <trace_id>   # findings + ranked root-cause hypotheses
pyagenthound replay <trace_id> --set 'retrieval.documents=[]'   # try a fix, see if it clears
pyagenthound analyze <trace_id> --explain   # optional: local-LLM narrative (needs Ollama)
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
curl -X POST http://localhost:8787/api/traces/<trace_id>/explain
```

If a prior successful execution with the same `trace` name exists in the same
database, `analyze`/`root-cause` automatically diff against it (model/prompt/
retriever/tools/latency/tokens/execution path) and factor that into the root-cause
confidence — see `../docs/architecture.md` section 6. `replay` refuses (`409`) to
override a non-`READ_ONLY` span unless the request also sets `"allow_unsafe": true`
— see section 13.

## Regression testing

Hand-author a JSON test case (see `../docs/architecture.md` section 14 for the full
assertion list) referencing a trace already in the database:

```json
{
  "name": "my_test",
  "trace_id": "<trace_id>",
  "assertions": [{"type": "STATUS_OK", "target": null}]
}
```

```bash
pyagenthound test ./tests   # runs every *.json in the directory, exits non-zero on FAIL
```

## Web UI

```bash
pyagenthound serve
```

Open `http://localhost:8787` — a requests list, and a request-detail page with an
interactive execution graph (click a node for its attributes), findings, root-cause
hypotheses, and a replay form (same `NAME.KEY=VALUE` syntax as `--set` above, plus
an "allow unsafe" checkbox). Server-rendered, no separate frontend build step — see
`../docs/architecture.md` section 15.

## Optional LLM explanation

Requires [Ollama](https://ollama.com) running locally with a model pulled (default
`qwen2.5:7b-instruct`):

```bash
ollama pull qwen2.5:7b-instruct
pyagenthound analyze <trace_id> --explain
```

The model only ever sees the structured findings/hypotheses already computed, never
the raw trace, and any citation it makes to a `finding_id` that doesn't actually
exist is rejected rather than shown — see `../docs/architecture.md` section 16. If
Ollama isn't running, `--explain` fails soft: the deterministic output above it
still prints normally.

## What's not here yet

No cloud LLM providers (OpenAI, Anthropic, etc.) — only local Ollama — see
`../ROADMAP_HONEST.md` for exactly what's built vs. planned.

"""Smallest possible PyAgentHound SDK usage.

Run with: python examples/minimal_trace.py
Then:     pyagenthound inspect <trace_id printed below>
"""

from pyagenthound import AgentHound, SpanType

hound = AgentHound()  # local-only: writes to ~/.pyagenthound/pyagenthound.db

with hound.trace("minimal-example") as trace:
    with trace.span("retrieval", span_type=SpanType.RETRIEVAL) as span:
        span.set_attribute("query", "cancellation policy")
        span.set_output(["policy-2024", "policy-2026"])

    with trace.span("llm", span_type=SpanType.LLM) as span:
        span.set_attribute("model", "gpt-4o-mini")
        span.set_input("What is the cancellation policy?")
        span.set_output("You can cancel within 30 days of purchase.")

print(f"trace_id: {trace.trace.trace_id}")
print("Inspect it with:")
print(f"  pyagenthound inspect {trace.trace.trace_id}")

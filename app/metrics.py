"""Prometheus metrics for the AI code review bot."""
from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry()

webhook_received_total = Counter(
    "webhook_received_total",
    "Total number of webhooks received",
    ["event_type", "action"],
    registry=REGISTRY,
)

review_posted_total = Counter(
    "review_posted_total",
    "Total number of reviews posted to GitHub",
    ["repo"],
    registry=REGISTRY,
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "Latency of LLM API calls in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY,
)

feedback_signal_total = Counter(
    "feedback_signal_total",
    "Total number of feedback signals received",
    ["signal"],
    registry=REGISTRY,
)

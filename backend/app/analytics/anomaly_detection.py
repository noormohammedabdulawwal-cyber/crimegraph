"""
Suspicious-pattern detection (PRD FR6 / section 10).

MVP implements burst-call clustering — flag phone pairs with an unusually
high number of calls in a short time window. Other detectors (circular
financial transfers, repeated co-location) are noted as follow-ups.
"""
from collections import defaultdict
from datetime import timedelta

from app.ingestion.cdr_loader import CallRecord

BURST_WINDOW = timedelta(hours=1)
BURST_CALL_THRESHOLD = 5  # calls between the same pair within BURST_WINDOW


def detect_burst_call_clusters(records: list[CallRecord]) -> list[dict]:
    """Return pairs of numbers with call bursts exceeding the threshold,
    each flagged with a confidence score and the underlying evidence
    (per PRD FR12 — every AI-inferred pattern must be traceable and
    carry a confidence level, not asserted as fact)."""
    by_pair: dict[tuple[str, str], list[CallRecord]] = defaultdict(list)
    for r in records:
        pair = tuple(sorted((r.caller_number, r.callee_number)))
        by_pair[pair].append(r)

    flags = []
    for pair, calls in by_pair.items():
        calls_sorted = sorted(calls, key=lambda c: c.timestamp)
        for i, call in enumerate(calls_sorted):
            window_calls = [
                c for c in calls_sorted[i:]
                if c.timestamp - call.timestamp <= BURST_WINDOW
            ]
            if len(window_calls) >= BURST_CALL_THRESHOLD:
                flags.append(
                    {
                        "pair": pair,
                        "call_count_in_window": len(window_calls),
                        "window_start": call.timestamp.isoformat(),
                        "confidence": min(0.5 + 0.05 * len(window_calls), 0.95),
                        "pattern_type": "burst_call_cluster",
                    }
                )
                break  # one flag per pair is enough for MVP
    return flags

"""End-to-end manual verification for the extraction layer (build step 2).

Runs NER + entity resolution over the sample FIR text and prints the entity
clusters so a human can eyeball precision/recall. This is the verification
gate before the extraction layer is wired into the API in step 5.

Usage:
    python backend/demo_extraction.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.extraction.entity_resolution import resolve_entities  # noqa: E402
from app.extraction.ner import EntityType, extract_entities  # noqa: E402
from app.ingestion.fir_loader import load_fir_text  # noqa: E402

FIR_PATH = BACKEND_DIR.parent / "data" / "sample_fir.txt"


def main() -> None:
    fir = load_fir_text("sample_fir", str(FIR_PATH))
    entities = extract_entities(fir.raw_text, fir.case_id)
    clusters = resolve_entities(entities)

    print(f"FIR: {fir.case_id} ({len(fir.raw_text)} chars)")
    print(f"raw entities: {len(entities)}  resolved clusters: {len(clusters)}")
    print("-" * 62)

    for type_name in (t.value for t in EntityType):
        rows = [
            (canonical, members)
            for canonical, members in clusters.items()
            if members[0].entity_type.value == type_name
        ]
        rows.sort(key=lambda r: len(r[1]), reverse=True)
        for canonical, members in rows:
            mentions = sorted({m.text for m in members})
            conf = members[0].confidence
            sources = sorted({m.source_case_id for m in members})
            print(f"[{type_name}] {canonical!r}")
            print(f"    mention count: {len(members)}   mentions: {mentions}")
            print(f"    confidence: {conf}   source_case_id: {sources}")

    print("-" * 62)
    print("Reliability spot-checks (must degrade, not throw):")
    print(f"  resolve_entities([])      -> {resolve_entities([])}")
    print(f"  resolve_entities(None)    -> {resolve_entities(None)}")
    singles = resolve_entities(entities[:1])
    print(f"  resolve_entities([1 one]) -> {len(singles)} cluster(s), keys={list(singles)}")
    assert resolve_entities([]) == {}
    assert resolve_entities(None) == {}
    assert len(singles) == 1
    print("OK — empty/None/single-entity all degrade gracefully.")


if __name__ == "__main__":
    main()
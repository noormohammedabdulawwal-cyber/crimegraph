"""
Loads FIR (First Information Report) text for the NLP extraction pipeline.

Build step 1 (see CLAUDE.md). MVP handles plain-text FIRs; OCR for scanned
FIRs is explicitly deferred (see PRD section 11 — Deferred beyond MVP).

Per PRD NFR (Reliability), a single unreadable or empty file is skipped and
logged rather than failing the whole ingest.
"""
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FIRDocument:
    case_id: str
    raw_text: str
    source_path: str = ""


def load_fir_text(case_id: str, path: str) -> FIRDocument:
    """Read a single plain-text FIR file."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return FIRDocument(case_id=case_id, raw_text=text, source_path=path)


def load_fir_directory(directory: str) -> list[FIRDocument]:
    """Load every .txt file in a directory as a FIRDocument, using the
    filename stem as the case_id.

    Hidden files are ignored; files that fail to read/decode or are empty
    are skipped and logged (the rest of the directory still loads).
    """
    docs: list[FIRDocument] = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".txt") or fname.startswith("."):
            continue
        path = os.path.join(directory, fname)
        case_id = os.path.splitext(fname)[0]
        try:
            doc = load_fir_text(case_id, path)
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("Skipping FIR file %s: %s", fname, exc)
            continue
        if not doc.raw_text.strip():
            logger.warning("Skipping empty FIR file %s", fname)
            continue
        docs.append(doc)
    return docs
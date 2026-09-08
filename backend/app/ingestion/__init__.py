"""Ingestion layer — normalizes raw CDR/FIR/financial records into a common
in-memory shape ready for the extraction layer."""
from app.ingestion.cdr_loader import (
    CallRecord,
    CdrLoadResult,
    load_cdr_csv,
)
from app.ingestion.fir_loader import (
    FIRDocument,
    load_fir_directory,
    load_fir_text,
)

__all__ = [
    "CallRecord",
    "CdrLoadResult",
    "load_cdr_csv",
    "FIRDocument",
    "load_fir_directory",
    "load_fir_text",
]
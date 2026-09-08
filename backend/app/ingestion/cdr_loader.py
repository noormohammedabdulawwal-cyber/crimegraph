"""
Loads Call Detail Records (CDRs) from CSV into a normalized in-memory shape
ready for the extraction layer.

Build step 1 (see CLAUDE.md). Expected input columns:
    caller_number, callee_number, timestamp, duration_seconds, cell_tower_location

Per PRD NFR (Reliability), malformed/partial rows are skipped and logged,
never allowed to crash the pipeline. Missing *required columns* is a schema
error and fails loudly instead — it is the file that is wrong, not a row.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

# Columns that must be present for a CDR CSV to be usable for extraction.
REQUIRED_COLUMNS = {
    "caller_number",
    "callee_number",
    "timestamp",
    "duration_seconds",
}

# Read phone-number columns as strings up front so leading zeros and ISD
# prefixes survive pandas' numeric inference (they would otherwise be read as
# ints/floats and drop their formatting).
DTYPE_OVERRIDES = {col: str for col in ("caller_number", "callee_number")}


@dataclass
class CallRecord:
    caller_number: str
    callee_number: str
    timestamp: datetime
    duration_seconds: int
    location: str | None = None


@dataclass
class CdrLoadResult:
    """Outcome of a CDR load: the valid records plus a report of what was
    skipped, so callers can surface ingestion health to the investigator
    (e.g. "2 of 11 rows were malformed and skipped")."""

    records: list[CallRecord] = field(default_factory=list)
    skipped_rows: int = 0
    errors: list[dict] = field(default_factory=list)  # {"row": csv_line_no, "reason": str}


def load_cdr_csv(path: str) -> CdrLoadResult:
    """Read a CDR CSV file, skipping malformed rows instead of crashing.

    Raises ValueError for an empty file or a file missing required columns.
    """
    result = CdrLoadResult()

    try:
        df = pd.read_csv(path, dtype=DTYPE_OVERRIDES)
    except pd.errors.EmptyDataError:
        raise ValueError(f"CDR file is empty: {path}") from None
    except pd.errors.ParserError as exc:
        # Ragged/misaligned rows (or a header whose column count mismatches the
        # data) raise ParserError — a subclass of Exception, NOT ValueError. The
        # file itself is wrong, so surface it as a schema ValueError -> HTTP 422,
        # never an unhandled 500.
        raise ValueError(f"CDR CSV is malformed: {exc}") from exc
    except UnicodeDecodeError as exc:
        # A non-UTF-8 upload (raw bytes written straight to the temp file) blows
        # up inside the C reader; same "bad file, not a connection problem" class.
        raise ValueError(f"CDR CSV is not valid UTF-8 text: {exc}") from exc

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"CDR CSV is missing required column(s): {sorted(missing)}. "
            f"Expected at least: {sorted(REQUIRED_COLUMNS)}. Got: {sorted(df.columns)}."
        )

    for row_idx, series in df.iterrows():
        try:
            result.records.append(_row_to_record(series))
        except (ValueError, TypeError, OverflowError) as exc:
            # +2: pandas rows are 0-indexed, plus the header line.
            # OverflowError is defensively included so any out-of-range numeric
            # parse (e.g. int(float("1e1000"))) skips its row too — one bad
            # cell must never abort the whole upload (PRD Reliability NFR).
            csv_line = row_idx + 2
            result.skipped_rows += 1
            result.errors.append({"row": csv_line, "reason": str(exc)})
            logger.warning("Skipping CDR row %d: %s", csv_line, exc)

    return result


def _row_to_record(series: pd.Series) -> CallRecord:
    caller = _clean_phone(series["caller_number"])
    callee = _clean_phone(series["callee_number"])
    if not caller or not callee:
        raise ValueError("missing caller or callee number")

    timestamp = pd.to_datetime(series["timestamp"], errors="coerce")
    if pd.isna(timestamp):
        raise ValueError(f"unparseable timestamp {series['timestamp']!r}")

    duration = _parse_duration(series["duration_seconds"])

    location = series.get("cell_tower_location")
    location = str(location).strip() if pd.notna(location) else None

    return CallRecord(
        caller_number=caller,
        callee_number=callee,
        timestamp=timestamp.to_pydatetime(),
        duration_seconds=duration,
        location=location,
    )


def _clean_phone(value) -> str:
    """Normalize a phone cell to a plain string. Returns "" for genuinely
    missing values (NaN, NA, empty) so the caller can skip the row — pandas
    stringifies missing cells as "nan", which must not be treated as a real
    number."""
    if value is None or pd.isna(value):
        return ""
    phone = str(value).strip()
    # Drop a ".0" float artifact if the string-dtype override was ignored.
    if phone.endswith(".0"):
        phone = phone[:-2]
    if phone.lower() in {"nan", "nat", "none", ""}:
        return ""
    return phone


def _parse_duration(value) -> int:
    try:
        duration = int(float(value))
    except (TypeError, ValueError, OverflowError):
        # float("inf") and float("1e1000") are valid floats but int() of an
        # infinite value raises OverflowError — non-finite/out-of-range, so the
        # row is malformed and must be skipped, not crash the upload.
        raise ValueError(f"non-numeric duration {value!r}") from None
    if duration < 0:
        raise ValueError(f"negative duration {duration!r}")
    return duration
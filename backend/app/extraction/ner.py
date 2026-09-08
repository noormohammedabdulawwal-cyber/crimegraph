"""
Named Entity Recognition over FIR/surveillance text.

Build step 2 (see CLAUDE.md). Extracts PERSON, LOCATION, ORG entities via
spaCy, plus PHONE and VEHICLE via regex (spaCy's default model doesn't have
good coverage for these domain-specific patterns).
"""
import re
from dataclasses import dataclass
from enum import Enum

import spacy

# Load once at module level. Swap "en_core_web_sm" for a transformer model
# (e.g. en_core_web_trf) once accuracy on real FIR-style text is validated.
_nlp = spacy.load("en_core_web_sm")

PHONE_PATTERN = re.compile(r"\b(?:\+?91[-\s]?)?[6-9]\d{9}\b")
# Indian vehicle registration pattern, e.g. GJ01AB1234
VEHICLE_PATTERN = re.compile(r"\b[A-Z]{2}\d{1,2}[A-Z]{1,2}\d{4}\b")

# ---- Post-processing: contextual PERSON reclassification ------------------
# en_core_web_sm confidently mis-tags single-token Indian names (e.g. "Vikram")
# as ORG (verified against data/sample_fir.txt — see docs). FIRs introduce
# people with role cues ("known as X", "the accused X"); when a single-token
# ORG sits right after such a cue, it is almost certainly a person's name.
# Multi-token ORGs ("Ahmedabad Traders Pvt Ltd.") are never reclassified.
# Confidence is lowered to reflect that this is a contextual inference, not a
# direct NER tag (CLAUDE.md: never present an AI-inferred link as ground truth).
PERSON_CONTEXT_RE = re.compile(
    r"\b(?:known as|named|called|accused|complainant|witness|suspect|associate)\b",
    re.IGNORECASE,
)
PERSON_CONTEXT_WINDOW = 40  # chars of leading text checked for a role cue


def _person_role_cue_before(text: str, start: int) -> bool:
    """True if a PERSON role cue appears in the leading text up to `start`.

    The window lookbehind is deliberately conservative — "Vikram" is preceded
    by "an associate known as" in the sample, well inside the 40-char window.
    """
    window_start = max(0, start - PERSON_CONTEXT_WINDOW)
    return PERSON_CONTEXT_RE.search(text, window_start, start) is not None


class EntityType(str, Enum):
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    PHONE = "PHONE"
    VEHICLE = "VEHICLE"


@dataclass
class ExtractedEntity:
    text: str
    entity_type: EntityType
    source_case_id: str
    confidence: float  # 0-1, surfaced to investigators per PRD FR12


def extract_entities(text: str, source_case_id: str) -> list[ExtractedEntity]:
    entities: list[ExtractedEntity] = []

    doc = _nlp(text)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            entities.append(
                ExtractedEntity(ent.text, EntityType.PERSON, source_case_id, 0.8)
            )
        elif ent.label_ in ("GPE", "LOC"):
            entities.append(
                ExtractedEntity(ent.text, EntityType.LOCATION, source_case_id, 0.75)
            )
        elif ent.label_ == "ORG":
            # Single-token ORG near a role cue -> very likely a person (e.g. "Vikram").
            # Two-token ORG (e.g. "Deepak Jain") near a role cue is also commonly a person
            # for Indian names that spaCy mis-scores as ORG. Known multi-token orgs
            # ("Ahmedabad Traders Pvt Ltd.") have 3+ tokens, so they stay ORG.
            token_count = len(ent.text.split())
            if token_count <= 2 and _person_role_cue_before(text, ent.start_char):
                entities.append(
                    ExtractedEntity(ent.text, EntityType.PERSON, source_case_id, 0.6)
                )
            else:
                entities.append(
                    ExtractedEntity(ent.text, EntityType.ORGANIZATION, source_case_id, 0.7)
                )

    for match in PHONE_PATTERN.finditer(text):
        entities.append(
            ExtractedEntity(match.group(), EntityType.PHONE, source_case_id, 0.95)
        )

    for match in VEHICLE_PATTERN.finditer(text):
        entities.append(
            ExtractedEntity(match.group(), EntityType.VEHICLE, source_case_id, 0.9)
        )

    return entities

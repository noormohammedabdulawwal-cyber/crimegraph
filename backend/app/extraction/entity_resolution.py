"""
Entity resolution / deduplication — merges entities that refer to the same
real-world person/location/etc. despite spelling variants or aliases.

Build step 2 (see CLAUDE.md). MVP uses fuzzy string matching within the same
entity type; a production version would add shared-attribute matching (phone,
address) per PRD section 10.

Reliability (same bar as the ingestion layer): empty / None / single-entity
input degrades to an empty or single-cluster result — never an exception.

Provenance is non-negotiable (CLAUDE.md): cluster members are the original
`ExtractedEntity` objects, so `source_case_id` and `confidence` ride through
resolution untouched. The canonical cluster name is the spelling of the first
mention; a future version may prefer the most frequent or source-verified
spelling.
"""
from rapidfuzz import fuzz

from app.extraction.ner import ExtractedEntity, EntityType

SIMILARITY_THRESHOLD = 85  # 0-100, rapidfuzz token_sort_ratio


def resolve_entities(entities: list[ExtractedEntity] | None) -> dict[str, list[ExtractedEntity]]:
    """Group entities into clusters representing the same canonical entity.

    Returns a dict mapping a canonical name -> list of raw ExtractedEntity
    mentions that were merged into it. Only merges within the same
    entity_type (a phone number must never collapse into a person).

    Deterministic: cluster key = first mention's text; later mentions are
    appended in input order.
    """
    if not entities:
        return {}

    clusters: dict[str, list[ExtractedEntity]] = {}

    for entity in entities:
        if entity is None or not entity.text:
            continue  # skip blank mentions rather than keying a cluster on ""

        # Same-text, different-type collision: a person name that spaCy's sm
        # model also tagged ORG (e.g. "known as Deepak Jain" -> PERSON mention
        # + a later ORG mention of the identical string). Fold the ORG mention
        # into the existing PERSON cluster instead of letting it clobber the
        # dict key and silently drop the person.
        exact_person = None
        for canonical_name, members in clusters.items():
            if (
                members[0].entity_type is EntityType.PERSON
                and entity.entity_type is EntityType.ORGANIZATION
                and canonical_name.lower() == entity.text.lower()
            ):
                exact_person = canonical_name
                break
        if exact_person is not None:
            entity.entity_type = EntityType.PERSON
            clusters[exact_person].append(entity)
            continue

        matched_key = None
        for canonical_name, members in clusters.items():
            if members[0].entity_type != entity.entity_type:
                continue
            score = fuzz.token_sort_ratio(canonical_name.lower(), entity.text.lower())
            if score >= SIMILARITY_THRESHOLD:
                matched_key = canonical_name
                break

        if matched_key:
            clusters[matched_key].append(entity)
        else:
            clusters[entity.text] = [entity]

    return clusters
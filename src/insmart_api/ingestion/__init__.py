"""Ingestion pipeline stages: parsing, entity resolution, dedup, persistence."""

from insmart_api.ingestion.dedup import (
    SEMANTIC_FIELDS,
    DuplicateDetector,
    DuplicateVerdict,
    content_fingerprint,
    differing_fields,
    row_content,
    stored_content_from_payload,
)
from insmart_api.ingestion.parsing import (
    COLUMNS,
    HeaderError,
    ParseFailure,
    RowOutcome,
    WorkOrderRow,
    column_index,
    compose_observation_text,
    parse_row,
    split_csv,
    validate_header,
)
from insmart_api.ingestion.resolution import (
    Ambiguous,
    AssetDescriptor,
    AssetIndex,
    Resolution,
    Resolved,
    Unresolvable,
    resolve_asset_tag,
)

__all__ = [
    "COLUMNS",
    "Ambiguous",
    "AssetDescriptor",
    "AssetIndex",
    "DuplicateDetector",
    "DuplicateVerdict",
    "SEMANTIC_FIELDS",
    "HeaderError",
    "ParseFailure",
    "Resolution",
    "Resolved",
    "RowOutcome",
    "Unresolvable",
    "WorkOrderRow",
    "column_index",
    "compose_observation_text",
    "content_fingerprint",
    "differing_fields",
    "parse_row",
    "resolve_asset_tag",
    "row_content",
    "split_csv",
    "stored_content_from_payload",
    "validate_header",
]

"""Shared validation for text that reaches PostgreSQL (NFR-22).

PostgreSQL cannot store U+0000 in a text column or compare against it, so a NUL in
a request field fails inside the query and became a 500. Rejecting it in the schema
turns that into a field-level 422.
"""

from pydantic import AfterValidator


def _reject_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


NoNul = AfterValidator(_reject_nul)

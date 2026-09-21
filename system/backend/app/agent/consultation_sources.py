"""Stable V1.1 source identifiers shared by import and consultation routing."""
from uuid import NAMESPACE_URL, uuid5

V11_DOCUMENT_IDS = {
    key: uuid5(NAMESPACE_URL, f"furniture-consultation-v1.1/{key}")
    for key in ("collection", "admission")
}

__all__ = ["V11_DOCUMENT_IDS"]

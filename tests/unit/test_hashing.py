from __future__ import annotations

from alpha_research.common.hashing import hash_mapping


def test_hash_mapping_is_order_independent() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}
    assert hash_mapping(left) == hash_mapping(right)

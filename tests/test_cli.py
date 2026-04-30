"""Fast CLI helper tests."""

from __future__ import annotations

from embedumap.cli import normalize_trails_args


def test_normalize_trails_args_defaults_to_cluster_without_value() -> None:
    assert normalize_trails_args(["sample.csv", "--trails", "--dry-run"]) == [
        "sample.csv",
        "--trails",
        "cluster",
        "--dry-run",
    ]
    assert normalize_trails_args(["sample.csv", "--trails"]) == ["sample.csv", "--trails", "cluster"]


def test_normalize_trails_args_preserves_explicit_values() -> None:
    assert normalize_trails_args(["sample.csv", "--trails", "theme,cluster"]) == [
        "sample.csv",
        "--trails",
        "theme,cluster",
    ]
    assert normalize_trails_args(["sample.csv", "--trails=theme"]) == ["sample.csv", "--trails=theme"]

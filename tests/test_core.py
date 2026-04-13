"""Fast unit tests for embedumap core helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from embedumap.core import (
    BuildConfig,
    CsvSource,
    _bucket_label,
    _time_bucket,
    build_payload,
    compute_centroid_trails,
    default_cache_path,
    direct_cluster_labels,
    parse_centroid_time_period,
    split_option_values,
)
from embedumap.html import render_html


def test_split_option_values_flattens_and_deduplicates() -> None:
    values = split_option_values(["text1,text2", "text2", " text3 ", ""])
    assert values == ["text1", "text2", "text3"]


def test_direct_cluster_labels_use_raw_column_values() -> None:
    class Record:
        def __init__(self, value: str) -> None:
            self.raw = {"theme": value}

    labels, label_map = direct_cluster_labels([Record("a"), Record("b"), Record("a")], ["theme"])
    assert labels.tolist() == [0, 1, 0]
    assert label_map == {0: "a", 1: "b"}


def test_build_payload_includes_popup_sort_columns() -> None:
    source = CsvSource(
        label="sample.csv",
        frame=pd.DataFrame([{"title": "Hello", "year": "2024"}], columns=["title", "year"]),
        csv_path=None,
        csv_url=None,
    )
    config = BuildConfig(
        csv_input="sample.csv",
        output_path=Path("index.html"),
        embedding_columns=["title"],
        image_columns=[],
        audio_columns=[],
        audio_metadata_columns=[],
        color_columns=["year"],
        filter_columns=[],
        cluster_columns=["embeddings"],
        label_columns=[],
        timeline_column="year",
        branding="embedumap",
        opacity=1.0,
        bar_chart_corner="top-right",
        axis_labels=True,
        popup_style="table",
        model="model",
        cluster_naming_model="gemini-3-flash-preview",
        cluster_names=False,
        dimensions=768,
        sample=None,
        dry_run=False,
        centroid_trails=[],
        centroid_time_period=None,
    )

    class Record:
        row_index = 0
        raw = {"title": "Hello", "year": "2024"}
        tooltip = raw
        label = "Hello"
        audio_metadata_text = ""
        timeline_text = "2024-01-01 00:00:00 UTC"
        timeline_ms = 1704067200000
        images = []
        audios = []

    payload = build_payload(
        source,
        config,
        [Record()],
        np.array([[0.0, 0.0]]),
        np.array([0]),
        {0: "Cluster 1"},
        axis_labels={"x": "People -> products", "y": "Narrative -> technical"},
        timeline_kind_value="year",
    )
    assert payload["defaultSort"] == "year"
    assert payload["sortColumns"] == ["_row_index", "year", "title"]
    assert payload["audioColumns"] == []
    assert payload["branding"] == "embedumap"
    assert payload["opacity"] == 1.0
    assert payload["barChartCorner"] == "top-right"
    assert payload["axisLabels"] == {"x": "People -> products", "y": "Narrative -> technical"}
    assert payload["timelineKind"] == "year"


def test_render_html_embeds_json_safely_for_windows_paths_and_newlines() -> None:
    payload = {
        "title": "Map",
        "source": r"C:\Users\admin\work\embedumap\sample.csv",
        "rows": [
            {
                "label": "Line 1\nLine 2",
                "raw": {"path": r"C:\Users\admin\work\embedumap\data.txt"},
            }
        ],
    }

    html = render_html(payload)
    assert 'id="trails-group"' in html
    assert 'Trails Only' in html
    assert 'Nodes Only' in html
    assert 'id="page-switch-group"' in html
    assert 'id="timeline-mode-group"' in html
    assert 'id="timeline-speed"' in html
    match = re.search(r'<script id="data-json" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    assert json.loads(match.group(1)) == payload


def test_default_cache_path_tracks_output_directory() -> None:
    output_path = Path("/tmp/embedumap/output/index.html")
    assert default_cache_path(output_path) == Path("/tmp/embedumap/output/embedumap.duckdb")


def test_time_bucket_supports_year_month_and_day_granularity() -> None:
    ms = 1706834700000  # 2024-02-02 UTC
    assert _time_bucket(ms, "year") == 2024
    assert _time_bucket(ms, "datetime") == (2024, 2)
    assert _time_bucket(ms, "date") == (2024, 2, 2)
    assert _bucket_label((2024, 2), "datetime") == "2024-02"
    assert _bucket_label((2024, 2, 2), "date") == "2024-02-02"


def test_parse_centroid_time_period_supports_aliases_fixed_and_calendar_values() -> None:
    assert parse_centroid_time_period("hourly").duration_ms == 3_600_000
    assert parse_centroid_time_period("2h 15min").duration_ms == 8_100_000
    assert parse_centroid_time_period("fortnightly").frequency == "2W-SUN"
    assert parse_centroid_time_period("2Q").frequency == "2Q-DEC"


def test_compute_centroid_trails_includes_requested_groups_and_two_point_buckets() -> None:
    def ms(value: str) -> int:
        return int(pd.Timestamp(value).value // 1_000_000)

    rows = [
        {"timelineMs": ms("2024-01-01T00:10:00Z"), "clusterId": 0, "x": 0.0, "y": 0.0, "filters": {"category": "A"}},
        {"timelineMs": ms("2024-01-01T00:40:00Z"), "clusterId": 0, "x": 2.0, "y": 0.0, "filters": {"category": "A"}},
        {"timelineMs": ms("2024-01-01T01:05:00Z"), "clusterId": 0, "x": 2.0, "y": 2.0, "filters": {"category": "A"}},
        {"timelineMs": ms("2024-01-01T01:35:00Z"), "clusterId": 0, "x": 4.0, "y": 2.0, "filters": {"category": "A"}},
        {"timelineMs": ms("2024-01-01T02:00:00Z"), "clusterId": 0, "x": 8.0, "y": 8.0, "filters": {"category": "A"}},
    ]

    trails = compute_centroid_trails(rows, {0: "Cluster 1"}, "datetime", ["category", "cluster"], "1h")

    assert sorted(trails) == ["category", "cluster"]
    assert trails["cluster"][0]["groupLabel"] == "Cluster 1"
    assert trails["category"][0]["groupLabel"] == "A"
    assert len(trails["cluster"][0]["points"]) == 2
    assert trails["cluster"][0]["points"][0] == {
        "time": ms("2024-01-01T00:00:00Z"),
        "timeLabel": "2024-01-01 00:00 UTC to 2024-01-01 00:59 UTC",
        "timeStartMs": ms("2024-01-01T00:00:00Z"),
        "timeEndMs": ms("2024-01-01T00:59:59.999Z"),
        "x": 1.0,
        "y": 0.0,
        "count": 2,
        "std": 1.0,
    }

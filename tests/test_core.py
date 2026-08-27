"""Fast unit tests for embedumap core helpers."""

from __future__ import annotations

import io
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from PIL import Image

from embedumap.core import (
    BuildConfig,
    CsvSource,
    MediaInput,
    _bucket_label,
    _time_bucket,
    batch_slices,
    build_payload,
    compute_trails,
    default_cache_path,
    direct_cluster_labels,
    embed_records,
    normalized_image_bytes,
    parse_trail_period,
    record_cache_key,
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


def base_config(**overrides: object) -> BuildConfig:
    values = {
        "csv_input": "sample.csv",
        "output_path": Path("index.html"),
        "embedding_columns": ["title"],
        "image_columns": [],
        "audio_columns": [],
        "audio_metadata_columns": [],
        "color_columns": [],
        "filter_columns": [],
        "cluster_columns": ["embeddings"],
        "label_columns": [],
        "timeline_column": None,
        "branding": "embedumap",
        "opacity": 1.0,
        "inactive_opacity": 0.08,
        "trail_opacity": 0.28,
        "bar_chart_corner": "top-right",
        "axis_labels": True,
        "popup_style": "table",
        "model": "model",
        "cluster_naming_model": "gemini-3-flash-preview",
        "cluster_names": False,
        "dimensions": 768,
        "batch_size": 8,
        "max_image_size": None,
        "sample": None,
        "dry_run": False,
        "trail_columns": [],
        "trail_period": None,
    }
    values.update(overrides)
    return BuildConfig(**values)


def test_build_payload_includes_popup_sort_columns() -> None:
    source = CsvSource(
        label="sample.csv",
        frame=pd.DataFrame([{"title": "Hello", "year": "2024"}], columns=["title", "year"]),
        csv_path=None,
        csv_url=None,
    )
    config = base_config(
        color_columns=["year"],
        timeline_column="year",
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
    assert payload["inactiveOpacity"] == 0.08
    assert payload["trailOpacity"] == 0.28
    assert payload["barChartCorner"] == "top-right"
    assert payload["axisLabels"] == {"x": "People -> products", "y": "Narrative -> technical"}
    assert payload["timelineKind"] == "year"
    assert payload["trailColumns"] == []
    assert payload["centroidTrails"] is None


def test_default_cache_path_tracks_output_directory() -> None:
    output_path = Path("/tmp/embedumap/output/index.html")
    assert default_cache_path(output_path) == Path("/tmp/embedumap/output/embedumap.duckdb")


def test_batch_slices_uses_custom_size() -> None:
    assert list(batch_slices([0, 1, 2, 3, 4], 2)) == [[0, 1], [2, 3], [4]]


def test_parse_trail_period_supports_aliases_fixed_and_calendar_values() -> None:
    assert parse_trail_period("hourly").duration_ms == 3_600_000
    assert parse_trail_period("2h 15min").duration_ms == 8_100_000
    assert parse_trail_period("fortnightly").frequency == "2W-SUN"
    assert parse_trail_period("2Q").frequency == "2Q-DEC"


def test_time_bucket_supports_expected_granularity() -> None:
    ms = int(pd.Timestamp("2024-02-02T03:04:05Z").value // 1_000_000)

    assert _time_bucket(ms, "year") == 2024
    assert _time_bucket(ms, "month") == (2024, 2)
    assert _time_bucket(ms, "date") == (2024, 2, 2)
    assert _time_bucket(ms, "hour") == (2024, 2, 2, 3)
    assert _time_bucket(ms, "minute") == (2024, 2, 2, 3, 4)
    assert _bucket_label((2024, 2, 2, 3), "hour") == "2024-02-02 03:00 UTC"


def test_compute_trails_includes_cluster_by_default_and_requested_groups() -> None:
    def ms(value: str) -> int:
        return int(pd.Timestamp(value).value // 1_000_000)

    rows = [
        {"timelineMs": ms("2024-01-01T00:10:00Z"), "clusterId": 0, "x": 0.0, "y": 0.0, "filters": {"theme": "A"}},
        {"timelineMs": ms("2024-01-01T00:40:00Z"), "clusterId": 0, "x": 2.0, "y": 0.0, "filters": {"theme": "A"}},
        {"timelineMs": ms("2024-01-01T01:05:00Z"), "clusterId": 0, "x": 2.0, "y": 2.0, "filters": {"theme": "A"}},
        {"timelineMs": ms("2024-01-01T01:35:00Z"), "clusterId": 0, "x": 4.0, "y": 2.0, "filters": {"theme": "A"}},
        {"timelineMs": ms("2024-01-01T02:00:00Z"), "clusterId": 0, "x": 8.0, "y": 8.0, "filters": {"theme": "A"}},
    ]

    trails = compute_trails(rows, {0: "Cluster 1"}, "datetime", ["theme"], None)

    assert sorted(trails) == ["cluster", "theme"]
    assert trails["cluster"][0]["groupLabel"] == "Cluster 1"
    assert trails["theme"][0]["groupLabel"] == "A"
    assert len(trails["cluster"][0]["points"]) == 3
    assert trails["cluster"][0]["points"][0] == {
        "time": (2024, 1, 1, 0),
        "timeLabel": "2024-01-01 00:00 UTC",
        "timeStartMs": ms("2024-01-01T00:00:00Z"),
        "timeEndMs": ms("2024-01-01T00:59:59.999Z"),
        "x": 1.0,
        "y": 0.0,
        "count": 2,
        "std": 1.0,
    }


def test_compute_trails_keeps_singleton_buckets_for_sparse_groups() -> None:
    def ms(value: str) -> int:
        return int(pd.Timestamp(value).value // 1_000_000)

    rows = [
        {"timelineMs": ms("2024-01-01T00:00:00Z"), "clusterId": 0, "x": 0.0, "y": 0.0, "filters": {}},
        {"timelineMs": ms("2024-01-01T01:00:00Z"), "clusterId": 0, "x": 2.0, "y": 0.0, "filters": {}},
    ]

    trails = compute_trails(rows, {0: "Cluster 1"}, "datetime", ["cluster"], "1h")

    assert trails["cluster"][0]["points"][0]["count"] == 1
    assert trails["cluster"][0]["points"][0]["std"] == 0.0
    assert len(trails["cluster"][0]["points"]) == 2


def test_build_payload_adds_trail_columns_and_centroid_trails() -> None:
    source = CsvSource(
        label="sample.csv",
        frame=pd.DataFrame(
            [
                {"title": "A", "theme": "Alpha", "when": "2024-01-01T00:10:00Z"},
                {"title": "B", "theme": "Alpha", "when": "2024-01-01T00:40:00Z"},
                {"title": "C", "theme": "Alpha", "when": "2024-01-01T01:10:00Z"},
                {"title": "D", "theme": "Beta", "when": "2024-01-01T01:00:00Z"},
            ],
            columns=["title", "theme", "when"],
        ),
        csv_path=None,
        csv_url=None,
    )
    config = base_config(
        color_columns=["theme"],
        filter_columns=["theme"],
        timeline_column="when",
        trail_columns=["theme"],
        trail_period="1h",
    )

    class Record:
        def __init__(self, index: int, title: str, theme: str, timeline_ms: int) -> None:
            self.row_index = index
            self.raw = {"title": title, "theme": theme, "when": str(timeline_ms)}
            self.tooltip = self.raw
            self.label = title
            self.audio_metadata_text = ""
            self.timeline_text = "2024-01-01"
            self.timeline_ms = timeline_ms
            self.images = []
            self.audios = []

    def ms(value: str) -> int:
        return int(pd.Timestamp(value).value // 1_000_000)

    payload = build_payload(
        source,
        config,
        [
            Record(0, "A", "Alpha", ms("2024-01-01T00:10:00Z")),
            Record(1, "B", "Alpha", ms("2024-01-01T00:40:00Z")),
            Record(2, "C", "Alpha", ms("2024-01-01T01:10:00Z")),
            Record(3, "D", "Beta", ms("2024-01-01T01:00:00Z")),
        ],
        np.array([[0.0, 0.0], [2.0, 0.0], [3.0, 3.0], [10.0, 10.0]]),
        np.array([0, 0, 0, 1]),
        {0: "Cluster 1", 1: "Cluster 2"},
        timeline_kind_value="datetime",
    )

    assert payload["trailColumns"] == ["theme", "cluster"]
    assert payload["colorColumns"] == ["theme", "cluster"]
    assert sorted(payload["centroidTrails"]) == ["cluster", "theme"]


def test_render_html_includes_trail_and_playback_controls() -> None:
    html = render_html(
        {
            "title": "Map",
            "source": "sample.csv",
            "rows": [],
            "trailColumns": ["theme", "cluster"],
            "centroidTrails": {"cluster": []},
        }
    )

    assert 'id="trails-group"' in html
    assert 'id="trails-toggle"' in html
    assert 'id="control-search" type="search"' in html
    assert 'data-trail-mode' not in html
    assert "Lines + Nodes" not in html
    assert 'id="timeline-cumulative"' in html
    assert 'id="timeline-mode-group"' not in html
    assert 'data-playback-mode="slide"' not in html
    assert 'data-playback-mode="reveal"' not in html
    assert 'id="timeline-speed"' in html
    assert 'id="timeline-inactive-opacity" type="range" min="0" max="100" step="1"' in html
    assert "const opacitySliderMax = 100;" in html
    assert "toPrecision(2)" in html
    assert 'type="range"' in html
    assert "top: -10px;" in html
    assert "trailsVisible: false" in html
    assert 'loading="lazy"' in html
    assert 'data-play-speed' not in html


def test_normalized_image_bytes_resizes_into_square_tile_without_distortion() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (1600, 800), "blue").save(buffer, format="PNG")

    data, mime_type = normalized_image_bytes(buffer.getvalue(), "image/png", max_image_size=768)

    assert mime_type == "image/png"
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (768, 384)


def test_normalized_image_bytes_does_not_upscale_small_images() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 180), "blue").save(buffer, format="PNG")

    data, _ = normalized_image_bytes(buffer.getvalue(), "image/png", max_image_size=768)

    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (320, 180)


def test_record_cache_key_includes_max_image_size() -> None:
    source = CsvSource(
        label="sample.csv",
        frame=pd.DataFrame([{"image": "photo.png"}]),
        csv_path=None,
        csv_url=None,
    )

    class Record:
        row_index = 0
        text_payload = ""
        audio_metadata_text = ""
        images = [
            MediaInput(
                kind="image",
                column="image",
                raw_value="photo.png",
                display_url="file:///tmp/photo.png",
                local_path=None,
                remote_url="https://example.com/photo.png",
                exists=True,
            )
        ]
        audios = []

    original_key, original_hash = record_cache_key(source, Record(), "model", 768, None)
    resized_key, resized_hash = record_cache_key(source, Record(), "model", 768, 768)

    assert original_hash == resized_hash
    assert original_key != resized_key


def test_record_cache_key_ignores_max_image_size_without_images() -> None:
    source = CsvSource(
        label="sample.csv",
        frame=pd.DataFrame([{"text": "hello"}]),
        csv_path=None,
        csv_url=None,
    )

    class Record:
        row_index = 0
        text_payload = "hello"
        audio_metadata_text = ""
        images = []
        audios = []

    original_key, original_hash = record_cache_key(source, Record(), "model", 768, None)
    resized_key, resized_hash = record_cache_key(source, Record(), "model", 768, 768)

    assert original_hash == resized_hash
    assert original_key == resized_key

def test_embed_records_reuses_cache_across_source_paths(monkeypatch, tmp_path: Path) -> None:
    frames = pd.DataFrame([{"title": "same text"}])

    class Record:
        def __init__(self, row_index: int) -> None:
            self.row_index = row_index
            self.text_payload = "same text"
            self.audio_metadata_text = ""
            self.images = []
            self.audios = []

    config = base_config(output_path=tmp_path / "index.html", dimensions=4, batch_size=1)
    calls = 0

    def fake_embed_batch_once(*args: object, **kwargs: object) -> np.ndarray:
        nonlocal calls
        calls += 1
        return np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr("embedumap.core.gemini_client", lambda: object())
    monkeypatch.setattr("embedumap.core.embed_batch_once", fake_embed_batch_once)

    first = CsvSource(label="/old/path/sample.csv", frame=frames, csv_path=None, csv_url=None)
    second = CsvSource(label="/new/path/sample.csv", frame=frames, csv_path=None, csv_url=None)
    first_vectors = embed_records(first, [Record(0)], config)
    second_vectors = embed_records(second, [Record(99)], config)

    assert calls == 1
    np.testing.assert_array_equal(second_vectors, first_vectors)


def test_embed_records_does_not_portably_reuse_image_cache(monkeypatch, tmp_path: Path) -> None:
    frames = pd.DataFrame([{"image": "photo.png"}])

    class Record:
        row_index = 0
        text_payload = ""
        audio_metadata_text = ""
        images = [object()]
        audios = []

    config = base_config(output_path=tmp_path / "index.html", dimensions=4, batch_size=1)
    calls = 0

    def fake_record_cache_key(
        source: CsvSource,
        record: object,
        model: str,
        dimensions: int,
        max_image_size: int | None,
    ) -> tuple[str, str]:
        return (f"key:{source.label}", "same-content")

    def fake_embed_batch_once(*args: object, **kwargs: object) -> np.ndarray:
        nonlocal calls
        calls += 1
        return np.array([[float(calls), 0.0, 0.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr("embedumap.core.record_cache_key", fake_record_cache_key)
    monkeypatch.setattr("embedumap.core.build_content", lambda *args: object())
    monkeypatch.setattr("embedumap.core.gemini_client", lambda: object())
    monkeypatch.setattr("embedumap.core.embed_batch_once", fake_embed_batch_once)

    first = CsvSource(label="/old/path/sample.csv", frame=frames, csv_path=None, csv_url=None)
    second = CsvSource(label="/new/path/sample.csv", frame=frames, csv_path=None, csv_url=None)
    embed_records(first, [Record()], config)
    embed_records(second, [Record()], config)

    assert calls == 2


def test_embed_records_checkpoints_successful_batches(monkeypatch, tmp_path: Path) -> None:
    source = CsvSource(
        label="sample.csv",
        frame=pd.DataFrame([{"title": f"row {index}"} for index in range(4)]),
        csv_path=None,
        csv_url=None,
    )

    class Record:
        def __init__(self, index: int) -> None:
            self.row_index = index
            self.text_payload = f"row {index}"
            self.audio_metadata_text = ""
            self.images = []
            self.audios = []

    records = [Record(index) for index in range(4)]
    config = base_config(
        output_path=tmp_path / "index.html",
        dimensions=4,
        batch_size=2,
    )
    calls = 0

    def fake_embed_batch_once(*args: object, **kwargs: object) -> np.ndarray:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("forced second-batch failure")
        return np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
            dtype=np.float32,
        )

    monkeypatch.setattr("embedumap.core.gemini_client", lambda: object())
    monkeypatch.setattr("embedumap.core.embed_batch_once", fake_embed_batch_once)

    try:
        embed_records(source, records, config)
    except RuntimeError as exc:
        assert str(exc) == "forced second-batch failure"
    else:
        raise AssertionError("expected the forced second-batch failure")

    cache_path = default_cache_path(config.output_path)
    with duckdb.connect(str(cache_path), read_only=True) as connection:
        cached_rows = connection.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
    assert cached_rows == 2


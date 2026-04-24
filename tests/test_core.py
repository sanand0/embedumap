"""Fast unit tests for embedumap core helpers."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from embedumap.core import (
    BuildConfig,
    CsvSource,
    MediaInput,
    build_payload,
    default_cache_path,
    direct_cluster_labels,
    normalized_image_bytes,
    record_cache_key,
    split_option_values,
)


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
        max_image_size=None,
        sample=None,
        dry_run=False,
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


def test_default_cache_path_tracks_output_directory() -> None:
    output_path = Path("/tmp/embedumap/output/index.html")
    assert default_cache_path(output_path) == Path("/tmp/embedumap/output/embedumap.duckdb")


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

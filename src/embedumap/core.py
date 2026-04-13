"""Core pipeline for embedumap."""

from __future__ import annotations

import io
import json
import math
import mimetypes
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlparse

import duckdb
import httpx
import numpy as np
import pandas as pd
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image
from rich.console import Console
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import OneHotEncoder
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

console = Console()
DEFAULT_MODEL = "gemini-embedding-2-preview"
DEFAULT_CLUSTER_NAMING_MODEL = "gemini-3-flash-preview"
DEFAULT_DIMENSIONS = 768
DEFAULT_BATCH_SIZE = 8
DEFAULT_CACHE_NAME = "embedumap.duckdb"
MAX_LABEL_CHARS = 140
MAX_TOOLTIP_CHARS = 140
UMAP_NEIGHBORS = 20
UMAP_MIN_DIST = 0.15
EMBEDDING_CACHE_VERSION = "embedumap-embedding-v1"
CLUSTER_NAMING_VERSION = "embedumap-cluster-name-v1"
AXIS_LABEL_VERSION = "embedumap-axis-label-v1"
CLUSTER_NAMING_TOP_N = 6
CLUSTER_NAMING_NEIGHBORS = 2
CLUSTER_NAMING_CONTRAST_ROWS = 3
AXIS_LABEL_TOP_N = 6


@dataclass(slots=True)
class CsvSource:
    """Resolved CSV source and media bases."""

    label: str
    frame: pd.DataFrame
    csv_path: Path | None
    csv_url: str | None


@dataclass(slots=True)
class BuildConfig:
    """Normalized CLI configuration."""

    csv_input: str
    output_path: Path
    embedding_columns: list[str]
    image_columns: list[str]
    audio_columns: list[str]
    audio_metadata_columns: list[str]
    color_columns: list[str]
    filter_columns: list[str]
    cluster_columns: list[str]
    label_columns: list[str]
    timeline_column: str | None
    branding: str
    opacity: float
    bar_chart_corner: str
    axis_labels: bool
    popup_style: str
    model: str
    cluster_naming_model: str
    cluster_names: bool
    dimensions: int
    sample: int | None
    dry_run: bool
    centroid_trails: list[str]
    centroid_time_period: str | None


@dataclass(slots=True)
class MediaInput:
    """One resolved media reference for embedding and popup display."""

    kind: Literal["image", "audio"]
    column: str
    raw_value: str
    display_url: str
    local_path: Path | None
    remote_url: str | None
    exists: bool


@dataclass(slots=True)
class RowRecord:
    """Prepared row used for embedding, analysis, and rendering."""

    row_index: int
    raw: dict[str, str]
    tooltip: dict[str, str]
    label: str
    text_payload: str
    audio_metadata_text: str
    images: list[MediaInput]
    audios: list[MediaInput]
    timeline_text: str | None
    timeline_ms: int | None


def split_option_values(values: list[str]) -> list[str]:
    """Split repeated comma-delimited option values while preserving order."""

    flattened: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in str(value).split(","):
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            flattened.append(cleaned)
            seen.add(cleaned)
    return flattened


def truncate(value: str, limit: int) -> str:
    """Clamp a display value without mutating the raw row."""

    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}…"


def is_http_url(value: str) -> bool:
    """Return True when the value is an HTTP(S) URL."""

    return urlparse(value).scheme in {"http", "https"}


def is_file_url(value: str) -> bool:
    """Return True when the value is a file URI."""

    return urlparse(value).scheme == "file"


def filename_tail(value: str) -> str:
    """Return the last filename-like path segment for labels."""

    if is_http_url(value) or is_file_url(value):
        return Path(unquote(urlparse(value).path)).name or value
    return Path(value).name or value


def load_csv_source(csv_input: str) -> CsvSource:
    """Load a local or remote CSV into a normalized string dataframe."""

    if is_http_url(csv_input):
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            response = client.get(csv_input)
            response.raise_for_status()
        frame = pd.read_csv(io.StringIO(response.text), dtype=str, keep_default_na=False).fillna("")
        return CsvSource(label=str(response.url), frame=frame, csv_path=None, csv_url=str(response.url))

    csv_path = Path(csv_input).expanduser().resolve()
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False).fillna("")
    return CsvSource(label=str(csv_path), frame=frame, csv_path=csv_path, csv_url=None)


def validate_columns(frame: pd.DataFrame, columns: list[str], *, allow_special: set[str] | None = None) -> None:
    """Raise on missing columns while allowing explicit virtual names."""

    allow_special = allow_special or set()
    missing = [column for column in columns if column not in allow_special and column not in frame.columns]
    if missing:
        sample = ", ".join(missing)
        raise ValueError(f"Unknown CSV column(s): {sample}")


def apply_sample(frame: pd.DataFrame, sample: int | None) -> pd.DataFrame:
    """Apply a deterministic sample while preserving original row order."""

    frame = frame.copy()
    frame["_row_index"] = np.arange(len(frame))
    if sample is None or sample >= len(frame):
        return frame.reset_index(drop=True)
    sampled = frame.sample(n=sample, random_state=42).sort_values("_row_index")
    return sampled.reset_index(drop=True)


def row_text_payload(row: pd.Series, columns: list[str]) -> str:
    """Build the merged text payload for one row."""

    parts = [f"{column}: {str(row[column]).strip()}" for column in columns if str(row[column]).strip()]
    return "\n\n".join(parts)


def default_cache_path(output_path: Path) -> Path:
    """Store the default cache beside the generated HTML output."""

    return output_path.parent / DEFAULT_CACHE_NAME


def resolve_media_input(
    source: CsvSource,
    raw_value: str,
    *,
    kind: Literal["image", "audio"],
    column: str,
) -> MediaInput | None:
    """Resolve one raw media cell into browser and embedding references."""

    value = str(raw_value).strip()
    if not value:
        return None
    if is_http_url(value):
        return MediaInput(
            kind=kind,
            column=column,
            raw_value=value,
            display_url=value,
            local_path=None,
            remote_url=value,
            exists=True,
        )
    if is_file_url(value):
        path = Path(unquote(urlparse(value).path))
        return MediaInput(
            kind=kind,
            column=column,
            raw_value=value,
            display_url=value,
            local_path=path,
            remote_url=None,
            exists=path.exists(),
        )
    if source.csv_url:
        joined = urljoin(source.csv_url, value)
        return MediaInput(
            kind=kind,
            column=column,
            raw_value=value,
            display_url=joined,
            local_path=None,
            remote_url=joined,
            exists=True,
        )
    if not source.csv_path:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (source.csv_path.parent / path).resolve()
    return MediaInput(
        kind=kind,
        column=column,
        raw_value=value,
        display_url=path.as_uri(),
        local_path=path,
        remote_url=None,
        exists=path.exists(),
    )


def timeline_values(frame: pd.DataFrame, timeline_column: str | None) -> pd.Series | None:
    """Parse the optional timeline column into UTC milliseconds."""

    if not timeline_column:
        return None
    parsed = pd.to_datetime(frame[timeline_column], utc=True, errors="coerce")
    return parsed


def timeline_kind(frame: pd.DataFrame, timeline_column: str | None) -> str | None:
    """Infer a friendly timeline formatting mode from the raw CSV values."""

    if not timeline_column:
        return None
    values = [str(value).strip() for value in frame[timeline_column].tolist() if str(value).strip()]
    if not values:
        return None
    if all(value.isdigit() and len(value) == 4 for value in values):
        return "year"
    has_time = any((":" in value) or ("T" in value) for value in values)
    return "datetime" if has_time else "date"


def format_timeline_text(timestamp: pd.Timestamp, kind: str | None) -> str:
    """Render a compact, UI-friendly timeline label."""

    as_utc = timestamp.tz_convert("UTC") if timestamp.tzinfo is not None else timestamp.tz_localize("UTC")
    if kind == "year":
        return as_utc.strftime("%Y")
    if kind == "date":
        return as_utc.strftime("%d %b %Y")
    return as_utc.strftime("%d %b %Y, %H:%M UTC")


def default_label(
    row: pd.Series,
    embedding_columns: list[str],
    image_columns: list[str],
    audio_columns: list[str],
) -> str:
    """Derive a row label when the user did not choose one explicitly."""

    if embedding_columns:
        value = str(row[embedding_columns[0]]).strip()
        if value:
            return truncate(value, MAX_LABEL_CHARS)
    if image_columns:
        value = str(row[image_columns[0]]).strip()
        if value:
            return filename_tail(value)
    if audio_columns:
        value = str(row[audio_columns[0]]).strip()
        if value:
            return filename_tail(value)
    return f"Row {int(row['_row_index']) + 1}"


def prepare_rows(source: CsvSource, config: BuildConfig) -> tuple[list[RowRecord], dict[str, object]]:
    """Normalize rows, resolve labels, and collect image references."""

    frame = apply_sample(source.frame, config.sample)
    validate_columns(
        frame,
        config.embedding_columns
        + config.image_columns
        + config.audio_columns
        + config.audio_metadata_columns,
    )
    validate_columns(frame, config.color_columns + config.filter_columns + config.label_columns)
    validate_columns(frame, [value for value in config.cluster_columns if value != "embeddings"], allow_special={"embeddings"})
    validate_columns(frame, [value for value in config.centroid_trails if value != "cluster"], allow_special={"cluster"})
    if config.timeline_column:
        validate_columns(frame, [config.timeline_column])

    parsed_timeline = timeline_values(frame, config.timeline_column)
    inferred_timeline_kind = timeline_kind(frame, config.timeline_column)
    records: list[RowRecord] = []
    skipped_rows = 0
    missing_local_images = 0
    remote_image_rows = 0
    missing_local_audios = 0
    remote_audio_rows = 0

    for idx, row in frame.iterrows():
        raw = {column: str(row[column]) for column in source.frame.columns}
        tooltip = {column: truncate(raw[column], MAX_TOOLTIP_CHARS) for column in source.frame.columns}
        text_payload = row_text_payload(row, config.embedding_columns)
        images = [
            resolved
            for column in config.image_columns
            if (resolved := resolve_media_input(source, raw[column], kind="image", column=column))
        ]
        audios = [
            resolved
            for column in config.audio_columns
            if (resolved := resolve_media_input(source, raw[column], kind="audio", column=column))
        ]
        audio_metadata_text = (
            row_text_payload(
                row,
                [column for column in config.audio_metadata_columns if column not in config.embedding_columns],
            )
            if audios
            else ""
        )
        if images:
            remote_image_rows += sum(image.remote_url is not None for image in images)
            missing_local_images += sum(image.local_path is not None and not image.exists for image in images)
        if audios:
            remote_audio_rows += sum(audio.remote_url is not None for audio in audios)
            missing_local_audios += sum(audio.local_path is not None and not audio.exists for audio in audios)
        label = truncate(
            " | ".join(str(row[column]).strip() for column in config.label_columns if str(row[column]).strip())
            or default_label(row, config.embedding_columns, config.image_columns, config.audio_columns),
            MAX_LABEL_CHARS,
        )
        timeline_text = None
        timeline_ms = None
        if parsed_timeline is not None and not pd.isna(parsed_timeline.iloc[idx]):
            timestamp = parsed_timeline.iloc[idx]
            timeline_text = format_timeline_text(timestamp, inferred_timeline_kind)
            timeline_ms = int(timestamp.value // 1_000_000)

        has_content = bool(text_payload) or any(
            media.exists or media.remote_url for media in [*images, *audios]
        )
        if not has_content:
            skipped_rows += 1
            continue
        records.append(
            RowRecord(
                row_index=int(row["_row_index"]),
                raw=raw,
                tooltip=tooltip,
                label=label,
                text_payload=text_payload,
                audio_metadata_text=audio_metadata_text,
                images=images,
                audios=audios,
                timeline_text=timeline_text,
                timeline_ms=timeline_ms,
            )
        )

    timeline_non_empty = int(frame[config.timeline_column].astype(str).str.strip().ne("").sum()) if config.timeline_column else 0
    timeline_valid = int(parsed_timeline.notna().sum()) if parsed_timeline is not None else 0
    report = {
        "source": source.label,
        "total_rows": int(len(frame)),
        "usable_rows": int(len(records)),
        "skipped_rows": int(skipped_rows),
        "timeline_non_empty": timeline_non_empty,
        "timeline_valid": timeline_valid,
        "missing_local_images": int(missing_local_images),
        "remote_image_rows": int(remote_image_rows),
        "missing_local_audios": int(missing_local_audios),
        "remote_audio_rows": int(remote_audio_rows),
        "timeline_kind": inferred_timeline_kind,
        "frame": frame,
    }
    return records, report


def dry_run_report(source: CsvSource, config: BuildConfig, records: list[RowRecord], report: dict[str, object]) -> None:
    """Print a compact dry-run summary."""

    frame = report["frame"]
    color_counts = {column: int(frame[column].astype(str).fillna("").nunique(dropna=False)) for column in config.color_columns}
    filter_counts = {column: int(frame[column].astype(str).fillna("").nunique(dropna=False)) for column in config.filter_columns}
    cluster_mode = "kmeans" if "embeddings" in config.cluster_columns else "direct-label"
    console.print(f"Source: {report['source']}")
    console.print(
        f"Rows: {report['total_rows']} sampled, {report['usable_rows']} usable, {report['skipped_rows']} skipped"
    )
    console.print(f"Embedding columns: {config.embedding_columns or ['(none)']}")
    console.print(f"Image columns: {config.image_columns or ['(none)']}")
    console.print(f"Audio columns: {config.audio_columns or ['(none)']}")
    console.print(f"Audio metadata columns: {config.audio_metadata_columns or ['(none)']}")
    console.print(f"Color columns: {config.color_columns or ['(cluster only)']}")
    console.print(f"Filter columns: {config.filter_columns or ['(cluster only)']}")
    console.print(f"Cluster columns: {config.cluster_columns} ({cluster_mode})")
    console.print(f"Label columns: {config.label_columns or ['(derived default)']}")
    console.print(f"Branding: {config.branding}")
    console.print(f"Opacity: {config.opacity}")
    console.print(f"Bar chart corner: {config.bar_chart_corner}")
    console.print(f"Axis labels: {'enabled' if config.axis_labels else 'disabled'} ({config.cluster_naming_model})")
    console.print(f"Cluster naming: {'enabled' if config.cluster_names else 'disabled'} ({config.cluster_naming_model})")
    if config.timeline_column:
        console.print(
            f"Timeline: {config.timeline_column} ({report['timeline_kind'] or 'unknown'}, {report['timeline_valid']}/{report['timeline_non_empty']} parseable)"
        )
    if config.centroid_trails:
        console.print(f"Centroid trails: {config.centroid_trails}")
    if config.centroid_time_period:
        console.print(f"Centroid time period: {config.centroid_time_period}")
    if report["missing_local_images"]:
        console.print(f"Missing local image references: {report['missing_local_images']}")
    if report["remote_image_rows"]:
        console.print(f"Rows with remote image URLs: {report['remote_image_rows']}")
    if report["missing_local_audios"]:
        console.print(f"Missing local audio references: {report['missing_local_audios']}")
    if report["remote_audio_rows"]:
        console.print(f"Rows with remote audio URLs: {report['remote_audio_rows']}")
    if color_counts:
        console.print(f"Color cardinalities: {color_counts}")
    if filter_counts:
        console.print(f"Filter cardinalities: {filter_counts}")
    console.print(f"Cache: {default_cache_path(config.output_path)}")
    console.print(f"Output: {config.output_path}")


def media_bytes(media: MediaInput) -> tuple[bytes, str]:
    """Fetch one media payload and mime type for Gemini embedding."""

    if media.local_path:
        if not media.local_path.exists():
            raise FileNotFoundError(f"Missing {media.kind} file: {media.local_path}")
        mime_type = mimetypes.guess_type(media.local_path.name)[0] or "application/octet-stream"
        data = media.local_path.read_bytes()
        return normalized_image_bytes(data, mime_type) if media.kind == "image" else (data, mime_type)

    if not media.remote_url:
        raise FileNotFoundError(f"Could not resolve {media.kind} reference: {media.raw_value}")
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        response = client.get(media.remote_url)
        response.raise_for_status()
    mime_type = response.headers.get("content-type", "").split(";")[0] or mimetypes.guess_type(media.remote_url)[0] or "application/octet-stream"
    return normalized_image_bytes(response.content, mime_type) if media.kind == "image" else (response.content, mime_type)


def normalized_image_bytes(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Convert image inputs into a Gemini-friendly PNG payload."""

    if not mime_type.startswith("image/"):
        return data, mime_type
    with Image.open(io.BytesIO(data)) as image:
        converted = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
        buffer = io.BytesIO()
        converted.save(buffer, format="PNG")
        return buffer.getvalue(), "image/png"


def build_content(record: RowRecord) -> types.Content:
    """Create one Gemini content payload for a row."""

    parts: list[types.Part] = []
    if record.text_payload:
        parts.append(types.Part.from_text(text=record.text_payload))
    if record.audio_metadata_text:
        parts.append(types.Part.from_text(text=f"Audio metadata:\n{record.audio_metadata_text}"))
    for image in record.images:
        data, mime_type = media_bytes(image)
        parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
    for audio in record.audios:
        data, mime_type = media_bytes(audio)
        parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
    if not parts:
        raise ValueError(f"Row {record.row_index} has no embeddable content")
    return types.Content(parts=parts)


def normalize_vectors(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize vectors for cosine-friendly downstream analysis."""

    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms == 0, 1.0, norms)
    return matrix / safe


def stable_json(value: object) -> str:
    """Serialize compact stable JSON for hashing and cache payloads."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def ensure_cache_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create the small cache tables used for embeddings and cluster names."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_cache (
          cache_key TEXT PRIMARY KEY,
          source_label TEXT NOT NULL,
          row_index BIGINT NOT NULL,
          content_hash TEXT NOT NULL,
          model TEXT NOT NULL,
          dimensions INTEGER NOT NULL,
          vector BLOB NOT NULL,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cluster_name_cache (
          cache_key TEXT PRIMARY KEY,
          model TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS axis_label_cache (
          cache_key TEXT PRIMARY KEY,
          model TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def with_cache(cache_path: Path) -> duckdb.DuckDBPyConnection:
    """Open the default duckdb cache, creating parent directories as needed."""

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(cache_path))
    ensure_cache_schema(connection)
    return connection


def media_signature(media: MediaInput) -> dict[str, object]:
    """Build a stable cache signature for one media input without re-downloading it."""

    signature: dict[str, object] = {
        "kind": media.kind,
        "column": media.column,
        "raw_value": media.raw_value,
        "display_url": media.display_url,
        "exists": media.exists,
    }
    if media.local_path:
        signature["local_path"] = str(media.local_path)
        if media.exists:
            stat = media.local_path.stat()
            signature["size"] = stat.st_size
            signature["mtime_ns"] = stat.st_mtime_ns
    if media.remote_url:
        signature["remote_url"] = media.remote_url
    return signature


def record_content_hash(record: RowRecord) -> str:
    """Hash the normalized embeddable row inputs for cache reuse."""

    payload = {
        "text_payload": record.text_payload,
        "audio_metadata_text": record.audio_metadata_text,
        "images": [media_signature(image) for image in record.images],
        "audios": [media_signature(audio) for audio in record.audios],
    }
    return sha256(stable_json(payload).encode("utf-8")).hexdigest()


def record_cache_key(source: CsvSource, record: RowRecord, model: str, dimensions: int) -> tuple[str, str]:
    """Return the cache key plus the underlying content hash for one row."""

    content_hash = record_content_hash(record)
    payload = {
        "version": EMBEDDING_CACHE_VERSION,
        "source": source.label,
        "row_index": record.row_index,
        "content_hash": content_hash,
        "model": model,
        "dimensions": dimensions,
    }
    return sha256(stable_json(payload).encode("utf-8")).hexdigest(), content_hash


def cached_vectors(
    connection: duckdb.DuckDBPyConnection,
    cache_keys: list[str],
    dimensions: int,
) -> dict[str, np.ndarray]:
    """Fetch cached vectors for the requested keys."""

    if not cache_keys:
        return {}
    placeholders = ", ".join("?" for _ in cache_keys)
    rows = connection.execute(
        f"SELECT cache_key, vector FROM embedding_cache WHERE cache_key IN ({placeholders})",
        cache_keys,
    ).fetchall()
    return {
        str(cache_key): np.frombuffer(vector_blob, dtype=np.float32, count=dimensions).copy()
        for cache_key, vector_blob in rows
    }


def store_cached_vectors(
    connection: duckdb.DuckDBPyConnection,
    rows: list[tuple[str, str, int, str, str, int, bytes]],
) -> None:
    """Persist newly generated embeddings into the cache."""

    if not rows:
        return
    connection.executemany(
        """
        INSERT OR REPLACE INTO embedding_cache
          (cache_key, source_label, row_index, content_hash, model, dimensions, vector)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def gemini_client() -> genai.Client:
    """Build a Gemini client from the environment."""

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in the environment or .env before building")
    return genai.Client(api_key=api_key)


@retry(
    retry=retry_if_exception_type(genai_errors.ServerError),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)
def embed_batch_once(
    client: genai.Client,
    model: str,
    dimensions: int,
    contents: list[types.Content],
) -> np.ndarray:
    """Embed one batch via Gemini."""

    response = client.models.embed_content(
        model=model,
        contents=contents,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=dimensions,
        ),
    )
    vectors = np.array([list(item.values) for item in response.embeddings], dtype=np.float32)
    return normalize_vectors(vectors)


def embed_records(source: CsvSource, records: list[RowRecord], config: BuildConfig) -> np.ndarray:
    """Embed all prepared rows with cache reuse, retries, and bounded batching."""

    cache_path = default_cache_path(config.output_path)
    cache_entries = [record_cache_key(source, record, config.model, config.dimensions) for record in records]
    cache_keys = [cache_key for cache_key, _ in cache_entries]
    with with_cache(cache_path) as connection:
        cached = cached_vectors(connection, cache_keys, config.dimensions)

    vectors = np.empty((len(records), config.dimensions), dtype=np.float32)
    missing_indices = [idx for idx, cache_key in enumerate(cache_keys) if cache_key not in cached]
    for idx, cache_key in enumerate(cache_keys):
        if cache_key in cached:
            vectors[idx] = cached[cache_key]

    if not missing_indices:
        console.print(f"Embedding cache hit: reused {len(records)} of {len(records)} rows from {cache_path}")
        return vectors

    client = gemini_client()
    console.print(
        f"Embedding cache hit: reused {len(records) - len(missing_indices)} of {len(records)} rows from {cache_path}"
    )
    rows_to_store: list[tuple[str, str, int, str, str, int, bytes]] = []
    for start in range(0, len(missing_indices), DEFAULT_BATCH_SIZE):
        batch_indices = missing_indices[start : start + DEFAULT_BATCH_SIZE]
        batch = [records[idx] for idx in batch_indices]
        batch_range = f"{batch_indices[0] + 1}-{batch_indices[-1] + 1}"
        console.print(f"Embedding uncached rows {batch_range} of {len(records)}...")
        contents = [build_content(record) for record in batch]
        delay = 4
        for attempt in range(6):
            try:
                batch_vectors = embed_batch_once(client, config.model, config.dimensions, contents)
                break
            except genai_errors.ClientError as exc:
                message = str(exc)
                if "429" not in message and "RESOURCE_EXHAUSTED" not in message:
                    raise
                if attempt == 5:
                    raise
                console.print(f"Rate limited. Sleeping {delay}s before retry {attempt + 1}/6.")
                import time

                time.sleep(delay)
                delay = min(delay * 2, 120)
        for idx, vector in zip(batch_indices, batch_vectors, strict=True):
            vectors[idx] = vector
            cache_key, content_hash = cache_entries[idx]
            rows_to_store.append(
                (
                    cache_key,
                    source.label,
                    records[idx].row_index,
                    content_hash,
                    config.model,
                    config.dimensions,
                    vector.astype(np.float32).tobytes(),
                )
            )

    with with_cache(cache_path) as connection:
        store_cached_vectors(connection, rows_to_store)
    return vectors


def fallback_coords(vectors: np.ndarray) -> np.ndarray:
    """Return a deterministic 2D fallback when UMAP cannot fit."""

    count = len(vectors)
    if count == 0:
        return np.empty((0, 2), dtype=np.float32)
    if count == 1:
        return np.zeros((1, 2), dtype=np.float32)
    if count == 2:
        return np.array([[-1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    pca = PCA(n_components=min(2, vectors.shape[1]), random_state=42)
    coords = pca.fit_transform(vectors).astype(np.float32)
    if coords.shape[1] == 1:
        coords = np.column_stack([coords[:, 0], np.zeros(len(coords), dtype=np.float32)])
    return coords


def project_umap(vectors: np.ndarray) -> np.ndarray:
    """Project embeddings into a 2D layout."""

    count = len(vectors)
    if count < 5:
        return fallback_coords(vectors)
    pca_components = min(50, count - 1, vectors.shape[1])
    pca = PCA(n_components=pca_components, random_state=42)
    reduced = pca.fit_transform(vectors).astype(np.float32)
    import umap

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(UMAP_NEIGHBORS, max(2, count - 1)),
        min_dist=UMAP_MIN_DIST,
        metric="cosine",
        random_state=42,
    )
    return reducer.fit_transform(reduced).astype(np.float32)


def cluster_count(count: int) -> int:
    """Choose a modest default cluster count without exposing a flag yet."""

    if count <= 1:
        return 1
    if count < 9:
        return 2
    return min(12, max(2, round(math.sqrt(count))))


def reorder_labels(raw_labels: np.ndarray) -> tuple[np.ndarray, dict[int, int]]:
    """Reassign cluster ids by descending size."""

    counts = pd.Series(raw_labels).value_counts().sort_values(ascending=False)
    mapping = {int(label): idx for idx, label in enumerate(counts.index)}
    mapped = np.array([mapping[int(label)] for label in raw_labels], dtype=np.int32)
    return mapped, mapping


def direct_cluster_labels(records: list[RowRecord], columns: list[str]) -> tuple[np.ndarray, dict[int, str]]:
    """Use one or more CSV columns directly as cluster labels."""

    labels = []
    for record in records:
        parts = []
        for column in columns:
            value = record.raw[column].strip() or "(blank)"
            parts.append(value if len(columns) == 1 else f"{column}={value}")
        labels.append(" | ".join(parts))
    series = pd.Series(labels)
    codes, uniques = pd.factorize(series, sort=False)
    mapped, mapping = reorder_labels(codes.astype(np.int32))
    label_map = {new: str(uniques[old]) for old, new in mapping.items()}
    return mapped, label_map


def kmeans_clusters(
    records: list[RowRecord],
    vectors: np.ndarray,
    columns: list[str],
) -> tuple[np.ndarray, dict[int, str]]:
    """Cluster on embeddings plus optional one-hot metadata."""

    blocks: list[np.ndarray] = []
    if "embeddings" in columns or not columns:
        embed_components = min(32, len(vectors) - 1, vectors.shape[1]) if len(vectors) > 2 else vectors.shape[1]
        if embed_components and embed_components < vectors.shape[1]:
            pca = PCA(n_components=embed_components, random_state=42)
            embed_block = pca.fit_transform(vectors).astype(np.float32)
        else:
            embed_block = vectors.astype(np.float32)
        blocks.append(normalize_vectors(embed_block))

    meta_columns = [column for column in columns if column != "embeddings"]
    if meta_columns:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float32)
        encoded = encoder.fit_transform([[record.raw[column] for column in meta_columns] for record in records])
        blocks.append(0.45 * normalize_vectors(encoded))

    feature_matrix = np.hstack(blocks) if len(blocks) > 1 else blocks[0]
    if len(records) < 2:
        labels = np.zeros(len(records), dtype=np.int32)
    else:
        model = KMeans(n_clusters=cluster_count(len(records)), random_state=42, n_init="auto")
        labels = model.fit_predict(feature_matrix)
    mapped, _ = reorder_labels(labels)
    names = {cluster_id: f"Cluster {cluster_id + 1}" for cluster_id in sorted(set(mapped.tolist()))}
    return mapped, names


def representative_row_payload(record: RowRecord) -> dict[str, object]:
    """Build a compact row summary for cluster naming prompts."""

    summary_fields = []
    for key, value in record.raw.items():
        cleaned = str(value).strip()
        if not cleaned:
            continue
        summary_fields.append(f"{key}={truncate(cleaned, 80)}")
        if len(summary_fields) == 4:
            break
    return {
        "row_index": record.row_index,
        "label": record.label,
        "text_excerpt": truncate(record.text_payload.replace("\n\n", " | "), 220) if record.text_payload else "",
        "summary": " | ".join(summary_fields),
        "timeline": record.timeline_text or "",
    }


def cluster_centroids(vectors: np.ndarray, cluster_ids: np.ndarray) -> dict[int, np.ndarray]:
    """Compute one normalized centroid per cluster in embedding space."""

    centroids: dict[int, np.ndarray] = {}
    for cluster_id in sorted(set(int(value) for value in cluster_ids.tolist())):
        centroid = vectors[cluster_ids == cluster_id].mean(axis=0, keepdims=True)
        centroids[cluster_id] = normalize_vectors(centroid)[0]
    return centroids


def cluster_context_columns(config: BuildConfig, frame: pd.DataFrame) -> list[str]:
    """Choose a small set of categorical columns that can help with naming."""

    columns = list(
        dict.fromkeys(
            [
                *config.color_columns,
                *config.filter_columns,
                *[column for column in config.cluster_columns if column != "embeddings"],
                *([config.timeline_column] if config.timeline_column else []),
            ]
        )
    )
    return [column for column in columns if column in frame.columns]


def salient_cluster_values(
    records: list[RowRecord],
    indices: np.ndarray,
    columns: list[str],
) -> list[str]:
    """Summarize a few recurring column values for one cluster."""

    if not columns:
        return []
    summaries: list[tuple[int, str]] = []
    cluster_rows = [records[int(index)] for index in indices.tolist()]
    for column in columns:
        values = [row.raw[column].strip() or "(blank)" for row in cluster_rows]
        counts = Counter(values)
        if not counts:
            continue
        unique_count = len(counts)
        if unique_count > min(8, max(3, len(cluster_rows) // 2)):
            continue
        top_values = counts.most_common(2)
        rendered = ", ".join(f"{value} ({count}/{len(cluster_rows)})" for value, count in top_values)
        summaries.append((top_values[0][1], f"{column}: {rendered}"))
    summaries.sort(reverse=True)
    return [summary for _, summary in summaries[:3]]


def naming_context(
    source: CsvSource,
    records: list[RowRecord],
    vectors: np.ndarray,
    cluster_ids: np.ndarray,
    cluster_labels: dict[int, str],
    config: BuildConfig,
) -> list[dict[str, object]]:
    """Build the compact per-cluster context sent to the naming model."""

    centroids = cluster_centroids(vectors, cluster_ids)
    centroid_matrix = np.vstack([centroids[cluster_id] for cluster_id in sorted(centroids)])
    similarity_matrix = centroid_matrix @ centroid_matrix.T if len(centroid_matrix) > 1 else np.ones((1, 1), dtype=np.float32)
    cluster_order = sorted(centroids)
    cluster_columns = cluster_context_columns(config, source.frame)
    contexts: list[dict[str, object]] = []
    for position, cluster_id in enumerate(cluster_order):
        cluster_indices = np.where(cluster_ids == cluster_id)[0]
        scores = vectors[cluster_indices] @ centroids[cluster_id]
        top_local = cluster_indices[np.argsort(-scores)[:CLUSTER_NAMING_TOP_N]]
        neighbor_positions = np.argsort(-similarity_matrix[position]).tolist()
        contrast_clusters = [cluster_order[idx] for idx in neighbor_positions if cluster_order[idx] != cluster_id][
            :CLUSTER_NAMING_NEIGHBORS
        ]
        nearby = []
        for other_cluster_id in contrast_clusters:
            other_indices = np.where(cluster_ids == other_cluster_id)[0]
            other_scores = vectors[other_indices] @ centroids[other_cluster_id]
            top_other = other_indices[np.argsort(-other_scores)[:CLUSTER_NAMING_CONTRAST_ROWS]]
            nearby.append(
                {
                    "cluster_id": other_cluster_id,
                    "label": cluster_labels[other_cluster_id],
                    "rows": [representative_row_payload(records[int(index)]) for index in top_other.tolist()],
                }
            )
        contexts.append(
            {
                "cluster_id": cluster_id,
                "current_label": cluster_labels[cluster_id],
                "size": int(len(cluster_indices)),
                "salient_values": salient_cluster_values(records, cluster_indices, cluster_columns),
                "rows": [representative_row_payload(records[int(index)]) for index in top_local.tolist()],
                "nearby_clusters": nearby,
            }
        )
    return contexts


def cluster_name_cache_key(model: str, contexts: list[dict[str, object]]) -> str:
    """Hash the naming request so cluster names can be reused independently."""

    payload = {"version": CLUSTER_NAMING_VERSION, "model": model, "clusters": contexts}
    return sha256(stable_json(payload).encode("utf-8")).hexdigest()


def load_cached_cluster_names(
    connection: duckdb.DuckDBPyConnection,
    cache_key: str,
) -> dict[int, str] | None:
    """Load cached cluster names for a given naming request."""

    row = connection.execute(
        "SELECT payload_json FROM cluster_name_cache WHERE cache_key = ?",
        [cache_key],
    ).fetchone()
    if not row:
        return None
    payload = json.loads(str(row[0]))
    if isinstance(payload, dict) and "clusters" in payload:
        payload = payload["clusters"]
    return {
        int(item["cluster_id"]): str(item["name"]).strip()
        for item in payload
        if str(item.get("name", "")).strip()
    }


def store_cached_cluster_names(
    connection: duckdb.DuckDBPyConnection,
    cache_key: str,
    model: str,
    payload: list[dict[str, object]],
) -> None:
    """Persist generated cluster names in the cache."""

    connection.execute(
        """
        INSERT OR REPLACE INTO cluster_name_cache
          (cache_key, model, payload_json)
        VALUES (?, ?, ?)
        """,
        [cache_key, model, stable_json(payload)],
    )


def default_axis_labels() -> dict[str, str]:
    """Return the fallback projection labels used without LLM interpretation."""

    return {"x": "UMAP 1", "y": "UMAP 2"}


def axis_side_payload(
    records: list[RowRecord],
    coords: np.ndarray,
    cluster_ids: np.ndarray,
    cluster_labels: dict[int, str],
    indices: np.ndarray,
    columns: list[str],
) -> dict[str, object]:
    """Summarize one side of the 2D projection for axis interpretation."""

    rows = []
    for index in indices.tolist():
        summary = representative_row_payload(records[int(index)])
        rows.append(
            {
                **summary,
                "cluster_id": int(cluster_ids[int(index)]),
                "cluster_label": cluster_labels[int(cluster_ids[int(index)])],
                "x": round(float(coords[int(index), 0]), 4),
                "y": round(float(coords[int(index), 1]), 4),
            }
        )
    return {
        "salient_values": salient_cluster_values(records, indices, columns),
        "rows": rows,
    }


def axis_label_context(
    source: CsvSource,
    records: list[RowRecord],
    coords: np.ndarray,
    cluster_ids: np.ndarray,
    cluster_labels: dict[int, str],
    config: BuildConfig,
) -> dict[str, object]:
    """Build the compact prompt payload used to interpret the two plotted axes."""

    if len(records) == 0:
        return {"source": Path(source.label).name}
    context_columns = cluster_context_columns(config, source.frame)
    x_order = np.argsort(coords[:, 0])
    y_order = np.argsort(coords[:, 1])
    top_n = min(AXIS_LABEL_TOP_N, len(records))
    return {
        "source": Path(source.label).name,
        "x_low": axis_side_payload(records, coords, cluster_ids, cluster_labels, x_order[:top_n], context_columns),
        "x_high": axis_side_payload(
            records, coords, cluster_ids, cluster_labels, x_order[::-1][:top_n], context_columns
        ),
        "y_low": axis_side_payload(records, coords, cluster_ids, cluster_labels, y_order[:top_n], context_columns),
        "y_high": axis_side_payload(
            records, coords, cluster_ids, cluster_labels, y_order[::-1][:top_n], context_columns
        ),
    }


def axis_label_cache_key(model: str, context: dict[str, object]) -> str:
    """Hash the axis-label request so projection labels can be reused."""

    payload = {"version": AXIS_LABEL_VERSION, "model": model, "axis_context": context}
    return sha256(stable_json(payload).encode("utf-8")).hexdigest()


def load_cached_axis_labels(
    connection: duckdb.DuckDBPyConnection,
    cache_key: str,
) -> dict[str, str] | None:
    """Load cached axis labels for a given interpretation request."""

    row = connection.execute(
        "SELECT payload_json FROM axis_label_cache WHERE cache_key = ?",
        [cache_key],
    ).fetchone()
    if not row:
        return None
    payload = json.loads(str(row[0]))
    x_label = str(payload.get("x", "")).strip()
    y_label = str(payload.get("y", "")).strip()
    return {"x": x_label, "y": y_label} if x_label and y_label else None


def store_cached_axis_labels(
    connection: duckdb.DuckDBPyConnection,
    cache_key: str,
    model: str,
    payload: dict[str, object],
) -> None:
    """Persist generated axis labels in the cache."""

    connection.execute(
        """
        INSERT OR REPLACE INTO axis_label_cache
          (cache_key, model, payload_json)
        VALUES (?, ?, ?)
        """,
        [cache_key, model, stable_json(payload)],
    )


@retry(
    retry=retry_if_exception_type(genai_errors.ServerError),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)
def generate_structured_content_once(
    client: genai.Client,
    model: str,
    prompt: str,
    schema: dict[str, object],
) -> str:
    """Generate one structured JSON response via Gemini."""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        ),
    )
    return response.text or "[]"


def dedupe_cluster_names(
    proposed: dict[int, str],
    fallback: dict[int, str],
) -> dict[int, str]:
    """Keep cluster names short, non-empty, and unique."""

    final: dict[int, str] = {}
    seen: Counter[str] = Counter()
    for cluster_id in sorted(fallback):
        candidate = truncate(proposed.get(cluster_id, "").strip() or fallback[cluster_id], 48)
        seen[candidate.casefold()] += 1
        if seen[candidate.casefold()] > 1:
            candidate = truncate(f"{candidate} ({seen[candidate.casefold()]})", 48)
        final[cluster_id] = candidate
    return final


def maybe_name_clusters(
    source: CsvSource,
    records: list[RowRecord],
    vectors: np.ndarray,
    cluster_ids: np.ndarray,
    cluster_labels: dict[int, str],
    config: BuildConfig,
) -> dict[int, str]:
    """Replace generic cluster labels with short LLM-generated names when requested."""

    if not config.cluster_names or not cluster_labels:
        return cluster_labels

    contexts = naming_context(source, records, vectors, cluster_ids, cluster_labels, config)
    cache_key = cluster_name_cache_key(config.cluster_naming_model, contexts)
    cache_path = default_cache_path(config.output_path)
    with with_cache(cache_path) as connection:
        cached = load_cached_cluster_names(connection, cache_key)
    if cached:
        console.print(f"Cluster-name cache hit: reused names from {cache_path}")
        return dedupe_cluster_names(cached, cluster_labels)

    prompt = "\n".join(
        [
            "Name each cluster for an embedding visualization.",
            "Return only JSON: an array of objects with cluster_id, name, and optional rationale.",
            "Use reasonably short names, ideally 2 to 5 words.",
            "Names must characterize the cluster well, stay broad enough for future rows, and disambiguate similar nearby clusters.",
            "Do not repeat generic labels like Cluster 1 unless you have no better option.",
            "",
            stable_json(contexts),
        ]
    )
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "cluster_id": {"type": "INTEGER"},
                "name": {"type": "STRING"},
                "rationale": {"type": "STRING"},
            },
            "required": ["cluster_id", "name"],
        },
    }
    client = gemini_client()
    delay = 4
    for attempt in range(6):
        try:
            text = generate_structured_content_once(client, config.cluster_naming_model, prompt, schema)
            break
        except genai_errors.ClientError as exc:
            message = str(exc)
            if "429" not in message and "RESOURCE_EXHAUSTED" not in message:
                console.print(f"Cluster naming failed: {exc}. Keeping base labels.")
                return cluster_labels
            if attempt == 5:
                console.print(f"Cluster naming failed: {exc}. Keeping base labels.")
                return cluster_labels
            console.print(f"Cluster naming rate limited. Sleeping {delay}s before retry {attempt + 1}/6.")
            import time

            time.sleep(delay)
            delay = min(delay * 2, 120)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and "clusters" in payload:
            payload = payload["clusters"]
        proposed = {
            int(item["cluster_id"]): str(item["name"]).strip()
            for item in payload
            if str(item.get("name", "")).strip()
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        console.print(f"Cluster naming returned invalid JSON: {exc}. Keeping base labels.")
        return cluster_labels

    with with_cache(cache_path) as connection:
        store_cached_cluster_names(connection, cache_key, config.cluster_naming_model, payload)
    return dedupe_cluster_names(proposed, cluster_labels)


def maybe_label_axes(
    source: CsvSource,
    records: list[RowRecord],
    coords: np.ndarray,
    cluster_ids: np.ndarray,
    cluster_labels: dict[int, str],
    config: BuildConfig,
) -> dict[str, str]:
    """Interpret the plotted x/y dimensions with short human-facing labels."""

    fallback = default_axis_labels()
    if not config.axis_labels or len(records) < 3:
        return fallback

    context = axis_label_context(source, records, coords, cluster_ids, cluster_labels, config)
    cache_key = axis_label_cache_key(config.cluster_naming_model, context)
    cache_path = default_cache_path(config.output_path)
    with with_cache(cache_path) as connection:
        cached = load_cached_axis_labels(connection, cache_key)
    if cached:
        console.print(f"Axis-label cache hit: reused labels from {cache_path}")
        return cached

    prompt = "\n".join(
        [
            "Interpret the two plotted dimensions of an embedding visualization for humans.",
            "Return only JSON with keys x and y.",
            "Each label must describe movement from low to high values in 3 to 10 words.",
            "Use a compact directional form like 'Personal stories -> AI tooling'.",
            "Be intuitive and tentative. These are latent embedding axes, so do not overclaim.",
            "Do not mention UMAP, coordinates, or row ids in the labels.",
            "",
            stable_json(context),
        ]
    )
    schema = {
        "type": "OBJECT",
        "properties": {
            "x": {"type": "STRING"},
            "y": {"type": "STRING"},
            "x_rationale": {"type": "STRING"},
            "y_rationale": {"type": "STRING"},
        },
        "required": ["x", "y"],
    }
    client = gemini_client()
    delay = 4
    for attempt in range(6):
        try:
            text = generate_structured_content_once(client, config.cluster_naming_model, prompt, schema)
            break
        except genai_errors.ClientError as exc:
            message = str(exc)
            if "429" not in message and "RESOURCE_EXHAUSTED" not in message:
                console.print(f"Axis labeling failed: {exc}. Keeping fallback labels.")
                return fallback
            if attempt == 5:
                console.print(f"Axis labeling failed: {exc}. Keeping fallback labels.")
                return fallback
            console.print(f"Axis labeling rate limited. Sleeping {delay}s before retry {attempt + 1}/6.")
            import time

            time.sleep(delay)
            delay = min(delay * 2, 120)
    try:
        payload = json.loads(text)
        x_label = truncate(str(payload.get("x", "")).strip(), 72)
        y_label = truncate(str(payload.get("y", "")).strip(), 72)
    except Exception as exc:  # pragma: no cover - defensive fallback
        console.print(f"Axis labeling returned invalid JSON: {exc}. Keeping fallback labels.")
        return fallback
    if not x_label or not y_label:
        return fallback

    labels = {"x": x_label, "y": y_label}
    with with_cache(cache_path) as connection:
        store_cached_axis_labels(connection, cache_key, config.cluster_naming_model, labels)
    return labels


def analyze_records(
    source: CsvSource,
    records: list[RowRecord],
    config: BuildConfig,
) -> tuple[np.ndarray, np.ndarray, dict[int, str], dict[str, str]]:
    """Embed, project, cluster, and optionally name the prepared rows."""

    vectors = embed_records(source, records, config)
    coords = project_umap(vectors)
    if config.cluster_columns == ["embeddings"] or "embeddings" in config.cluster_columns:
        cluster_ids, cluster_labels = kmeans_clusters(records, vectors, config.cluster_columns)
    else:
        cluster_ids, cluster_labels = direct_cluster_labels(records, config.cluster_columns)
    cluster_labels = maybe_name_clusters(source, records, vectors, cluster_ids, cluster_labels, config)
    axis_labels = maybe_label_axes(source, records, coords, cluster_ids, cluster_labels, config)
    return coords, cluster_ids, cluster_labels, axis_labels


MIN_CENTROID_BUCKET_SIZE = 2
MIN_CENTROID_TRAIL_POINTS = 2
CENTROID_TIME_ALIASES = {
    "hourly": "1h",
    "daily": "1d",
    "weekly": "1w",
    "fortnightly": "2w",
    "biweekly": "2w",
    "monthly": "1 month",
    "quarterly": "1q",
    "yearly": "1y",
    "annual": "1y",
    "annually": "1y",
}
CALENDAR_PERIOD_UNITS = {
    "mo": "M",
    "mon": "M",
    "month": "M",
    "months": "M",
    "q": "Q-DEC",
    "quarter": "Q-DEC",
    "quarters": "Q-DEC",
    "y": "Y-DEC",
    "yr": "Y-DEC",
    "year": "Y-DEC",
    "years": "Y-DEC",
}
WEEK_PERIOD = re.compile(r"^(?P<count>\d+)\s*(?:w|wk|wks|week|weeks)$", re.IGNORECASE)
CALENDAR_PERIOD = re.compile(
    r"^(?P<count>\d+)\s*(?P<unit>mo|mon|month|months|q|quarter|quarters|y|yr|year|years)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TrailTimePeriod:
    """Parsed centroid trail period."""

    duration_ms: int | None = None
    frequency: str | None = None


@dataclass(frozen=True, slots=True)
class TrailBucket:
    """Resolved trail bucket metadata for one timestamp."""

    key: int | tuple[int, ...]
    label: str
    start_ms: int
    end_ms: int


def parse_centroid_time_period(value: str | None) -> TrailTimePeriod | None:
    """Parse a user-friendly centroid trail period."""

    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    if not normalized:
        return None
    normalized = CENTROID_TIME_ALIASES.get(normalized, normalized)
    if match := WEEK_PERIOD.fullmatch(normalized):
        count = int(match.group("count"))
        prefix = "" if count == 1 else str(count)
        return TrailTimePeriod(frequency=f"{prefix}W-SUN")
    if match := CALENDAR_PERIOD.fullmatch(normalized):
        count = int(match.group("count"))
        prefix = "" if count == 1 else str(count)
        return TrailTimePeriod(frequency=f"{prefix}{CALENDAR_PERIOD_UNITS[match.group('unit').lower()]}")
    try:
        duration = pd.Timedelta(normalized)
    except ValueError as exc:
        raise ValueError(
            "Invalid --centroid-time-period. Examples: 1h, 2.5h, 2h 15min, daily, weekly, 30d, 2Q."
        ) from exc
    duration_ms = int(duration.value // 1_000_000)
    if duration_ms <= 0:
        raise ValueError("--centroid-time-period must be greater than zero.")
    return TrailTimePeriod(duration_ms=duration_ms)


def compute_centroid_trails(
    rows: list[dict[str, object]],
    cluster_labels: dict[int, str],
    timeline_kind_value: str | None,
    trail_columns: list[str] | None = None,
    time_period: str | None = None,
) -> dict[str, list[dict[str, object]]] | None:
    """Compute centroid trails per group per time bucket.

    Returns a dict keyed by trail column ("cluster", "category", etc.)
    mapping to lists of trail objects. Returns *None* when timeline data
    is missing or insufficient.
    """

    timed = [row for row in rows if row["timelineMs"] is not None]
    if len(timed) < MIN_CENTROID_TRAIL_POINTS:
        return None

    period = parse_centroid_time_period(time_period)
    result: dict[str, list[dict[str, object]]] = {}
    for column in dict.fromkeys(trail_columns or []):
        trails = _trails_for_group(
            timed,
            timeline_kind_value,
            period,
            group_fn=(
                (lambda row: row["clusterId"])
                if column == "cluster"
                else (lambda row, current=column: _trail_group_value(row, current))
            ),
            label_fn=(
                (lambda group_id: cluster_labels.get(int(group_id), str(group_id)))
                if column == "cluster"
                else str
            ),
        )
        if trails:
            result[column] = trails

    return result or None


def _trails_for_group(
    timed_rows: list[dict[str, object]],
    timeline_kind_value: str | None,
    period: TrailTimePeriod | None,
    group_fn,
    label_fn,
) -> list[dict[str, object]]:
    """Build centroid trails for an arbitrary grouping function."""

    buckets: dict[tuple[object, int | tuple[int, ...]], list[dict[str, object]]] = {}
    bucket_info: dict[int | tuple[int, ...], TrailBucket] = {}
    for row in timed_rows:
        group_id = group_fn(row)
        bucket = _trail_bucket(int(row["timelineMs"]), timeline_kind_value, period)
        bucket_info[bucket.key] = bucket
        buckets.setdefault((group_id, bucket.key), []).append(row)

    trails: list[dict[str, object]] = []
    for group_id in sorted({group_fn(row) for row in timed_rows}, key=str):
        points = []
        group_buckets = sorted(
            (
                (bucket_info[bucket_key], rows_for_bucket)
                for (gid, bucket_key), rows_for_bucket in buckets.items()
                if gid == group_id
            ),
            key=lambda item: item[0].start_ms,
        )
        for bucket, rows_for_bucket in group_buckets:
            if len(rows_for_bucket) < MIN_CENTROID_BUCKET_SIZE:
                continue
            count = len(rows_for_bucket)
            cx = sum(float(row["x"]) for row in rows_for_bucket) / count
            cy = sum(float(row["y"]) for row in rows_for_bucket) / count
            std = (
                sum((float(row["x"]) - cx) ** 2 + (float(row["y"]) - cy) ** 2 for row in rows_for_bucket) / count
            ) ** 0.5
            points.append(
                {
                    "time": bucket.key,
                    "timeLabel": bucket.label,
                    "timeStartMs": bucket.start_ms,
                    "timeEndMs": bucket.end_ms,
                    "x": round(cx, 6),
                    "y": round(cy, 6),
                    "count": count,
                    "std": round(std, 6),
                }
            )
        if len(points) >= MIN_CENTROID_TRAIL_POINTS:
            trails.append({"groupId": str(group_id), "groupLabel": label_fn(group_id), "points": points})
    return trails


def _trail_group_value(row: dict[str, object], column: str) -> str:
    """Read one trail grouping value from the payload row."""

    for field in ("colors", "filters", "raw"):
        values = row.get(field)
        if isinstance(values, dict) and column in values:
            return str(values[column]).strip() or "(blank)"
    return "(blank)"


def _trail_bucket(ms: int, kind: str | None, period: TrailTimePeriod | None) -> TrailBucket:
    """Build a serialized bucket for one trail timestamp."""

    if period is None:
        key = _time_bucket(ms, kind)
        start_ms, end_ms = _default_bucket_bounds(ms, kind)
        return TrailBucket(key=key, label=_bucket_label(key, kind), start_ms=start_ms, end_ms=end_ms)
    if period.frequency:
        timestamp = pd.Timestamp(ms, unit="ms", tz="UTC").tz_localize(None)
        bucket = timestamp.to_period(period.frequency)
        start = bucket.start_time.tz_localize("UTC")
        end = bucket.end_time.tz_localize("UTC")
        return TrailBucket(
            key=int(start.value // 1_000_000),
            label=_period_label(start, end),
            start_ms=int(start.value // 1_000_000),
            end_ms=int(end.value // 1_000_000),
        )
    assert period.duration_ms is not None
    start_ms = (ms // period.duration_ms) * period.duration_ms
    end_ms = start_ms + period.duration_ms - 1
    start = pd.Timestamp(start_ms, unit="ms", tz="UTC")
    end = pd.Timestamp(end_ms, unit="ms", tz="UTC")
    return TrailBucket(
        key=start_ms,
        label=_period_label(start, end),
        start_ms=start_ms,
        end_ms=end_ms,
    )


def _time_bucket(ms: int, kind: str | None) -> int | tuple[int, int] | tuple[int, int, int]:
    """Map a UTC-ms timestamp to a discrete time bucket."""

    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    if kind == "year":
        return dt.year
    if kind == "date":
        return (dt.year, dt.month, dt.day)
    return (dt.year, dt.month)


def _default_bucket_bounds(ms: int, kind: str | None) -> tuple[int, int]:
    """Return inclusive UTC-ms bounds for the default trail bucket."""

    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    if kind == "year":
        start = datetime(dt.year, 1, 1, tzinfo=UTC)
        end = datetime(dt.year + 1, 1, 1, tzinfo=UTC)
        return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1
    if kind == "date":
        start = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
        end = start + pd.Timedelta(days=1).to_pytimedelta()
        return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1
    start = datetime(dt.year, dt.month, 1, tzinfo=UTC)
    if dt.month == 12:
        end = datetime(dt.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(dt.year, dt.month + 1, 1, tzinfo=UTC)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1


def _bucket_label(bucket: int | tuple, kind: str | None) -> str:
    """Human-readable label for a time bucket."""

    if isinstance(bucket, tuple):
        if len(bucket) == 3:
            return f"{bucket[0]}-{bucket[1]:02d}-{bucket[2]:02d}"
        return f"{bucket[0]}-{bucket[1]:02d}"
    return str(bucket)


def _period_label(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Render a compact label for a custom trail period."""

    if start.normalize() == start and end == (start + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)):
        return start.strftime("%Y-%m-%d")
    start_text = start.strftime("%Y-%m-%d %H:%M UTC")
    end_text = end.strftime("%Y-%m-%d %H:%M UTC")
    if start_text == end_text:
        return start_text
    return f"{start_text} to {end_text}"


def build_payload(
    source: CsvSource,
    config: BuildConfig,
    records: list[RowRecord],
    coords: np.ndarray,
    cluster_ids: np.ndarray,
    cluster_labels: dict[int, str],
    axis_labels: dict[str, str] | None = None,
    timeline_kind_value: str | None = None,
) -> dict[str, object]:
    """Build the browser payload consumed by the standalone HTML."""

    trail_columns = list(dict.fromkeys(config.centroid_trails))
    filter_columns = list(dict.fromkeys([*config.filter_columns, "cluster"]))
    color_columns = list(
        dict.fromkeys([*config.color_columns, *[column for column in trail_columns if column != "cluster"], "cluster"])
    )
    sort_columns = ["_row_index", *([config.timeline_column] if config.timeline_column else []), *source.frame.columns.tolist()]
    sort_columns = list(dict.fromkeys(column for column in sort_columns if column))

    rows: list[dict[str, object]] = []
    for idx, record in enumerate(records):
        cluster_id = int(cluster_ids[idx])
        cluster_label = cluster_labels[cluster_id]
        row_payload = {
            "id": int(record.row_index),
            "x": round(float(coords[idx, 0]), 6),
            "y": round(float(coords[idx, 1]), 6),
            "label": record.label,
            "timelineText": record.timeline_text,
            "timelineMs": record.timeline_ms,
            "clusterId": cluster_id,
            "clusterLabel": cluster_label,
            "images": [image.display_url for image in record.images],
            "audios": [audio.display_url for audio in record.audios],
            "imageUrlsByColumn": {
                column: [image.display_url for image in record.images if image.column == column]
                for column in config.image_columns
            },
            "audioUrlsByColumn": {
                column: [audio.display_url for audio in record.audios if audio.column == column]
                for column in config.audio_columns
            },
            "raw": record.raw,
            "tooltip": record.tooltip,
            "colors": {
                **{column: record.raw[column].strip() or "(blank)" for column in config.color_columns},
                "cluster": cluster_label,
            },
            "filters": {
                **{column: record.raw[column].strip() or "(blank)" for column in config.filter_columns},
                "cluster": cluster_label,
            },
        }
        rows.append(row_payload)

    x_values = [row["x"] for row in rows] or [0.0]
    y_values = [row["y"] for row in rows] or [0.0]
    cluster_counts = Counter(int(cluster_id) for cluster_id in cluster_ids.tolist())
    timeline_values = [row["timelineMs"] for row in rows if row["timelineMs"] is not None]
    source_name = Path(source.label).name

    return {
        "title": f"{config.branding} · {source_name}",
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branding": config.branding,
        "sourceName": source_name,
        "opacity": config.opacity,
        "barChartCorner": config.bar_chart_corner,
        "axisLabels": axis_labels or default_axis_labels(),
        "popupStyle": config.popup_style,
        "source": source.label,
        "columns": source.frame.columns.tolist(),
        "imageColumns": config.image_columns,
        "audioColumns": config.audio_columns,
        "colorColumns": color_columns,
        "filterColumns": filter_columns,
        "sortColumns": sort_columns,
        "defaultSort": config.timeline_column or "_row_index",
        "timelineColumn": config.timeline_column,
        "timelineKind": timeline_kind_value if timeline_kind_value is not None else timeline_kind(source.frame, config.timeline_column),
        "timelineMin": min(timeline_values) if timeline_values else None,
        "timelineMax": max(timeline_values) if timeline_values else None,
        "clusters": [
            {"id": cluster_id, "label": cluster_labels[cluster_id], "count": cluster_counts[cluster_id]}
            for cluster_id in sorted(cluster_labels)
        ],
        "rows": rows,
        "xDomain": [round(float(min(x_values)), 6), round(float(max(x_values)), 6)],
        "yDomain": [round(float(min(y_values)), 6), round(float(max(y_values)), 6)],
        "centroidTrails": compute_centroid_trails(
            rows,
            cluster_labels,
            timeline_kind_value,
            trail_columns,
            config.centroid_time_period,
        )
        if trail_columns
        else None,
    }

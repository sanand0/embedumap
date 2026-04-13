"""CLI entry point for embedumap."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.traceback import install

from .core import (
    BuildConfig,
    DEFAULT_CLUSTER_NAMING_MODEL,
    DEFAULT_DIMENSIONS,
    DEFAULT_MODEL,
    analyze_records,
    build_payload,
    dry_run_report,
    load_csv_source,
    parse_centroid_time_period,
    prepare_rows,
    split_option_values,
)
from .html import render_html

install(show_locals=True)
load_dotenv(override=True)

HELP = """Build a standalone HTML UMAP visualization from a CSV using Gemini embeddings."""
app = typer.Typer(add_completion=False, help=HELP)


def normalize_popup_style(value: str) -> str:
    """Validate the popup style eagerly for cleaner CLI errors."""

    style = value.strip().lower()
    if style not in {"table", "grid", "list"}:
        raise typer.BadParameter("Popup style must be one of: table, grid, list")
    return style


def normalize_bar_chart_corner(value: str) -> str:
    """Validate the bar-chart corner eagerly for cleaner CLI errors."""

    corner = value.strip().lower()
    if corner not in {"top-left", "top-right", "bottom-left", "bottom-right"}:
        raise typer.BadParameter("Bar chart corner must be one of: top-left, top-right, bottom-left, bottom-right")
    return corner


@app.command()
def run(
    csv_input: str = typer.Argument(..., help="Local CSV path or HTTP(S) URL."),
    embedding_columns_raw: list[str] = typer.Option([], "--embedding-columns", help="Text columns to embed."),
    image_columns_raw: list[str] = typer.Option([], "--image-columns", help="Image URL/path columns to embed."),
    audio_columns_raw: list[str] = typer.Option([], "--audio-columns", help="Audio URL/path columns to embed."),
    audio_metadata_columns_raw: list[str] = typer.Option(
        [],
        "--audio-metadata-columns",
        help="Optional text columns to include alongside audio embeddings.",
    ),
    color_columns_raw: list[str] = typer.Option([], "--color-columns", help="Columns available for point colors."),
    filter_columns_raw: list[str] = typer.Option([], "--filter-columns", help="Columns exposed as filters."),
    timeline_column: str | None = typer.Option(None, "--timeline-column", help="Timeline column."),
    branding: str = typer.Option("embedumap", "--branding", help="Brand shown at the top left of the page."),
    opacity: float = typer.Option(1.0, "--opacity", min=0.0, max=1.0, help="Base point opacity."),
    bar_chart_corner: str = typer.Option(
        "top-right",
        "--bar-chart-corner",
        help="Corner used for the overlay bar chart.",
    ),
    axis_labels: bool = typer.Option(
        True,
        "--axis-labels/--no-axis-labels",
        help="Ask Gemini to interpret the plotted x/y axes.",
    ),
    cluster_columns_raw: list[str] = typer.Option(
        ["embeddings"],
        "--cluster-columns",
        help='Cluster dimensions. Use "embeddings" for K-means on embeddings.',
    ),
    label_columns_raw: list[str] = typer.Option(
        [],
        "--label-column",
        "--label-columns",
        help="Columns used to build the primary hover label.",
    ),
    popup_style: str = typer.Option("table", "--popup-style", help="Popup layout: table, grid, or list."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Gemini embedding model."),
    cluster_names: bool = typer.Option(False, "--cluster-names", help="Ask Gemini to generate short cluster names."),
    cluster_naming_model: str = typer.Option(
        DEFAULT_CLUSTER_NAMING_MODEL,
        "--cluster-naming-model",
        help="Gemini model used for cluster naming and axis interpretation.",
    ),
    dimensions: int = typer.Option(DEFAULT_DIMENSIONS, "--dimensions", min=128, help="Embedding dimensionality."),
    sample: int | None = typer.Option(None, "--sample", min=1, help="Sample N rows before building."),
    output_path: Path = typer.Option(Path("index.html"), "--output", help="Where to write the HTML output."),
    centroid_trails_raw: list[str] = typer.Option(
        [],
        "--centroid-trails",
        help='Columns to build centroid trails for. Include "cluster" for cluster trails.',
    ),
    centroid_time_period: str | None = typer.Option(
        None,
        "--centroid-time-period",
        help='Optional trail bucket size like "1h", "2h 15min", "daily", "weekly", or "2Q".',
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs without embedding or writing HTML."),
) -> None:
    """Build the map or validate the plan for it."""

    popup_style = normalize_popup_style(popup_style)
    bar_chart_corner = normalize_bar_chart_corner(bar_chart_corner)
    timeline_column = timeline_column.strip() if timeline_column else None
    centroid_trails = split_option_values(centroid_trails_raw)
    centroid_time_period = centroid_time_period.strip() if centroid_time_period else None
    if centroid_trails and not timeline_column:
        raise typer.BadParameter("--centroid-trails requires --timeline-column.")
    if centroid_time_period and not centroid_trails:
        raise typer.BadParameter("--centroid-time-period requires --centroid-trails.")
    try:
        parse_centroid_time_period(centroid_time_period)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    config = BuildConfig(
        csv_input=csv_input,
        output_path=output_path.expanduser().resolve(),
        embedding_columns=split_option_values(embedding_columns_raw),
        image_columns=split_option_values(image_columns_raw),
        audio_columns=split_option_values(audio_columns_raw),
        audio_metadata_columns=split_option_values(audio_metadata_columns_raw),
        color_columns=split_option_values(color_columns_raw),
        filter_columns=split_option_values(filter_columns_raw),
        cluster_columns=split_option_values(cluster_columns_raw) or ["embeddings"],
        label_columns=split_option_values(label_columns_raw),
        timeline_column=timeline_column,
        branding=branding.strip() or "embedumap",
        opacity=opacity,
        bar_chart_corner=bar_chart_corner,
        axis_labels=axis_labels,
        popup_style=popup_style,
        model=model.strip(),
        cluster_naming_model=cluster_naming_model.strip(),
        cluster_names=cluster_names,
        dimensions=dimensions,
        sample=sample,
        dry_run=dry_run,
        centroid_trails=centroid_trails,
        centroid_time_period=centroid_time_period,
    )
    if not config.embedding_columns and not config.image_columns and not config.audio_columns:
        raise typer.BadParameter(
            "At least one of --embedding-columns, --image-columns, or --audio-columns is required."
        )

    source = load_csv_source(config.csv_input)
    records, report = prepare_rows(source, config)
    if not records:
        raise typer.BadParameter("No usable rows remain after validation.")
    if config.dry_run:
        dry_run_report(source, config, records, report)
        return

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    coords, cluster_ids, cluster_labels, axis_labels_map = analyze_records(source, records, config)
    payload = build_payload(
        source,
        config,
        records,
        coords,
        cluster_ids,
        cluster_labels,
        axis_labels=axis_labels_map,
        timeline_kind_value=report.get("timeline_kind"),
    )
    config.output_path.write_text(render_html(payload), encoding="utf-8")
    typer.echo(f"Wrote {config.output_path}")


def main() -> None:
    """Console-script entry point."""

    app()


if __name__ == "__main__":
    main()

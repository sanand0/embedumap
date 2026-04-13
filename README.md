# embedumap

`embedumap` builds a standalone `index.html` scatterplot from a CSV using Gemini embeddings, UMAP, and clustering.

## Install / run

```bash
uvx --from "git+https://github.com/sanand0/embedumap.git@main" embedumap ...
```

## Examples

Dry run:

```bash
uv run embedumap samples/blog-text.csv \
  --embedding-columns text \
  --color-columns primary_category,year \
  --filter-columns primary_category,year \
  --timeline-column year \
  --dry-run
```

Build a text map:

```bash
uv run embedumap samples/blog-text.csv \
  --embedding-columns text \
  --color-columns primary_category,year \
  --filter-columns primary_category,year \
  --timeline-column year
```

Build a text map with short LLM cluster names:

```bash
uv run embedumap samples/blog-text.csv \
  --embedding-columns text \
  --color-columns primary_category,year \
  --filter-columns primary_category,year \
  --timeline-column year \
  --branding "My map" \
  --opacity 0.7 \
  --bar-chart-corner bottom-left \
  --cluster-names
```

Build a text map without LLM-interpreted axis labels:

```bash
uv run embedumap samples/blog-text.csv \
  --embedding-columns text \
  --color-columns primary_category,year \
  --filter-columns primary_category,year \
  --timeline-column year \
  --no-axis-labels
```

Build an image-first map:

```bash
uv run embedumap samples/calvin-images.csv \
  --image-columns file \
  --timeline-column date \
  --popup-style grid
```

Build centroid trails for selected columns:

```bash
uv run embedumap samples/blog-text.csv \
  --embedding-columns text \
  --color-columns primary_category \
  --filter-columns primary_category,year \
  --timeline-column year \
  --centroid-trails primary_category,cluster
```

Build centroid trails with a custom time bucket:

```bash
uv run embedumap samples/mixed-media.csv \
  --image-columns file \
  --color-columns theme \
  --filter-columns theme,person,place \
  --timeline-column date \
  --centroid-trails theme,cluster \
  --centroid-time-period fortnightly
```

Build an audio-first map:

```bash
uv run embedumap /path/to/audio.csv \
  --audio-columns clip \
  --audio-metadata-columns title,speaker \
  --filter-columns speaker \
  --popup-style list
```

No-clone public smoke test:

```bash
uvx --from "git+https://github.com/sanand0/embedumap.git@main" embedumap https://raw.githubusercontent.com/sanand0/embedumap/main/samples/blog-text-300.csv --embedding-columns text --color-columns primary_category,year --filter-columns primary_category,year --timeline-column year
```

## Notes

- Put `GEMINI_API_KEY` in `.env` or the environment.
- The generated HTML embeds data inline and uses direct image/audio references when media columns are provided.
- `--branding` controls the top-left page label, and `--opacity` sets the base point opacity.
- `--bar-chart-corner` moves the overlay bar chart between `top-left`, `top-right`, `bottom-left`, and `bottom-right`.
- Axis labels are interpreted by Gemini by default using `--cluster-naming-model`; use `--no-axis-labels` to keep `UMAP 1` and `UMAP 2`.
- Embeddings are cached by default in `embedumap.duckdb` next to the output HTML.
- `--cluster-names` adds a lightweight Gemini naming pass after deterministic clustering.
- `--centroid-trails` takes one or more column names, for example `--centroid-trails primary_category,cluster`. Include `cluster` explicitly when you want cluster trails.
- `--centroid-time-period` overrides the default bucket size used for centroid trails. Examples: `1h`, `2.5h`, `2h 15min`, `3d`, `daily`, `weekly`, `30d`, `2Q`, `fortnightly`.
- If `--centroid-time-period` is omitted, centroid trails default to yearly buckets for year timelines, daily buckets for date timelines, and monthly buckets for datetime timelines.
- Requested centroid trail columns are added to the available color dimensions so you can switch trail views in the UI.
- Trail nodes are only created for time buckets with at least 2 points, and a trail is only drawn when a group has at least 2 such buckets.
- The pipeline still stays intentionally small: no thumbnails, no sidecar JSON, no transcription pipeline.

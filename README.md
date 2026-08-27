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
  --max-image-size 768 \
  --timeline-column date \
  --popup-style grid
```

Build trails from time-bucket centroids:

```bash
uv run embedumap samples/blog-text.csv \
  --embedding-columns text \
  --color-columns primary_category \
  --filter-columns primary_category,year \
  --timeline-column year \
  --trails
```

Build trails for selected grouping columns with a custom bucket size:

```bash
uv run embedumap samples/blog-text.csv \
  --embedding-columns text \
  --color-columns primary_category \
  --filter-columns primary_category,year \
  --timeline-column year \
  --trails primary_category \
  --trail-period yearly
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
- `--branding` controls the top-left page label, `--opacity` sets active point opacity, `--inactive-opacity` sets point opacity outside filters or timeline range, and `--trail-opacity` sets trail opacity.
- `--bar-chart-corner` moves the overlay bar chart between `top-left`, `top-right`, `bottom-left`, and `bottom-right`.
- Axis labels are interpreted by Gemini by default using `--cluster-naming-model`; use `--no-axis-labels` to keep `UMAP 1` and `UMAP 2`.
- `--max-image-size N` resizes embedded image payloads to fit inside an `N` by `N` tile without changing aspect ratio. There is no default resize; use `768` to match the Gemini embedding models' tile size.
- Embeddings are cached by default in `embedumap.duckdb` next to the output HTML.
- `--batch-size N` controls how many rows are sent per embedding request. Increase it to speed up builds when your Gemini quota allows larger batches.
- `--cluster-names` adds a lightweight Gemini naming pass after deterministic clustering.
- `--trails` draws paths through time-bucket centroids. With no value it draws cluster trails; with values like `--trails primary_category,cluster`, it also draws those group trails.
- `--trail-period` overrides the automatic bucket size. Examples: `1min`, `1h`, `2h 15min`, `daily`, `weekly`, `2Q`, `yearly`.
- Trail playback uses a play button, cumulative toggle, logarithmic speed slider, and inactive opacity slider for dimmed nodes and trails. Trails start off in the UI; timeline range, trail visibility, playback mode, speed, and inactive opacity are shareable in the URL.
- The pipeline still stays intentionally small: no thumbnails, no sidecar JSON, no transcription pipeline.

## Embedding cache

Embeddings are cached by default in `embedumap.duckdb` next to the generated HTML output. Each row cache key is a SHA-256 hash of stable JSON containing:

- the cache version,
- the source label,
- the row index,
- a content hash of the normalized text payload, audio metadata text, image signatures, and audio signatures,
- the embedding model,
- the embedding dimensions,
- and `--max-image-size` when the row includes images.

To regenerate an HTML file using existing embeddings, rerun with the same embedding inputs, model, dimensions, and image resize setting. For text/audio-only rows, existing cache entries are also reused by content across source paths or row positions; image rows retain exact cache-key matching because resize settings affect their embeddings. Visualization-only changes such as colors, filters, timeline controls, trails, opacity, branding, and popup options reuse cached embeddings. If you write the HTML to a different directory, move or copy the existing `embedumap.duckdb` beside the new output file before rerunning.

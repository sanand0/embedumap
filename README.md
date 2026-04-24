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
- `--max-image-size N` resizes embedded image payloads to fit inside an `N` by `N` tile without changing aspect ratio. There is no default resize; use `768` to match the Gemini embedding models' tile size.
- Embeddings are cached by default in `embedumap.duckdb` next to the output HTML.
- `--cluster-names` adds a lightweight Gemini naming pass after deterministic clustering.
- The pipeline still stays intentionally small: no thumbnails, no sidecar JSON, no transcription pipeline.

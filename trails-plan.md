# Trails and Playback Integration Plan

## Goal

Incorporate the fork's centroid trails feature plus improved timeline speed/playback controls into this repo, but do not port the fork wholesale. The implementation should preserve the current standalone-HTML model, keep the CLI small, and make the new controls understandable without adding dataset-specific behavior.

## Fork Review

Reviewed branches from `https://github.com/ritesh17rb/embedumap`:

- `ritesh17rb/feature-clean` is the best source branch for the intended feature work. It adds `--centroid-trails`, `--centroid-time-period`, centroid trail payload generation, renderer controls, and tests.
- `ritesh17rb/main` includes the same feature family plus generated/demo artifacts (`index.html`, `REPORT.md`, patent-specific `.gitignore` entries) and a hard-coded patent page switcher. Do not port those artifacts.
- `feature-clean` tests pass: `8 passed`. Ruff passes on `feature-clean`.
- `main` tests pass, but Ruff fails on an unused `rows_to_store` variable in `src/embedumap/core.py`.

The fork's implementation works at a basic level, but it mixes general product behavior with demo-specific behavior and puts too much feature logic directly into the monolithic HTML template.

## How The Fork Works

CLI and config:

- Adds `centroid_trails` and `centroid_time_period` to `BuildConfig`.
- Adds `--centroid-trails` as comma/repeated column names. `cluster` is treated as a special group.
- Adds `--centroid-time-period` with aliases and pandas-style durations such as `hourly`, `daily`, `weekly`, `fortnightly`, `2h 15min`, and `2Q`.
- Requires `--timeline-column` when trails are requested.

Payload generation:

- Existing rows already include `timelineMs`, `timelineText`, coordinates, cluster ids, raw fields, colors, and filters.
- Trails are generated after rows are built by grouping rows by trail column and time bucket.
- Each trail point stores bucket bounds, label, centroid `x/y`, count, and spread (`std`).
- Buckets with fewer than 2 rows are skipped, and a trail must have at least 2 retained buckets.
- Requested trail columns are added to `colorColumns`, so the renderer can switch trail families by switching the active color dimension.

Renderer:

- Draws scatter points and centroid trails on the same canvas.
- Supports three trail display modes: trails + nodes, trails only, nodes only.
- Uses the existing bar chart as an implicit trail highlighter when the active color dimension has matching trails.
- Adds playback modes: `Slide` moves a fixed window; `Reveal` keeps the left edge fixed and advances the right edge.
- Adds a speed slider from `0.25x` to `4x`.
- URL state stores color, filters, timeline range, sort direction, and trail display mode, but not playback mode or speed.

## UX Changes I Would Make

1. Replace the single cycling `Trails + Nodes / Trails Only / Nodes Only` button with explicit controls.

   A cycling button hides available states and makes it easy to miss that "nodes only" is not the same as turning trails off. I would use a compact segmented control with `Off`, `Lines`, `Nodes`, and `Lines + Nodes`. Default should be `Lines + Nodes` only when trails were explicitly requested and generated; otherwise the control is hidden.

2. Add an explicit trail dimension selector when more than one trail family exists.

   The fork ties trails to the active color dimension. That is clever, but surprising: changing point color also changes which trails are drawn. I would keep color and trail grouping related but not inseparable:

   - Default trail grouping can follow the active color dimension when possible.
   - A visible `Trail` selector should allow `cluster`, each requested trail column, and `none`.
   - Changing color should not silently discard a user's chosen trail grouping unless it is still in "follow color" mode.

3. Make trail highlighting discoverable.

   Clicking bar chart rows to highlight trails is useful but hidden. I would add hover affordance/cursor on bar rows only when they can highlight a trail, keep selected row styling in the bar chart, and add a small clear state. The renderer state should call this `highlightTrailId`, not `highlightTrailCluster`, since trails may be grouped by non-cluster columns.

4. Improve timeline playback control labels.

   `Slide` and `Reveal` are compact but ambiguous. I would label them as `Moving window` and `Cumulative reveal`, while keeping internal ids as `slide` and `reveal`. The current labels can still appear in docs if we prefer shorter UI text.

5. Replace the free speed slider with predictable presets or a stepped segmented control.

   The current `0.25x` to `4x` range works, but a narrow slider is hard to set precisely. I would use presets: `0.5x`, `1x`, `2x`, `4x`. If we keep a slider, it should have tick labels and an accessible label.

6. Add pause/reset behavior for manual timeline edits.

   If the user drags either timeline handle, drags the filled range, changes playback mode, or changes trail grouping while playing, playback should pause. This keeps state changes predictable.

7. Add a replay/reset button only if needed.

   The fork restarts playback from the beginning when the window is at the end. That behavior is reasonable but implicit. I would consider a small reset-to-start control, or at minimum make Play from end consistently restart for both playback modes.

8. Improve trail rendering legibility.

   The fork uses count for node radius and spread for blur. That is useful but visually dense. I would keep count-scaled nodes, but make spread optional or subtler, and draw time labels only for the highlighted trail endpoints. Tooltips should show group, period, count, and spread in plain labels.

9. Avoid disabling too many base interactions in trail modes.

   `trails only` currently disables scatter hit-testing and clears selections. That may be correct, but users may still expect to select underlying points while trails are visible. I would treat `Off/Lines/Nodes/Lines + Nodes` as visual layers first, and only disable point selection in an explicit "trails only" state if we keep that state.

10. Keep generated maps responsive.

   The existing top control bar is already crowded. I would place trail controls near color/filter controls but keep timeline playback controls in the bottom timeline bar. On mobile, controls should wrap without pushing the plot into a tiny strip.

## Code Quality Changes I Would Make

1. Port the data model deliberately, not as a direct diff.

   Keep `BuildConfig` additions and payload additions, but separate trail-specific code into a focused section or module-level helpers with typed return shapes. The fork's algorithm is useful; the names and boundaries need cleanup.

2. Rename feature concepts consistently.

   Use `trail_columns`, `trail_time_period`, `trail_groups`, `trail_points`, and `highlightTrailId`. The CLI can expose `--centroid-trails` if we want that user-facing term, but internals should not mix centroid, cluster, and trail terminology casually.

3. Keep domain-specific artifacts out.

   Do not port `REPORT.md`, generated `index.html`, patent `.gitignore` entries, `PAGE_VARIANTS`, or person-specific comments. The generated renderer must not know about patent filenames.

4. Add validation and reporting that explain when no trails are generated.

   If a user requests trails and all groups are filtered out by bucket-size rules, the build should report that clearly in dry-run and/or console output. The payload can carry empty trails, but the UI should avoid showing dead controls.

5. Make time bucketing behavior explicit.

   The fork defaults to yearly buckets for `year`, daily buckets for `date`, and monthly buckets for `datetime`. That default is defensible, but it should be documented and covered by tests. Custom period parsing should reject ambiguous or zero/negative values with CLI-friendly errors.

6. Add stronger unit tests around trail generation.

   Keep the fork's tests, then add cases for:

   - Missing/unparseable timeline values.
   - Blank grouping values.
   - Multiple requested trail columns with duplicate input.
   - Custom calendar periods versus fixed durations.
   - Trail columns not present in color/filter columns.
   - No generated trails because every bucket has fewer than 2 points.

7. Add focused renderer smoke tests.

   The current tests only check that strings are present in HTML. Add payload-level render smoke tests for the new controls, and use a browser smoke test before merging to verify:

   - Trails render.
   - Trail mode changes do not break scatter selection.
   - Bar chart highlighting works.
   - Playback starts, pauses, restarts, and respects speed.
   - URL state round-trips.

8. Reduce global JavaScript sprawl where practical.

   The HTML template is already large. I would keep this as one standalone file for now, but group renderer functions by responsibility and avoid adding unrelated globals. Trail state, timeline playback, and canvas drawing should have clear helper boundaries.

9. Reuse existing URL state patterns carefully.

   Persist trail mode and selected trail grouping. Consider whether playback mode and speed should be URL state; my default is no for speed, yes for trail grouping and trail display mode.

10. Preserve current behavior for users who do not request trails.

   No new UI should appear, no payload bloat beyond `centroidTrails: null`, no changes to non-trail point selection, filtering, sorting, or existing timeline playback semantics except the requested speed/playback controls.

## Proposed Implementation Steps

1. Add config and CLI support.

   Add `centroid_trails` and `centroid_time_period` to `BuildConfig`; add `--centroid-trails` and `--centroid-time-period`; validate dependencies and period syntax early.

2. Add trail computation helpers.

   Implement period parsing, default bucket selection, bucket labels/bounds, group extraction, and centroid/spread computation. Return a compact payload keyed by trail column.

3. Extend payload generation.

   Include `centroidTrails` only when requested. Add requested trail columns to color dimensions only if we decide to keep "follow color" behavior; otherwise include a separate `trailColumns` payload field.

4. Redesign renderer state.

   Add state for `trailMode`, `trailBy`, `highlightTrailId`, `playbackMode`, and `playSpeed`. Keep defaults stable and ensure no-trail payloads behave exactly as today.

5. Build explicit trail controls.

   Add an explicit trail mode segmented control and trail grouping selector. Hide the controls when there are no generated trails. Keep bar chart highlighting as an enhancement, not the only control path.

6. Add playback mode and speed controls.

   Extend the current timeline playback code with moving-window/cumulative modes and speed presets. Pause playback on manual timeline edits and state changes.

7. Draw trails and hit-test trail nodes.

   Draw trails after points or between dimmed and active point passes, based on visual testing. Build a separate trail-dot hit list for tooltips. Keep selected point behavior intact unless the user chooses a true trails-only display.

8. Update docs and tests.

   Add README examples and notes, unit tests for the trail helpers and payload, and renderer smoke tests. Run `uv run pytest -q` and `uvx ruff check .`.

9. Browser-verify generated HTML.

   Use a small deterministic payload or sample output to verify desktop and mobile layout, control wrapping, trail rendering, tooltips, playback, and URL state.

## Questions Before Coding

1. Should the user-facing CLI flag remain `--centroid-trails`, or would you prefer a shorter name like `--trails` with docs explaining that the visual path is made from time-bucket centroids?

2. Should trails default to `cluster` when `--centroid-trails` is provided without values, or should the user always name the grouping columns explicitly?

3. Should trail grouping follow the active color dimension by default, or should color and trails be fully independent controls?

4. Should `cluster` trails be included automatically whenever trails are requested, or only when the user explicitly includes `cluster`?

5. Are the fork's bucket defaults acceptable: yearly for year timelines, daily for date timelines, and monthly for datetime timelines?

6. Should buckets with only one row be skipped, as in the fork, or shown with a different visual treatment?

7. Is the spread metric useful in the UI, or should we keep it in the payload/tooltips only and avoid using blur as a visual encoding?

8. Should playback mode be persisted in the URL? My default is to persist trail grouping/mode and timeline range, but not speed.

9. Should there be a true `Off` mode for trails, or is `Nodes only` enough?

10. Do you want the compact top-control layout from the fork's `main` branch considered as part of this work, or should this pass be limited to trails and timeline playback only?

## Non-Goals

- Do not port generated demo HTML or report artifacts.
- Do not add dataset-specific page switchers.
- Do not change embedding, UMAP, clustering, cluster naming, or axis labeling behavior.
- Do not start implementation until the questions above are answered.

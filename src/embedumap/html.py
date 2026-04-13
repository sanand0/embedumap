"""Standalone HTML renderer for embedumap."""

from __future__ import annotations

import json

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #0b1220;
    --bg-panel: rgba(15, 23, 42, 0.9);
    --bg-panel-strong: rgba(15, 23, 42, 0.96);
    --bg-chip: rgba(255, 255, 255, 0.04);
    --stroke: rgba(148, 163, 184, 0.22);
    --stroke-strong: rgba(148, 163, 184, 0.42);
    --text: #e2e8f0;
    --text-dim: #94a3b8;
    --text-faint: #64748b;
    --accent: #60a5fa;
    --accent-strong: #3b82f6;
    --shadow: 0 24px 80px rgba(0, 0, 0, 0.48);
    --radius: 14px;
  }

  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    min-height: 100%;
    overflow: hidden;
    color-scheme: dark;
    background:
      radial-gradient(circle at top left, rgba(96, 165, 250, 0.14), transparent 28%),
      radial-gradient(circle at 82% 16%, rgba(244, 114, 182, 0.1), transparent 22%),
      linear-gradient(180deg, #111827 0%, #0b1220 62%, #09101a 100%);
    color: var(--text);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: 0.18;
    background-image:
      radial-gradient(circle at 1px 1px, rgba(255, 255, 255, 0.08) 1px, transparent 0);
    background-size: 18px 18px;
    mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.68), transparent 88%);
  }

  button, select, input { font: inherit; }

  #app {
    position: relative;
    display: grid;
    grid-template-rows: auto 1fr auto;
    height: 100dvh;
  }

  #controls, #timeline-bar {
    position: relative;
    z-index: 3;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    padding: 10px 14px;
    background: var(--bg-panel);
    border-bottom: 1px solid var(--stroke);
    backdrop-filter: blur(22px);
  }

  #timeline-bar {
    display: none;
    border-top: 1px solid var(--stroke);
    border-bottom: none;
  }

  #timeline-bar.visible { display: flex; }

  #brand {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-right: 10px;
  }

  #brand-title {
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    color: var(--text);
  }

  #brand-subtitle {
    color: var(--text-faint);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  .label {
    color: var(--text-faint);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    white-space: nowrap;
  }

  .button-group {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .button-group button,
  select,
  .toolbar button,
  #timeline-play,
  .popup-close {
    color: var(--text);
    background: var(--bg-chip);
    border: 1px solid var(--stroke);
    border-radius: 999px;
    padding: 6px 12px;
    cursor: pointer;
    transition: background 140ms ease, border-color 140ms ease, color 140ms ease, transform 140ms ease;
  }

  .button-group button:hover,
  select:hover,
  .toolbar button:hover,
  #timeline-play:hover,
  .popup-close:hover {
    border-color: var(--stroke-strong);
    background: rgba(255, 255, 255, 0.08);
  }

  .button-group button.active {
    color: #eff6ff;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
    border-color: transparent;
  }

  #plot-wrap {
    position: relative;
    overflow: hidden;
    min-height: 0;
    isolation: isolate;
  }

  #plot,
  #overlay {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }

  #overlay {
    z-index: 1;
    cursor: crosshair;
    touch-action: none;
  }

  .selection-box {
    fill: rgba(96, 165, 250, 0.14);
    stroke: rgba(96, 165, 250, 0.85);
    stroke-width: 1.4px;
    pointer-events: none;
  }

  select:focus-visible,
  button:focus-visible,
  input:focus-visible {
    outline: 2px solid rgba(96, 165, 250, 0.55);
    outline-offset: 2px;
  }

  option,
  optgroup {
    color: var(--text);
    background: #111827;
  }

  option:checked {
    background: #1d4ed8;
    color: #eff6ff;
  }

  #loading {
    position: absolute;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    background: radial-gradient(circle at center, rgba(11, 18, 32, 0.76), rgba(11, 18, 32, 0.94));
    backdrop-filter: blur(18px);
    transition: opacity 220ms ease;
  }

  #loading.hidden {
    opacity: 0;
    pointer-events: none;
  }

  .loading-card {
    display: grid;
    justify-items: center;
    gap: 10px;
    padding: 22px 26px;
    min-width: min(340px, 88vw);
    background: var(--bg-panel-strong);
    border: 1px solid var(--stroke);
    border-radius: 18px;
    box-shadow: var(--shadow);
    text-align: center;
  }

  .loading-spinner {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    border: 2px solid rgba(148, 163, 184, 0.22);
    border-top-color: var(--accent);
    animation: spin 900ms linear infinite;
  }

  .loading-title {
    font-size: 1rem;
    font-weight: 700;
  }

  .loading-copy {
    color: var(--text-dim);
    font-size: 0.84rem;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  #tooltip {
    position: fixed;
    pointer-events: none;
    z-index: 1000;
    display: none;
    max-width: min(360px, 90vw);
    max-height: min(520px, 80vh);
    overflow: auto;
    padding: 10px;
    border: 1px solid var(--stroke);
    border-radius: 10px;
    background: rgba(15, 23, 42, 0.98);
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
  }

  #tooltip img {
    width: 100%;
    max-height: 260px;
    object-fit: contain;
    border-radius: 8px;
    background: #020617;
    margin-bottom: 8px;
  }

  #tooltip audio,
  .popup-audio-list audio,
  .card-audios audio {
    width: 100%;
  }

  .tooltip-label {
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 8px;
  }

  .tooltip-grid {
    display: grid;
    grid-template-columns: minmax(84px, auto) 1fr;
    gap: 6px 10px;
    font-size: 12px;
  }

  .tooltip-key,
  .field-key { color: #93c5fd; }

  .tooltip-value,
  .field-value {
    color: var(--text);
    word-break: break-word;
  }

  #popup-backdrop {
    position: fixed;
    inset: 0;
    z-index: 180;
    display: none;
    background: rgba(2, 6, 23, 0.7);
    backdrop-filter: blur(8px);
  }

  #popup {
    position: fixed;
    inset: 5vh 4vw;
    z-index: 200;
    display: none;
    grid-template-rows: auto auto 1fr;
    background: var(--bg-panel-strong);
    border: 1px solid var(--stroke);
    border-radius: 18px;
    overflow: hidden;
    box-shadow: var(--shadow);
  }

  #popup.visible,
  #popup-backdrop.visible { display: block; }

  #popup.visible { display: grid; }

  .popup-head,
  .toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 12px 14px;
    border-bottom: 1px solid var(--stroke);
  }

  .popup-head { justify-content: space-between; }

  .popup-title {
    font-size: 15px;
    font-weight: 700;
  }

  .popup-close {
    width: 38px;
    height: 38px;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
  }

  .spacer { margin-left: auto; }

  #popup-body {
    overflow: auto;
    padding: 14px;
  }

  .popup-table {
    width: 100%;
    border-collapse: collapse;
  }

  .popup-table th,
  .popup-table td {
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    padding: 8px 10px;
    text-align: left;
    vertical-align: top;
    font-size: 12px;
  }

  .popup-table th {
    position: sticky;
    top: 0;
    color: #bfdbfe;
    background: rgba(9, 16, 26, 0.96);
  }

  .popup-table th[data-sort] {
    cursor: pointer;
    user-select: none;
  }

  .popup-table th.sorted { color: #eff6ff; }

  .popup-image-list {
    display: grid;
    gap: 8px;
  }

  .popup-image-list img,
  .card-images img {
    width: 100%;
    max-height: 360px;
    object-fit: contain;
    border-radius: 10px;
    background: #020617;
  }

  .card-list {
    display: grid;
    gap: 14px;
  }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 14px;
  }

  .card {
    border: 1px solid rgba(148, 163, 184, 0.12);
    border-radius: 14px;
    background: rgba(11, 18, 32, 0.84);
    padding: 12px;
    display: grid;
    gap: 10px;
  }

  .card-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }

  .card-title {
    font-size: 13px;
    font-weight: 700;
  }

  .card-subtitle {
    color: var(--text-dim);
    font-size: 12px;
  }

  .card-fields {
    display: grid;
    grid-template-columns: minmax(84px, auto) 1fr;
    gap: 6px 10px;
    font-size: 12px;
  }

  #status-stack {
    margin-left: auto;
    display: grid;
    gap: 4px;
    justify-items: end;
  }

  #summary {
    color: var(--text-dim);
    text-align: right;
  }

  #axis-legend {
    display: grid;
    gap: 2px;
    justify-items: end;
  }

  .axis-row {
    display: flex;
    gap: 8px;
    align-items: baseline;
    max-width: min(520px, 50vw);
    font-size: 0.76rem;
    color: var(--text-dim);
  }

  .axis-tag {
    color: var(--text-faint);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    white-space: nowrap;
  }

  .axis-text {
    color: var(--text);
    text-align: right;
    text-wrap: balance;
  }

  #bar-chart {
    position: absolute;
    z-index: 2;
    width: min(340px, calc(100% - 28px));
    display: grid;
    gap: 6px;
    padding: 0;
    pointer-events: none;
    background: transparent;
  }

  #bar-chart.hidden { display: none; }

  #bar-chart[data-corner="top-left"] {
    top: 16px;
    left: 16px;
  }

  #bar-chart[data-corner="top-right"] {
    top: 16px;
    right: 16px;
  }

  #bar-chart[data-corner="bottom-left"] {
    bottom: 16px;
    left: 16px;
  }

  #bar-chart[data-corner="bottom-right"] {
    right: 16px;
    bottom: 16px;
  }

  .bar-chart-head {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: baseline;
    color: var(--text-dim);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    opacity: 1;
    text-shadow: 0 1px 12px rgba(2, 6, 23, 0.9);
  }

  .bar-chart-body {
    display: grid;
    gap: 5px;
  }

  .bar-chart-body .label {
    opacity: 1;
    text-shadow: 0 1px 12px rgba(2, 6, 23, 0.9);
  }

  .bar-row {
    display: flex;
    gap: 8px;
    align-items: center;
    transition: opacity 180ms ease, transform 180ms ease;
  }

  .bar-label,
  .bar-count {
    font-size: 12px;
    color: var(--text);
    opacity: 1;
    text-shadow: 0 1px 12px rgba(2, 6, 23, 0.9);
  }

  .bar-label {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bar-count {
    flex: 0 0 auto;
    min-width: 3ch;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  .bar-track {
    flex: 0 0 132px;
    width: 132px;
    height: 10px;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.12);
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    min-width: 2px;
    opacity: 0.8;
    border-radius: 999px;
    transition: width 180ms linear, background 180ms linear;
  }

  #timeline-wrap {
    display: none;
    align-items: center;
    gap: 10px;
    flex: 1;
    flex-wrap: wrap;
    min-width: min(720px, 100%);
  }

  #timeline-wrap.visible { display: flex; }

  #timeline-tools {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .timeline-label {
    color: var(--text-dim);
    font-size: 0.84rem;
    white-space: nowrap;
    min-width: 84px;
  }

  #timeline-end { text-align: right; }

  #timeline-play.playing {
    background: rgba(239, 68, 68, 0.16);
    border-color: rgba(239, 68, 68, 0.4);
  }

  #timeline-speed-wrap {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  #timeline-speed {
    width: 110px;
    accent-color: var(--accent);
  }

  #timeline-speed-value {
    min-width: 3.5ch;
    color: var(--text-dim);
    font-size: 0.78rem;
    text-align: right;
  }

  .range-block {
    position: relative;
    display: flex;
    align-items: center;
    flex: 1;
    height: 28px;
  }

  .range-block input[type=range] {
    position: absolute;
    inset: 0;
    width: 100%;
    background: transparent;
    pointer-events: none;
    appearance: none;
  }

  .range-block input[type=range]::-webkit-slider-thumb {
    appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent);
    border: 2px solid #0f172a;
    pointer-events: all;
    cursor: pointer;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
  }

  .range-block input[type=range]::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent);
    border: 2px solid #0f172a;
    pointer-events: all;
    cursor: pointer;
  }

  .timeline-line {
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 4px;
    transform: translateY(-50%);
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.16);
  }

  .timeline-fill {
    position: absolute;
    top: 50%;
    height: 4px;
    transform: translateY(-50%);
    border-radius: 999px;
    background: linear-gradient(90deg, var(--accent) 0%, var(--accent-strong) 100%);
    cursor: grab;
    touch-action: none;
    padding-block: 10px;
    box-sizing: content-box;
    background-clip: content-box;
  }

  .timeline-duration {
    position: absolute;
    top: -18px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 11px;
    color: var(--text-dim);
    white-space: nowrap;
    pointer-events: none;
    background: rgba(15, 23, 42, 0.85);
    padding: 1px 7px;
    border-radius: 999px;
  }

  @media (max-width: 900px) {
    #status-stack,
    #axis-legend {
      justify-items: start;
    }

    #summary {
      text-align: left;
    }

    .axis-row {
      max-width: 100%;
    }

    .axis-text {
      text-align: left;
    }

    #timeline-wrap {
      min-width: 100%;
    }

    .timeline-label {
      min-width: 70px;
      font-size: 0.75rem;
    }
  }
</style>
</head>
<body>
<div id="app">
  <div id="controls">
    <div id="brand">
      <div id="brand-title"></div>
      <div id="brand-subtitle"></div>
    </div>
    <span class="label">Color</span>
    <div id="color-group" class="button-group"></div>
    <span class="label">Filter</span>
    <div id="filter-group" class="button-group"></div>
    <div id="trails-group" class="button-group" style="display:none">
      <button id="trails-toggle">Trails</button>
    </div>
    <div id="page-switch-group" class="button-group" style="display:none"></div>
    <div id="status-stack">
      <div id="summary" class="label"></div>
      <div id="axis-legend" aria-label="Projection axes">
        <div class="axis-row"><span class="axis-tag">X</span><span id="axis-x-label" class="axis-text"></span></div>
        <div class="axis-row"><span class="axis-tag">Y</span><span id="axis-y-label" class="axis-text"></span></div>
      </div>
    </div>
  </div>
  <div id="plot-wrap">
    <div id="loading">
      <div class="loading-card">
        <div class="loading-spinner"></div>
        <div class="loading-title" id="loading-title">Loading map…</div>
        <div class="loading-copy" id="loading-copy">Parsing embedded dataset and preparing the view.</div>
      </div>
    </div>
    <canvas id="plot"></canvas>
    <svg id="overlay"></svg>
    <div id="bar-chart" data-corner="top-right">
      <div id="bar-chart-head" class="bar-chart-head"></div>
      <div id="bar-chart-body" class="bar-chart-body"></div>
    </div>
  </div>
  <div id="timeline-bar">
    <div id="timeline-wrap">
      <div id="timeline-tools">
        <button id="timeline-play" type="button">&#9654; Play</button>
        <span class="label">Playback</span>
        <div id="timeline-mode-group" class="button-group"></div>
        <label id="timeline-speed-wrap" for="timeline-speed">
          <span class="label">Speed</span>
          <input id="timeline-speed" type="range" min="25" max="400" step="25" value="100">
          <span id="timeline-speed-value"></span>
        </label>
      </div>
      <span id="timeline-start" class="timeline-label"></span>
      <div class="range-block" id="timeline-range">
        <div class="timeline-line"></div>
        <div id="timeline-fill" class="timeline-fill"></div>
        <div id="timeline-duration" class="timeline-duration"></div>
        <input id="timeline-min" type="range">
        <input id="timeline-max" type="range">
      </div>
      <span id="timeline-end" class="timeline-label"></span>
    </div>
  </div>
</div>
<div id="tooltip"></div>
<div id="popup-backdrop"></div>
<div id="popup">
  <div class="popup-head">
    <div class="popup-title" id="popup-title"></div>
    <button class="popup-close" id="popup-close" type="button" aria-label="Close popup">✕</button>
  </div>
  <div class="toolbar">
    <span class="label">Sort</span>
    <select id="sort-column"></select>
    <button id="sort-direction" type="button">Ascending</button>
    <span class="label">Popup</span>
    <span id="popup-style-label"></span>
  </div>
  <div id="popup-body"></div>
</div>
<script id="data-json" type="application/json">__DATA__</script>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
let DATA = null;
let state = null;

const $ = (selector, element = document) => element.querySelector(selector);
const PALETTE = [
  "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7",
  "#9c755f","#8dd3c7","#17becf","#aec7e8","#ffbb78","#98df8a","#ff9896","#c5b0d5",
  "#c49c94","#f7b6d2","#bcbd22","#637939","#9edae5","#5254a3","#ce6dbd","#843c39"
];
const margin = { top: 18, right: 18, bottom: 18, left: 18 };
const pointRadius = 4;
const sliderMax = 10000;
const playDurationMs = 12000;
const defaultPlaySpeed = 100;
const PLAYBACK_MODES = [
  { id: "slide", label: "Slide" },
  { id: "reveal", label: "Reveal" },
];

const plot = $("#plot");
const overlay = d3.select("#overlay");
const overlayNode = overlay.node();
const tooltip = $("#tooltip");
const popup = $("#popup");
const popupBackdrop = $("#popup-backdrop");
const popupBody = $("#popup-body");
const popupTitle = $("#popup-title");
const popupStyleLabel = $("#popup-style-label");
const summary = $("#summary");
const axisXLabel = $("#axis-x-label");
const axisYLabel = $("#axis-y-label");
const barChart = $("#bar-chart");
const barChartHead = $("#bar-chart-head");
const barChartBody = d3.select("#bar-chart-body");
const loading = $("#loading");
const loadingTitle = $("#loading-title");
const loadingCopy = $("#loading-copy");
const selectionBox = overlay.append("rect").attr("class", "selection-box").style("display", "none");

let width = 0;
let height = 0;
let dpr = window.devicePixelRatio || 1;
let xScale = d3.scaleLinear();
let yScale = d3.scaleLinear();
let baseXScale = d3.scaleLinear();
let baseYScale = d3.scaleLinear();
let xDomain = [0, 1];
let yDomain = [0, 1];
let quadtree = null;
let dragState = null;
let playRaf = 0;
let playPrev = null;
let zoomTransform = d3.zoomIdentity;

const TIMELINE_FORMATTERS = {
  year: new Intl.DateTimeFormat(undefined, { year: "numeric", timeZone: "UTC" }),
  date: new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }),
  datetime: new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  }),
};
const STATE_DATE = d3.utcFormat("%Y-%m-%d");
const STATE_DATE_TIME = d3.utcFormat("%Y-%m-%dT%H:%M:%SZ");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function displaySortLabel(column) {
  if (column === "_row_index") return "Row order";
  return column;
}

function formatTimeline(ms) {
  if (ms == null || !DATA?.timelineKind) return "";
  const formatter = TIMELINE_FORMATTERS[DATA.timelineKind] ?? TIMELINE_FORMATTERS.datetime;
  return formatter.format(new Date(ms));
}

function formatDuration(ms0, ms1) {
  const totalMinutes = Math.max(0, Math.round((ms1 - ms0) / 60000));
  if (totalMinutes < 120) return `${totalMinutes}m`;
  const totalHours = Math.round(totalMinutes / 60);
  if (totalHours < 72) return `${totalHours}h`;
  const totalDays = Math.round(totalHours / 24);
  if (totalDays < 120) return `${totalDays}d`;
  const totalMonths = Math.round(totalDays / 30.44);
  if (totalMonths < 24) return `${totalMonths}m`;
  const years = Math.floor(totalMonths / 12);
  const months = totalMonths % 12;
  return months ? `${years}y ${months}m` : `${years}y`;
}

function formatPlaySpeedValue() {
  return `${(state.playSpeed / 100).toFixed(2).replace(/\\.?0+$/, "")}x`;
}

function playbackDurationMs() {
  return playDurationMs / Math.max(0.25, state.playSpeed / 100);
}

function sliderToMs(value) {
  if (!DATA || DATA.timelineMin == null || DATA.timelineMax == null) return 0;
  return DATA.timelineMin + (Number(value) / sliderMax) * (DATA.timelineMax - DATA.timelineMin);
}

function msToSlider(ms) {
  if (!DATA || DATA.timelineMin == null || DATA.timelineMax == null) return 0;
  const total = DATA.timelineMax - DATA.timelineMin || 1;
  return Math.round(((ms - DATA.timelineMin) / total) * sliderMax);
}

function matchesFilters(row) {
  for (const [column, value] of Object.entries(state.filters)) {
    if (value && String(row.filters[column] ?? "") !== value) return false;
  }
  return true;
}

function inTimeline(row) {
  if (!DATA.timelineColumn || row.timelineMs == null) return !DATA.timelineColumn;
  return row.timelineMs >= state.timelineMin && row.timelineMs <= state.timelineMax;
}

function colorValue(row) {
  return row.colors[state.colorBy] ?? "(blank)";
}

function colorScale() {
  const values = [...new Set(DATA.rows.map(colorValue))];
  return d3.scaleOrdinal().domain(values).range(PALETTE);
}

function sceneRows() {
  const filtered = DATA.rows.filter(matchesFilters);
  const selectable = DATA.timelineColumn
    ? filtered.filter((row) => row.timelineMs != null && inTimeline(row))
    : filtered;
  return { filtered, selectable };
}

function formatTimelineParam(ms) {
  if (DATA.timelineKind === "year") return String(new Date(ms).getUTCFullYear());
  if (DATA.timelineKind === "datetime") return STATE_DATE_TIME(new Date(ms));
  return STATE_DATE(new Date(ms));
}

function parseTimelineParam(value, fallback) {
  if (!value) return fallback;
  if (DATA.timelineKind === "year") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Date.UTC(parsed, 0, 1) : fallback;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? fallback : parsed;
}

function syncUrlState() {
  if (!DATA) return;
  const params = new URLSearchParams();
  const defaultColor = DATA.colorColumns[0] ?? "cluster";
  if (state.colorBy !== defaultColor) params.set("color", state.colorBy);
  for (const column of DATA.filterColumns) {
    if (state.filters[column]) params.set(`filter.${column}`, state.filters[column]);
  }
  if (DATA.timelineColumn && DATA.timelineMin != null && DATA.timelineMax != null) {
    if (Math.abs(state.timelineMin - DATA.timelineMin) > 1) params.set("start", formatTimelineParam(state.timelineMin));
    if (Math.abs(state.timelineMax - DATA.timelineMax) > 1) params.set("end", formatTimelineParam(state.timelineMax));
  }
  if (state.sortColumn !== DATA.defaultSort) params.set("sort", state.sortColumn);
  if (!state.sortAsc) params.set("dir", "desc");
  if (DATA.centroidTrails && Object.keys(DATA.centroidTrails).length && state.trailMode !== "both") params.set("trails", state.trailMode);
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}`;
  window.history.replaceState({}, "", nextUrl);
}

function applyUrlState() {
  const params = new URL(window.location.href).searchParams;
  const color = params.get("color");
  if (color && DATA.colorColumns.includes(color)) state.colorBy = color;
  for (const column of DATA.filterColumns) {
    const value = params.get(`filter.${column}`) ?? "";
    const allowed = new Set(DATA.rows.map((row) => String(row.filters[column] ?? "")));
    state.filters[column] = value && allowed.has(value) ? value : "";
  }
  if (DATA.timelineColumn && DATA.timelineMin != null && DATA.timelineMax != null) {
    state.timelineMin = Math.max(DATA.timelineMin, parseTimelineParam(params.get("start"), DATA.timelineMin));
    state.timelineMax = Math.min(DATA.timelineMax, parseTimelineParam(params.get("end"), DATA.timelineMax));
    if (state.timelineMin > state.timelineMax) {
      state.timelineMin = DATA.timelineMin;
      state.timelineMax = DATA.timelineMax;
    }
  }
  const sortColumn = params.get("sort");
  if (sortColumn && DATA.sortColumns.includes(sortColumn)) state.sortColumn = sortColumn;
  state.sortAsc = params.get("dir") !== "desc";
  const trailParam = params.get("trails");
  if (trailParam && ["both", "trails", "nodes"].includes(trailParam)) state.trailMode = trailParam;
}

function clearSelectionBox() {
  selectionBox.style("display", "none");
  dragState = null;
}

function hideTooltip() {
  tooltip.style.display = "none";
}

function syncPlotScales() {
  xScale = zoomTransform.rescaleX(baseXScale);
  yScale = zoomTransform.rescaleY(baseYScale);
}

function updateSummary(scene) {
  const filtered = scene.filtered;
  const visible = scene.selectable;
  summary.textContent = DATA.timelineColumn
    ? `${visible.length} in range / ${filtered.length} filtered / ${DATA.rows.length} total`
    : `${filtered.length} visible / ${DATA.rows.length} total`;
}

function rebuildSpatialIndex(scene) {
  if (!showScatterNodes()) {
    quadtree = null;
    return;
  }
  quadtree = d3.quadtree()
    .x((row) => xScale(row.x))
    .y((row) => yScale(row.y))
    .addAll(scene.selectable);
}

function updateBarChart(scene) {
  const counts = new Map();
  for (const row of scene.selectable) {
    const key = colorValue(row);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const entries = [...counts.entries()]
    .map(([key, count]) => ({ key, label: String(key), count }))
    .sort((left, right) => d3.descending(left.count, right.count) || d3.ascending(left.label, right.label))
    .slice(0, 20);

  barChart.classList.remove("hidden");
  if (!entries.length) {
    barChartHead.innerHTML = `<span>Visible by ${escapeHtml(displaySortLabel(state.colorBy))}</span><span>0 categories</span>`;
    barChartBody.html(`<div class="label">No visible rows</div>`);
    return;
  }

  const totalCategories = counts.size;
  const suffix = totalCategories > entries.length ? `Top ${entries.length} of ${totalCategories}` : `${entries.length} categories`;
  barChartHead.innerHTML = `<span>Visible by ${escapeHtml(displaySortLabel(state.colorBy))}</span><span>${escapeHtml(suffix)}</span>`;
  const maxCount = d3.max(entries, (entry) => entry.count) ?? 1;
  const scale = colorScale();
  const rows = barChartBody.selectAll(".bar-row").data(entries, (entry) => entry.key);
  rows.exit()
    .style("opacity", 0)
    .style("transform", "translateY(-4px)")
    .remove();

  const enter = rows.enter()
    .append("div")
    .attr("class", "bar-row")
    .style("opacity", 0)
    .style("transform", "translateY(-4px)");
  enter.append("div").attr("class", "bar-label");
  const track = enter.append("div").attr("class", "bar-track");
  track.append("div").attr("class", "bar-fill").style("width", "0%");
  enter.append("div").attr("class", "bar-count");

  const merged = enter.merge(rows)
    .style("opacity", 1)
    .style("transform", "translateY(0)");
  merged.select(".bar-label")
    .text((entry) => entry.label)
    .attr("title", (entry) => entry.label);
  merged.select(".bar-count").text((entry) => entry.count.toLocaleString());
  merged.select(".bar-fill")
    .style("background", (entry) => scale(entry.key))
    .style("width", (entry) => `${Math.max(2, (entry.count / maxCount) * 100)}%`);
  merged.sort((left, right) => d3.descending(left.count, right.count) || d3.ascending(left.label, right.label));
}

function activeTrails() {
  if (!DATA.centroidTrails) return [];
  return DATA.centroidTrails[state.colorBy] || DATA.centroidTrails["cluster"] || [];
}

let trailDots = [];

function showTrailLines() {
  return state.trailMode !== "nodes";
}

function showTrailNodes() {
  return state.trailMode !== "trails";
}

function showScatterNodes() {
  return state.trailMode !== "trails";
}

function trailPointBounds(point) {
  if (Number.isFinite(point.timeStartMs) && Number.isFinite(point.timeEndMs)) {
    return { start: point.timeStartMs, end: point.timeEndMs };
  }
  if (!DATA.timelineColumn || DATA.timelineMin == null || DATA.timelineMax == null) {
    return { start: Number.NEGATIVE_INFINITY, end: Number.POSITIVE_INFINITY };
  }
  if (DATA.timelineKind === "year") {
    const year = Number(point.time);
    if (!Number.isFinite(year)) return { start: Number.NEGATIVE_INFINITY, end: Number.POSITIVE_INFINITY };
    return { start: Date.UTC(year, 0, 1), end: Date.UTC(year + 1, 0, 1) - 1 };
  }
  const bucket = Array.isArray(point.time) ? point.time : [];
  const year = Number(bucket[0]);
  const month = Number(bucket[1]);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return { start: Number.NEGATIVE_INFINITY, end: Number.POSITIVE_INFINITY };
  }
  if (DATA.timelineKind === "date") {
    const day = Number(bucket[2]);
    if (!Number.isFinite(day)) return { start: Number.NEGATIVE_INFINITY, end: Number.POSITIVE_INFINITY };
    const start = Date.UTC(year, month - 1, day);
    return { start, end: Date.UTC(year, month - 1, day + 1) - 1 };
  }
  const start = Date.UTC(year, month - 1, 1);
  return { start, end: Date.UTC(year, month, 1) - 1 };
}

function trailPointInRange(point) {
  const bounds = trailPointBounds(point);
  return bounds.end >= state.timelineMin && bounds.start <= state.timelineMax;
}

function trailSegmentInRange(left, right) {
  const leftBounds = trailPointBounds(left);
  const rightBounds = trailPointBounds(right);
  const segmentStart = Math.min(leftBounds.start, rightBounds.start);
  const segmentEnd = Math.max(leftBounds.end, rightBounds.end);
  return segmentEnd >= state.timelineMin && segmentStart <= state.timelineMax;
}

function strokeTrailSegment(ctx, left, right) {
  ctx.beginPath();
  ctx.moveTo(xScale(left.x), yScale(left.y));
  ctx.lineTo(xScale(right.x), yScale(right.y));
  ctx.stroke();
}

function strokeTrailArrow(ctx, left, right) {
  const x1 = xScale(left.x), y1 = yScale(left.y);
  const x2 = xScale(right.x), y2 = yScale(right.y);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const angle = Math.atan2(y2 - y1, x2 - x1);
  ctx.beginPath();
  ctx.moveTo(mx - 6 * Math.cos(angle - 0.45), my - 6 * Math.sin(angle - 0.45));
  ctx.lineTo(mx, my);
  ctx.lineTo(mx - 6 * Math.cos(angle + 0.45), my - 6 * Math.sin(angle + 0.45));
  ctx.stroke();
}

function trailRange(key) {
  let min = Infinity, max = 0;
  for (const trail of activeTrails()) for (const point of trail.points) { min = Math.min(min, point[key] ?? 0); max = Math.max(max, point[key] ?? 0); }
  return { min, max: max || 1 };
}

function trailActiveAlpha(filtered, isHighlighted) {
  if (filtered) return 0.06;
  return isHighlighted ? 0.9 : 0.12;
}

function trailContextAlpha(filtered, isHighlighted) {
  if (filtered) return 0.015;
  return isHighlighted ? 0.18 : 0.03;
}

function drawTrails(ctx) {
  trailDots = [];
  if (!showTrailLines() && !showTrailNodes()) return;
  const trails = activeTrails();
  if (!trails.length) return;
  const scale = colorScale();
  const highlight = state.highlightTrailCluster;
  const filterVal = state.filters[state.colorBy];
  const { min: cMin, max: cMax } = trailRange("count");
  const { min: sMin, max: sMax } = trailRange("std");

  for (const trail of trails) {
    const pts = trail.points;
    if (pts.length < 2) continue;

    const filtered = filterVal && trail.groupLabel !== filterVal;
    const isHighlighted = !filtered && (highlight == null || highlight === trail.groupId);
    const activeAlpha = trailActiveAlpha(filtered, isHighlighted);
    const contextAlpha = trailContextAlpha(filtered, isHighlighted);
    const color = scale(trail.groupLabel);
    const activePoints = pts.map((pt) => trailPointInRange(pt));
    const visiblePoints = pts.filter((pt, index) => activePoints[index]);

    ctx.save();
    if (showTrailLines()) {
      ctx.strokeStyle = color;
      ctx.lineWidth = isHighlighted ? 2.5 : 1.2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      // Keep the full trail faintly visible so the moving in-range segment has context during playback.
      ctx.globalAlpha = contextAlpha;
      for (let i = 0; i < pts.length - 1; i++) {
        strokeTrailSegment(ctx, pts[i], pts[i + 1]);
      }
      ctx.globalAlpha = activeAlpha;
      for (let i = 0; i < pts.length - 1; i++) {
        if (!trailSegmentInRange(pts[i], pts[i + 1])) continue;
        strokeTrailSegment(ctx, pts[i], pts[i + 1]);
      }
    }

    if (showTrailLines() && isHighlighted) {
      for (let i = 0; i < pts.length - 1; i++) {
        if (!trailSegmentInRange(pts[i], pts[i + 1])) continue;
        strokeTrailArrow(ctx, pts[i], pts[i + 1]);
      }
    }

    if (showTrailNodes()) {
      for (let i = 0; i < pts.length; i++) {
        const px = xScale(pts[i].x), py = yScale(pts[i].y);
        const countNorm = cMax > cMin ? (pts[i].count - cMin) / (cMax - cMin) : 0.5;
        const baseR = isHighlighted ? 5 : 3;
        const r = baseR + countNorm * baseR;
        const ageFactor = pts.length > 1 ? i / (pts.length - 1) : 1;
        const pointAlpha = activePoints[i] ? activeAlpha : contextAlpha;
        ctx.globalAlpha = pointAlpha * (0.4 + 0.6 * ageFactor);

        const stdNorm = sMax > sMin ? ((pts[i].std ?? 0) - sMin) / (sMax - sMin) : 0;
        const blur = r + stdNorm * r * 2;
        const grad = ctx.createRadialGradient(px, py, 0, px, py, blur);
        grad.addColorStop(0, color);
        grad.addColorStop(stdNorm < 0.3 ? 0.7 : 0.4, color);
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(px, py, blur, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = "rgba(255,255,255,0.6)";
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.stroke();

        if (activePoints[i]) {
          trailDots.push({ px, py, r: Math.max(r, blur), trail, pt: pts[i] });
        }
      }
    }

    if (isHighlighted && visiblePoints.length >= 1) {
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = "#e2e8f0";
      ctx.font = "bold 10px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillText(
        visiblePoints[0].timeLabel,
        xScale(visiblePoints[0].x),
        yScale(visiblePoints[0].y) - 8,
      );
      ctx.textBaseline = "top";
      ctx.fillText(
        visiblePoints[visiblePoints.length - 1].timeLabel,
        xScale(visiblePoints[visiblePoints.length - 1].x),
        yScale(visiblePoints[visiblePoints.length - 1].y) + 8,
      );
    }

    ctx.restore();
  }
}

function draw(scene = sceneRows()) {
  if (!DATA || !state) return;
  const rows = scene.filtered;
  const scale = colorScale();
  const selected = state.selectedIds;
  const hasSelection = selected.size > 0;
  const baseOpacity = Math.max(0, Math.min(1, DATA.opacity ?? 1));
  const trailsOn = activeTrails().length && state.trailMode !== "nodes";
  const pointOpacity = trailsOn ? baseOpacity * 0.4 : baseOpacity;
  const ctx = plot.getContext("2d");
  ctx.clearRect(0, 0, width, height);

  if (showScatterNodes()) {
    for (let pass = 0; pass < 2; pass += 1) {
      for (const row of rows) {
        const active = inTimeline(row) || !DATA.timelineColumn;
        const chosen = selected.has(row.id);
        let alpha = active ? pointOpacity : Math.max(0.03, pointOpacity * 0.12);
        if (hasSelection && !chosen) alpha = active ? Math.max(0.05, pointOpacity * 0.16) : Math.max(0.02, pointOpacity * 0.06);
        if (hasSelection && chosen) alpha = baseOpacity;
        const bright = alpha >= Math.max(0.25, pointOpacity * 0.45);
        if (pass === 0 && bright) continue;
        if (pass === 1 && !bright) continue;

        ctx.globalAlpha = alpha;
        ctx.fillStyle = scale(colorValue(row));
        ctx.beginPath();
        ctx.arc(xScale(row.x), yScale(row.y), chosen ? pointRadius + 1.6 : pointRadius, 0, Math.PI * 2);
        ctx.fill();
        if (chosen) {
          ctx.globalAlpha = Math.min(1, baseOpacity);
          ctx.strokeStyle = "rgba(255,255,255,0.9)";
          ctx.lineWidth = 1.1;
          ctx.stroke();
        }
      }
    }
  }

  // Draw centroid trails on top of points
  drawTrails(ctx);

  ctx.globalAlpha = 1;
  updateSummary(scene);
  rebuildSpatialIndex(scene);
  updateBarChart(scene);
}

function resetZoom() {
  zoomTransform = d3.zoomIdentity;
  syncPlotScales();
  refreshScene({ syncUrl: false });
}

function resize() {
  if (!DATA || !state) return;
  const rect = plot.parentElement.getBoundingClientRect();
  width = rect.width;
  height = rect.height;
  dpr = window.devicePixelRatio || 1;
  plot.width = Math.floor(width * dpr);
  plot.height = Math.floor(height * dpr);
  plot.style.width = `${width}px`;
  plot.style.height = `${height}px`;
  const ctx = plot.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  baseXScale = d3.scaleLinear().domain(xDomain).range([margin.left, width - margin.right]);
  baseYScale = d3.scaleLinear().domain(yDomain).range([height - margin.bottom, margin.top]);
  syncPlotScales();
  overlay.attr("width", width).attr("height", height);
  refreshScene({ syncUrl: false });
}

function showTooltip(row, event) {
  const image = row.images[0]
    ? `<img src="${escapeHtml(row.images[0])}" alt="${escapeHtml(row.label)}" loading="lazy" fetchpriority="low">`
    : "";
  const fields = Object.entries(row.tooltip)
    .map(([key, value]) => `<div class="tooltip-key">${escapeHtml(key)}</div><div class="tooltip-value">${escapeHtml(value)}</div>`)
    .join("");
  tooltip.innerHTML = `${image}<div class="tooltip-label">${escapeHtml(row.label)}</div><div class="tooltip-grid">${fields}</div>`;
  tooltip.style.display = "block";
  tooltip.style.left = `${Math.max(12, Math.min(window.innerWidth - tooltip.offsetWidth - 12, event.clientX + 14))}px`;
  tooltip.style.top = `${Math.max(12, Math.min(window.innerHeight - tooltip.offsetHeight - 12, event.clientY + 14))}px`;
}

function comparator(left, right) {
  const column = state.sortColumn;
  const direction = state.sortAsc ? 1 : -1;
  let a;
  let b;
  if (column === "_row_index") {
    a = left.id;
    b = right.id;
  } else if (column === DATA.timelineColumn) {
    a = left.timelineMs ?? Number.NEGATIVE_INFINITY;
    b = right.timelineMs ?? Number.NEGATIVE_INFINITY;
  } else {
    a = String(left.raw[column] ?? "");
    b = String(right.raw[column] ?? "");
  }
  if (a < b) return -1 * direction;
  if (a > b) return 1 * direction;
  return (left.id - right.id) * direction;
}

function selectedRows() {
  return DATA.rows.filter((row) => state.selectedIds.has(row.id)).sort(comparator);
}

function syncSortControls() {
  const select = $("#sort-column");
  if (select) select.value = state.sortColumn;
  $("#sort-direction").textContent = state.sortAsc ? "Ascending" : "Descending";
}

function updateSort(column, toggle = false) {
  if (toggle && state.sortColumn === column) state.sortAsc = !state.sortAsc;
  else {
    state.sortColumn = column;
    if (toggle) state.sortAsc = true;
  }
  syncSortControls();
  if (state.selectedIds.size) renderPopup();
  syncUrlState();
}

function renderImages(row) {
  if (!row.images.length) return "";
  return `<div class="card-images popup-image-list">${row.images.map((url) => (
    `<img src="${escapeHtml(url)}" alt="${escapeHtml(row.label)}" loading="lazy" fetchpriority="low">`
  )).join("")}</div>`;
}

function renderAudios(row) {
  if (!row.audios.length) return "";
  return `<div class="card-audios popup-audio-list">${row.audios.map((url) => (
    `<audio controls preload="metadata" src="${escapeHtml(url)}"></audio>`
  )).join("")}</div>`;
}

function renderMediaForColumn(row, column) {
  const images = row.imageUrlsByColumn?.[column] ?? [];
  const audios = row.audioUrlsByColumn?.[column] ?? [];
  const imageHtml = images.map((url) => (
    `<img src="${escapeHtml(url)}" alt="${escapeHtml(row.label)}" loading="lazy" fetchpriority="low" style="width:100%;max-height:240px;object-fit:contain;background:#020617;border-radius:8px;margin-bottom:6px;">`
  )).join("");
  const audioHtml = audios.map((url) => (
    `<audio controls preload="metadata" src="${escapeHtml(url)}" style="width:100%;margin-bottom:6px;"></audio>`
  )).join("");
  return imageHtml + audioHtml;
}

function renderFieldGrid(row, includeInlineMedia = true) {
  return Object.entries(row.raw)
    .map(([key, value]) => (
      `<div class="field-key">${escapeHtml(key)}</div><div class="field-value">${includeInlineMedia ? renderMediaForColumn(row, key) : ""}${escapeHtml(value)}</div>`
    ))
    .join("");
}

function renderTable(rows) {
  const headers = DATA.columns.map((column) => {
    const sorted = state.sortColumn === column;
    const arrow = sorted ? (state.sortAsc ? " ▲" : " ▼") : "";
    return `<th data-sort="${escapeHtml(column)}" class="${sorted ? "sorted" : ""}">${escapeHtml(displaySortLabel(column))}${arrow}</th>`;
  }).join("");
  const body = rows.map((row) => {
    const cells = DATA.columns.map((column) => `<td>${renderMediaForColumn(row, column)}${escapeHtml(row.raw[column] ?? "")}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  popupBody.innerHTML = `<table class="popup-table"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderCards(rows, grid) {
  const className = grid ? "card-grid" : "card-list";
  popupBody.innerHTML = `<div class="${className}">${rows.map((row) => `
    <article class="card">
      <div class="card-head">
        <div class="card-title">${escapeHtml(row.label)}</div>
        <div class="card-subtitle">${escapeHtml(row.timelineText ?? row.clusterLabel)}</div>
      </div>
      ${renderImages(row)}
      ${renderAudios(row)}
      <div class="card-fields">${renderFieldGrid(row, false)}</div>
    </article>
  `).join("")}</div>`;
}

function hidePopupOnly() {
  popup.classList.remove("visible");
  popupBackdrop.classList.remove("visible");
  popupBody.innerHTML = "";
}

function renderPopup() {
  const rows = selectedRows();
  if (!rows.length) {
    hidePopupOnly();
    return;
  }
  popupTitle.textContent = `${rows.length} row${rows.length === 1 ? "" : "s"} selected`;
  if (DATA.popupStyle === "table") renderTable(rows);
  else if (DATA.popupStyle === "grid") renderCards(rows, true);
  else renderCards(rows, false);
  hideTooltip();
  popup.classList.add("visible");
  popupBackdrop.classList.add("visible");
}

function dismissPopup({ clearSelection = true, redraw = true } = {}) {
  hidePopupOnly();
  popupBody.innerHTML = "";
  if (clearSelection) state.selectedIds = new Set();
  clearSelectionBox();
  hideTooltip();
  if (redraw) draw(sceneRows());
}

function syncSelectionToVisible(scene) {
  if (!showScatterNodes()) {
    state.selectedIds = new Set();
    return;
  }
  if (!state.selectedIds.size) return;
  const allowed = new Set(scene.selectable.map((row) => row.id));
  state.selectedIds = new Set([...state.selectedIds].filter((id) => allowed.has(id)));
}

function refreshScene({ scene = sceneRows(), syncUrl = true } = {}) {
  if (!DATA || !state) return;
  syncSelectionToVisible(scene);
  draw(scene);
  if (state.selectedIds.size) renderPopup();
  else hidePopupOnly();
  if (syncUrl) syncUrlState();
}

function buildBrand() {
  $("#brand-title").textContent = DATA.branding || "embedumap";
  $("#brand-subtitle").textContent = DATA.sourceName || "Standalone map";
  axisXLabel.textContent = DATA.axisLabels?.x || "UMAP 1";
  axisYLabel.textContent = DATA.axisLabels?.y || "UMAP 2";
  barChart.dataset.corner = DATA.barChartCorner || "top-right";
}

function buildColorControls() {
  const group = $("#color-group");
  group.innerHTML = DATA.colorColumns.map((column) => (
    `<button data-color="${escapeHtml(column)}" class="${column === state.colorBy ? "active" : ""}">${escapeHtml(displaySortLabel(column))}</button>`
  )).join("");
  group.addEventListener("click", (event) => {
    const button = event.target.closest("[data-color]");
    if (!button) return;
    state.colorBy = button.dataset.color;
    state.highlightTrailCluster = null;
    for (const candidate of group.querySelectorAll("button")) {
      candidate.classList.toggle("active", candidate === button);
    }
    refreshScene();
  });
}

function buildFilterControls() {
  const container = $("#filter-group");
  container.innerHTML = DATA.filterColumns.map((column) => {
    const values = [...new Set(DATA.rows.map((row) => String(row.filters[column] ?? "(blank)")))].sort();
    const options = [`<option value="">All ${escapeHtml(column)}</option>`]
      .concat(values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`))
      .join("");
    return `<select data-filter="${escapeHtml(column)}">${options}</select>`;
  }).join("");
  for (const select of container.querySelectorAll("select")) {
    select.value = state.filters[select.dataset.filter] ?? "";
    select.addEventListener("change", (event) => {
      state.filters[event.target.dataset.filter] = event.target.value;
      refreshScene();
    });
  }
}

function buildSortControls() {
  const select = $("#sort-column");
  select.innerHTML = DATA.sortColumns.map((column) => (
    `<option value="${escapeHtml(column)}"${column === state.sortColumn ? " selected" : ""}>${escapeHtml(displaySortLabel(column))}</option>`
  )).join("");
  select.addEventListener("change", (event) => {
    updateSort(event.target.value);
  });
  $("#sort-direction").addEventListener("click", () => {
    updateSort(state.sortColumn, true);
  });
  syncSortControls();
}

function syncControlsFromState() {
  for (const button of $("#color-group").querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.color === state.colorBy);
  }
  for (const select of $("#filter-group").querySelectorAll("select")) {
    select.value = state.filters[select.dataset.filter] ?? "";
  }
  syncSortControls();
  syncTimelineUi();
  syncPlaybackControls();
}

function syncTimelineUi() {
  if (!DATA.timelineColumn || DATA.timelineMin == null || DATA.timelineMax == null) return;
  const minInput = $("#timeline-min");
  const maxInput = $("#timeline-max");
  const start = msToSlider(state.timelineMin);
  const end = msToSlider(state.timelineMax);
  minInput.value = String(start);
  maxInput.value = String(end);
  $("#timeline-start").textContent = formatTimeline(state.timelineMin);
  $("#timeline-end").textContent = formatTimeline(state.timelineMax);
  $("#timeline-duration").textContent = formatDuration(state.timelineMin, state.timelineMax);
  $("#timeline-duration").style.left = `${((start + end) / 2 / sliderMax) * 100}%`;
  $("#timeline-fill").style.left = `${(start / sliderMax) * 100}%`;
  $("#timeline-fill").style.width = `${((end - start) / sliderMax) * 100}%`;
}

function syncPlaybackControls() {
  const speedInput = $("#timeline-speed");
  if (speedInput) speedInput.value = String(state.playSpeed);
  $("#timeline-speed-value").textContent = formatPlaySpeedValue();
  for (const button of $("#timeline-mode-group").querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.playbackMode === state.playbackMode);
  }
}

function pausePlay() {
  state.playing = false;
  $("#timeline-play").textContent = "▶ Play";
  $("#timeline-play").classList.remove("playing");
  cancelAnimationFrame(playRaf);
}

function stepPlay(timestamp) {
  if (!state.playing) return;
  if (playPrev == null) playPrev = timestamp;
  const delta = timestamp - playPrev;
  playPrev = timestamp;
  const windowSize = state.timelineMax - state.timelineMin;
  const fullRange = Math.max(1, DATA.timelineMax - DATA.timelineMin);
  state.timelineMax = Math.min(DATA.timelineMax, state.timelineMax + (delta * fullRange) / playbackDurationMs());
  // "Reveal" keeps the left edge fixed so Anand can inspect every intermediate state.
  if (state.playbackMode === "slide") {
    state.timelineMin = Math.max(DATA.timelineMin, state.timelineMax - windowSize);
  }
  syncTimelineUi();
  refreshScene();
  if (state.timelineMax >= DATA.timelineMax) {
    pausePlay();
    return;
  }
  playRaf = requestAnimationFrame(stepPlay);
}

function startPlay() {
  const fullRange = Math.max(1, DATA.timelineMax - DATA.timelineMin);
  let windowSize = state.timelineMax - state.timelineMin;
  // Reuse the existing readable starter window whenever playback begins from the full range.
  if (windowSize >= fullRange * 0.999) {
    windowSize = Math.max(fullRange * 0.18, fullRange / Math.min(12, Math.max(2, DATA.rows.length)));
    state.timelineMin = DATA.timelineMin;
    state.timelineMax = Math.min(DATA.timelineMax, DATA.timelineMin + windowSize);
  } else if (state.timelineMax >= DATA.timelineMax) {
    if (state.playbackMode === "reveal") {
      const replayStart = Math.max(DATA.timelineMin, DATA.timelineMax - windowSize);
      state.timelineMin = Math.min(state.timelineMin, replayStart);
      state.timelineMax = Math.min(DATA.timelineMax, state.timelineMin + windowSize);
    } else {
      state.timelineMin = DATA.timelineMin;
      state.timelineMax = Math.min(DATA.timelineMax, DATA.timelineMin + windowSize);
    }
  }
  state.playing = true;
  playPrev = null;
  $("#timeline-play").textContent = "⏸ Pause";
  $("#timeline-play").classList.add("playing");
  playRaf = requestAnimationFrame(stepPlay);
}

function buildTimelineControls() {
  if (!DATA.timelineColumn || DATA.timelineMin == null || DATA.timelineMax == null) return;
  $("#timeline-bar").classList.add("visible");
  $("#timeline-wrap").classList.add("visible");
  const minInput = $("#timeline-min");
  const maxInput = $("#timeline-max");
  const timelineFill = $("#timeline-fill");
  const modeGroup = $("#timeline-mode-group");
  const speedInput = $("#timeline-speed");
  minInput.min = "0";
  minInput.max = String(sliderMax);
  maxInput.min = "0";
  maxInput.max = String(sliderMax);
  // Keep the new playback controls isolated to the timeline so the rest of the viewer stays untouched.
  modeGroup.innerHTML = PLAYBACK_MODES.map((mode) => (
    `<button type="button" data-playback-mode="${escapeHtml(mode.id)}">${escapeHtml(mode.label)}</button>`
  )).join("");

  minInput.addEventListener("input", () => {
    const next = Math.min(Number(minInput.value), Number(maxInput.value) - 100);
    minInput.value = String(next);
    state.timelineMin = sliderToMs(next);
    syncTimelineUi();
    refreshScene();
  });

  maxInput.addEventListener("input", () => {
    const next = Math.max(Number(maxInput.value), Number(minInput.value) + 100);
    maxInput.value = String(next);
    state.timelineMax = sliderToMs(next);
    syncTimelineUi();
    refreshScene();
  });

  let rangeDrag = null;
  const updateRangeDrag = (event) => {
    if (!rangeDrag || event.pointerId !== rangeDrag.pointerId) return;
    const delta = ((event.clientX - rangeDrag.anchorX) / rangeDrag.rect.width) * (DATA.timelineMax - DATA.timelineMin);
    const windowSize = rangeDrag.startMax - rangeDrag.startMin;
    let nextMin = rangeDrag.startMin + delta;
    let nextMax = rangeDrag.startMax + delta;
    if (nextMin < DATA.timelineMin) {
      nextMin = DATA.timelineMin;
      nextMax = DATA.timelineMin + windowSize;
    }
    if (nextMax > DATA.timelineMax) {
      nextMax = DATA.timelineMax;
      nextMin = DATA.timelineMax - windowSize;
    }
    state.timelineMin = nextMin;
    state.timelineMax = nextMax;
    syncTimelineUi();
    refreshScene();
  };
  const finishRangeDrag = (event) => {
    if (!rangeDrag || (event && event.pointerId !== rangeDrag.pointerId)) return;
    timelineFill.style.cursor = "grab";
    timelineFill.releasePointerCapture?.(rangeDrag.pointerId);
    rangeDrag = null;
  };

  timelineFill.addEventListener("pointerdown", (event) => {
    if (state.playing || event.button !== 0) return;
    event.preventDefault();
    rangeDrag = {
      pointerId: event.pointerId,
      rect: $("#timeline-range").getBoundingClientRect(),
      anchorX: event.clientX,
      startMin: state.timelineMin,
      startMax: state.timelineMax,
    };
    timelineFill.style.cursor = "grabbing";
    timelineFill.setPointerCapture?.(event.pointerId);
  });
  timelineFill.addEventListener("pointermove", updateRangeDrag);
  timelineFill.addEventListener("pointerup", finishRangeDrag);
  timelineFill.addEventListener("pointercancel", finishRangeDrag);

  modeGroup.addEventListener("click", (event) => {
    const button = event.target.closest("[data-playback-mode]");
    if (!button) return;
    state.playbackMode = button.dataset.playbackMode;
    syncPlaybackControls();
  });
  speedInput.addEventListener("input", () => {
    state.playSpeed = Number(speedInput.value) || defaultPlaySpeed;
    syncPlaybackControls();
  });
  $("#timeline-play").addEventListener("click", () => {
    if (state.playing) pausePlay();
    else startPlay();
  });

  syncTimelineUi();
  syncPlaybackControls();
}

function pointerPosition(event) {
  const rect = plot.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(rect.width, event.clientX - rect.left)),
    y: Math.max(0, Math.min(rect.height, event.clientY - rect.top)),
  };
}

function updateSelectionBox() {
  if (!dragState) return;
  const x = Math.min(dragState.startX, dragState.currentX);
  const y = Math.min(dragState.startY, dragState.currentY);
  const w = Math.abs(dragState.currentX - dragState.startX);
  const h = Math.abs(dragState.currentY - dragState.startY);
  selectionBox
    .attr("x", x)
    .attr("y", y)
    .attr("width", w)
    .attr("height", h)
    .style("display", "block");
}

function handlePointClick(event) {
  if (!showScatterNodes() || !quadtree) {
    dismissPopup();
    return;
  }
  const { x, y } = pointerPosition(event);
  const found = quadtree.find(x, y, 12);
  if (!found) {
    dismissPopup();
    return;
  }
  state.selectedIds = new Set([found.id]);
  draw(sceneRows());
  renderPopup();
}

function handleBrushSelection(bounds) {
  if (!showScatterNodes()) {
    dismissPopup();
    return;
  }
  const scene = sceneRows();
  const selected = scene.selectable
    .filter((row) => {
      const px = xScale(row.x);
      const py = yScale(row.y);
      return px >= bounds.x0 && px <= bounds.x1 && py >= bounds.y0 && py <= bounds.y1;
    })
    .map((row) => row.id);
  state.selectedIds = new Set(selected);
  clearSelectionBox();
  draw(scene);
  if (selected.length) renderPopup();
  else hidePopupOnly();
}

const TRAIL_MODES = ["both", "trails", "nodes"];
const TRAIL_LABELS = { both: "Trails + Nodes", trails: "Trails Only", nodes: "Nodes Only" };
const PAGE_VARIANTS = {
  "patent-evolution-monthly-2k.html": [
    { id: "2k", label: "Monthly 2k", href: "patent-evolution-monthly-2k.html" },
    { id: "4k", label: "Monthly 4k", href: "patent-evolution-monthly-4k.html" },
  ],
  "patent-evolution-monthly-4k.html": [
    { id: "2k", label: "Monthly 2k", href: "patent-evolution-monthly-2k.html" },
    { id: "4k", label: "Monthly 4k", href: "patent-evolution-monthly-4k.html" },
  ],
};

function pageVariants() {
  const path = window.location.pathname.split("/").pop() || "";
  return PAGE_VARIANTS[path] || [];
}

function buildPageSwitchControls() {
  const variants = pageVariants();
  if (variants.length < 2) return;
  const group = $("#page-switch-group");
  const current = window.location.pathname.split("/").pop() || "";
  group.style.display = "";
  group.innerHTML = variants.map((variant) => (
    `<button data-page-switch="${escapeHtml(variant.href)}" class="${variant.href === current ? "active" : ""}">${escapeHtml(variant.label)}</button>`
  )).join("");
  group.addEventListener("click", (event) => {
    const button = event.target.closest("[data-page-switch]");
    if (!button) return;
    const target = button.dataset.pageSwitch;
    if (!target || target === current) return;
    window.location.href = target;
  });
}

function buildTrailsControls() {
  if (!DATA.centroidTrails || !Object.keys(DATA.centroidTrails).length) return;
  const group = $("#trails-group");
  group.style.display = "";
  const btn = $("#trails-toggle");
  btn.textContent = TRAIL_LABELS[state.trailMode];
  btn.classList.add("active");
  btn.addEventListener("click", () => {
    const idx = (TRAIL_MODES.indexOf(state.trailMode) + 1) % TRAIL_MODES.length;
    state.trailMode = TRAIL_MODES[idx];
    btn.textContent = TRAIL_LABELS[state.trailMode];
    if (!showScatterNodes()) dismissPopup({ clearSelection: true, redraw: false });
    if (state.trailMode === "nodes") state.highlightTrailCluster = null;
    refreshScene();
  });

  // Click on bar chart rows to highlight individual trails
  barChartBody.node().addEventListener("click", (event) => {
    if (!showTrailLines()) return;
    const trails = activeTrails();
    if (!trails.length) return;
    const row = event.target.closest(".bar-row");
    if (!row) return;
    const datum = d3.select(row).datum();
    if (!datum) return;
    const trail = trails.find((t) => t.groupLabel === datum.key);
    if (!trail) return;
    if (state.highlightTrailCluster === trail.groupId) {
      state.highlightTrailCluster = null;
    } else {
      state.highlightTrailCluster = trail.groupId;
    }
    refreshScene();
  });
}

function bindInteractions() {
  const zoomBehavior = d3.zoom()
    .scaleExtent([1, 20])
    .filter((event) => !state.playing && (
      event.type === "wheel"
      || (event.type === "mousedown" && event.shiftKey && event.button === 0)
      || event.type === "touchstart"
    ))
    .on("zoom", (event) => {
      zoomTransform = event.transform;
      syncPlotScales();
      clearSelectionBox();
      hideTooltip();
      refreshScene({ syncUrl: false });
    });
  overlay.call(zoomBehavior).on("dblclick.zoom", null);

  $("#popup-close").addEventListener("click", () => dismissPopup());
  popupBackdrop.addEventListener("click", () => dismissPopup());
  popupBody.addEventListener("click", (event) => {
    const header = event.target.closest("th[data-sort]");
    if (!header || DATA.popupStyle !== "table") return;
    updateSort(header.dataset.sort, true);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") dismissPopup();
    if (event.key === "0") {
      overlay.call(zoomBehavior.transform, d3.zoomIdentity);
    }
  });

  overlayNode.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || state.playing || event.shiftKey || !showScatterNodes()) return;
    const { x, y } = pointerPosition(event);
    dragState = { startX: x, startY: y, currentX: x, currentY: y, moved: false };
    overlayNode.setPointerCapture?.(event.pointerId);
    hideTooltip();
  });

  overlayNode.addEventListener("pointermove", (event) => {
    if (dragState) {
      const { x, y } = pointerPosition(event);
      dragState.currentX = x;
      dragState.currentY = y;
      dragState.moved = dragState.moved || Math.abs(x - dragState.startX) > 4 || Math.abs(y - dragState.startY) > 4;
      if (dragState.moved) updateSelectionBox();
      return;
    }
    if (state.playing || event.buttons > 0) {
      hideTooltip();
      return;
    }
    const { x, y } = pointerPosition(event);
    // Check centroid trail dots first
    const hitDot = trailDots.find((d) => Math.hypot(d.px - x, d.py - y) <= d.r + 4);
    if (hitDot) {
      tooltip.innerHTML = `<div class="tooltip-label">${escapeHtml(hitDot.trail.groupLabel)}</div>`
        + `<div class="tooltip-grid">`
        + `<div class="tooltip-key">Period</div><div class="tooltip-value">${escapeHtml(hitDot.pt.timeLabel)}</div>`
        + `<div class="tooltip-key">Points</div><div class="tooltip-value">${hitDot.pt.count.toLocaleString()}</div>`
        + `<div class="tooltip-key">Spread</div><div class="tooltip-value">${(hitDot.pt.std ?? 0).toFixed(3)}</div>`
        + `</div>`;
      tooltip.style.display = "block";
      tooltip.style.left = `${Math.min(window.innerWidth - 180, event.clientX + 14)}px`;
      tooltip.style.top = `${Math.min(window.innerHeight - 100, event.clientY + 14)}px`;
      return;
    }

    if (!quadtree) { hideTooltip(); return; }
    const found = quadtree.find(x, y, 12);
    if (!found) {
      hideTooltip();
      return;
    }
    showTooltip(found, event);
  });

  overlayNode.addEventListener("pointerup", (event) => {
    if (!dragState) return;
    overlayNode.releasePointerCapture?.(event.pointerId);
    const finished = dragState;
    if (!finished.moved) {
      clearSelectionBox();
      handlePointClick(event);
      return;
    }
    const x0 = Math.min(finished.startX, finished.currentX);
    const y0 = Math.min(finished.startY, finished.currentY);
    const x1 = Math.max(finished.startX, finished.currentX);
    const y1 = Math.max(finished.startY, finished.currentY);
    if (x1 - x0 < 4 || y1 - y0 < 4) {
      clearSelectionBox();
      handlePointClick(event);
      return;
    }
    handleBrushSelection({ x0, y0, x1, y1 });
  });

  overlayNode.addEventListener("pointerleave", () => {
    if (!dragState) hideTooltip();
  });

  overlayNode.addEventListener("pointercancel", () => {
    clearSelectionBox();
    hideTooltip();
  });
}

function boot() {
  try {
    DATA = JSON.parse($("#data-json").textContent);
    globalThis.DATA = DATA;
    state = {
      colorBy: DATA.colorColumns[0] ?? "cluster",
      filters: Object.fromEntries(DATA.filterColumns.map((column) => [column, ""])),
      selectedIds: new Set(),
      sortColumn: DATA.defaultSort,
      sortAsc: true,
      timelineMin: DATA.timelineMin,
      timelineMax: DATA.timelineMax,
      playing: false,
      playbackMode: "slide",
      playSpeed: defaultPlaySpeed,
      trailMode: "both",
      highlightTrailCluster: null,
    };
    globalThis.state = state;
    globalThis.renderPopup = renderPopup;
    applyUrlState();

    popupStyleLabel.textContent = DATA.popupStyle;
    buildBrand();

    xDomain = DATA.xDomain[0] === DATA.xDomain[1]
      ? [DATA.xDomain[0] - 1, DATA.xDomain[1] + 1]
      : DATA.xDomain;
    yDomain = DATA.yDomain[0] === DATA.yDomain[1]
      ? [DATA.yDomain[0] - 1, DATA.yDomain[1] + 1]
      : DATA.yDomain;

    buildColorControls();
    buildFilterControls();
    buildSortControls();
    buildTimelineControls();
    buildTrailsControls();
    buildPageSwitchControls();
    bindInteractions();
    resize();
    syncUrlState();
    requestAnimationFrame(() => loading.classList.add("hidden"));
  } catch (error) {
    loadingTitle.textContent = "Failed to load map";
    loadingCopy.textContent = error?.message ?? String(error);
    throw error;
  }
}

requestAnimationFrame(() => setTimeout(boot, 0));
window.addEventListener("resize", resize);
window.addEventListener("popstate", () => {
  if (!DATA || !state) return;
  applyUrlState();
  syncControlsFromState();
  refreshScene({ syncUrl: false });
});
</script>
</body>
</html>
"""


def render_html(payload: dict[str, object]) -> str:
    """Embed the payload into a standalone HTML page."""

    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__TITLE__", str(payload["title"])).replace("__DATA__", data_json)

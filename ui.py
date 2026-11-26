"""Look and feel: colours, CSS, number formatting and small HTML building blocks.

app.py decides *what* goes on the page; this file decides how it looks.
"""
import math
from html import escape
from string import Template

import pandas as pd
import streamlit as st

# ---------- Colours (one place to change the whole theme) ----------
BG, CARD, CARD2, LINE, GRID = "#0d1015", "#1b2028", "#242b35", "#2b323c", "#262c35"
TEXT, TEXT2, MUTED = "#f2f3f5", "#c3c9d1", "#8f98a3"
ACCENT = "#ff7a3d"
GOOD, WARN, BAD = "#3ecf8e", "#f2c94c", "#ff6b6b"
# Easy / moderate / hard: three steps of one blue ramp (brighter = harder)
INTENSITY = {"Easy": "#1c5cab", "Moderate": "#3987e5", "Hard": "#86b6ef"}
INTENSITY_INK = {"Easy": "#ffffff", "Moderate": "#0b0b0b", "Hard": "#0b0b0b"}
SANS = 'system-ui, -apple-system, "Segoe UI Variable Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

STATUS_ICON = {"good": "check_circle", "ok": "error", "low": "warning", "neutral": "info"}

SPORT_ICON = {"swim": "pool", "bike": "directions_bike", "run": "directions_run", "other": "directions_walk"}
SPORT_NAME = {"swim": "Swim", "bike": "Bike", "run": "Run", "other": "Other"}
TYPE_ICON = {"walking": "directions_walk", "hiking": "hiking", "strength_training": "fitness_center"}
EFFECT_NAME = {
    "RECOVERY": "Recovery", "BASE": "Base", "AEROBIC_BASE": "Base", "TEMPO": "Tempo",
    "LACTATE_THRESHOLD": "Threshold", "VO2MAX": "VO₂ max", "ANAEROBIC_CAPACITY": "Anaerobic",
    "SPRINT": "Sprint",
}

CSS = Template("""
:root {
  color-scheme: dark;
  --bg: $BG; --card: $CARD; --card-2: $CARD2; --line: $LINE;
  --text: $TEXT; --text-2: $TEXT2; --muted: $MUTED;
  --accent: $ACCENT; --accent-soft: rgba(255,122,61,.13); --accent-line: rgba(255,122,61,.4);
  --good: $GOOD; --warn: $WARN; --bad: $BAD;
  --sans: $SANS;
  --display: -apple-system, "SF Pro Display", "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
  --radius: 22px;
}
html, body, .stApp { background: var(--bg); }
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input,
.stMarkdown, .stMarkdown div, .stMarkdown span:not(.ms) { font-family: var(--sans); }
::selection { background: var(--accent-line); color: #fff; }
html { scrollbar-color: #3a424d transparent; }
:focus-visible { outline: 2px solid var(--accent) !important; outline-offset: 2px; }

/* Streamlit's own chrome */
[data-testid="stHeader"] { background: transparent; height: 0; }
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"],
[data-testid="stToolbar"] { display: none !important; }
.block-container { max-width: 1080px; padding: 32px 28px 72px; }
[data-testid="stVerticalBlock"] { gap: 12px; }
[data-testid="stHorizontalBlock"] { gap: 12px; }
.stMarkdown p { margin: 0; }
/* Streamlit pulls each text block up by 16px; undo it so every card gets the same gap */
[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* Blocks that only hold the page's <style> take no space */
.stElementContainer:has(> .stMarkdown style:only-child) { display: none; }
.stMarkdown a.accent { color: var(--accent) !important; }
.stMarkdown a.act { color: inherit !important; }
.st-key-nav { max-width: 600px; }
@media (max-width: 640px) { .block-container { padding: 22px 14px 56px; } }

/* Icons: Material Symbols, the icon font Streamlit ships with */
.ms { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; font-size: 20px;
  line-height: 1; letter-spacing: normal; text-transform: none; display: inline-block; white-space: nowrap;
  direction: ltr; font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; user-select: none;
  vertical-align: -0.2em; }

/* Type */
.stMarkdown .h1 { font: 700 28px/1.15 var(--sans); letter-spacing: -0.02em; color: var(--text); margin: 0; padding: 0; }
.stMarkdown .h2 { font: 650 20px/1.25 var(--sans); letter-spacing: -0.01em; color: var(--text); margin: 22px 2px 0; padding: 0; }
.stMarkdown .h3 { font: 600 16px/1.3 var(--sans); color: var(--text); margin: 0; padding: 0; }
.sub { color: var(--muted); font-size: 14px; margin-top: 6px; }
.muted { color: var(--muted); } .t2 { color: var(--text-2); }
.good { color: var(--good); } .ok { color: var(--warn); } .low { color: var(--bad); } .neutral { color: var(--muted); }
.accent { color: var(--accent); }

/* Cards */
.card { background: var(--card); border-radius: var(--radius); padding: 20px; }
.card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.card-aside { color: var(--muted); font-size: 13px; white-space: nowrap; }
.card-foot { color: var(--muted); font-size: 13px; line-height: 1.45; margin-top: 14px; }
[class*="st-key-card"] { background: var(--card); border-radius: var(--radius); padding: 20px 14px 10px; gap: 6px; }
[class*="st-key-card"] .inset { padding: 0 6px 6px; }

/* Hero: centred title, big figure, comparison in the corner (like the reference) */
.hero { position: relative; text-align: center; padding-top: 22px; }
.hero .h3 { font-size: 17px; }
.corner { position: absolute; top: 20px; right: 20px; text-align: right; line-height: 1.25; }
.corner .k { color: var(--muted); font-size: 13px; }
.corner .v { color: var(--text); font-size: 16px; font-weight: 600; }
.figure { font: 600 60px/1 var(--display); letter-spacing: -0.035em; color: var(--text); margin-top: 12px; }
.figure small { font: 500 17px var(--sans); color: var(--muted); letter-spacing: 0; margin-left: 8px; }
.hero-meta { color: var(--text-2); font-size: 15px; margin-top: 12px; }
.hero-note { color: var(--muted); font-size: 13px; margin-top: 10px; }
.hero-note.ok { color: var(--warn); }  /* e.g. the last weigh-in is over a week old */
[class*="st-key-card"] .hero { padding: 2px 6px 0; }
[class*="st-key-card"] .corner { top: 0; right: 6px; }

/* Status chip: icon + words, never colour alone */
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 4px 11px 4px 8px; border-radius: 99px;
  font-size: 13px; font-weight: 600; margin-top: 12px; }
.chip .ms { font-size: 17px; vertical-align: 0; }
.chip.good { background: rgba(62,207,142,.12); } .chip.ok { background: rgba(242,201,76,.12); }
.chip.low { background: rgba(255,107,107,.12); } .chip.neutral { background: var(--card-2); color: var(--text-2); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.chips .chip { margin-top: 0; }
.hero .chips { justify-content: center; }

/* Change marker: arrow + amount, coloured by whether the change is good */
.delta { display: inline-flex; align-items: center; gap: 1px; font-size: 13px; font-weight: 650;
  font-variant-numeric: tabular-nums; white-space: nowrap; letter-spacing: 0; }
.delta .ms { font-size: 15px; vertical-align: 0; }
.corner .delta { font-size: 16px; } .corner .delta .ms { font-size: 17px; }
.plan .delta { font: 650 15px var(--sans); margin-left: 10px; vertical-align: 6px; }
.chips .delta { padding: 4px 11px 4px 8px; border-radius: 99px; background: var(--card-2); }

/* "How it works": closed by default, opens on click */
.more { margin-top: 14px; }
.more summary { display: inline-flex; align-items: center; gap: 4px; min-height: 40px; margin: -8px 0 -8px -4px;
  padding: 0 8px 0 4px; border-radius: 10px; list-style: none; cursor: pointer; color: var(--muted);
  font-size: 13px; font-weight: 600; transition: color .16s ease-out, background-color .16s ease-out; }
.more summary::-webkit-details-marker { display: none; }
.more summary:hover { color: var(--text); background: rgba(255,255,255,.035); }
.more summary .ms { font-size: 18px; vertical-align: 0; transition: transform .2s cubic-bezier(.2, .7, .2, 1); }
.more[open] summary .ms { transform: rotate(180deg); }
.more-body { margin-top: 10px; color: var(--text-2); font-size: 13px; line-height: 1.5; max-width: 62ch; }
.more-body p { margin: 0 0 8px; }
.more-body b { color: var(--text); font-weight: 600; }
.more-body ul { margin: 0 0 8px; padding-left: 18px; }
.more-body .why { margin: 0 0 8px; padding: 0; }
.more-body .why li { font-size: 13px; padding: 2px 0; }

/* Rows inside a card */
.rows { margin-top: 6px; }
.r { display: flex; align-items: center; gap: 12px; padding: 13px 0; }
.r + .r { border-top: 1px solid var(--line); }
.r-main { flex: 1; min-width: 0; }
.r-label { color: var(--text); font-size: 15px; font-weight: 500; line-height: 1.3; }
.r-sub { color: var(--muted); font-size: 13px; line-height: 1.4; margin-top: 2px; }
.r-value { color: var(--text); font-size: 17px; font-weight: 600; white-space: nowrap; text-align: right;
  font-variant-numeric: tabular-nums; }
.r-value small { color: var(--muted); font-size: 13px; font-weight: 500; margin-left: 3px; }
.r-value.accent { color: var(--accent); }
.r-value .ms { font-size: 18px; margin-right: 4px; vertical-align: -3px; }
.r-label small { color: var(--muted); font-size: 13px; font-weight: 500; margin-left: 6px; }
.r-label .ms { font-size: 16px; color: var(--muted); margin-left: 6px; vertical-align: -2px; }
.rows.tight .r { padding: 9px 0; }
[data-testid="stHeaderActionElements"] { display: none; }  /* Streamlit's link icon next to headings */
.empty { margin: 10px 0 4px; padding: 18px 16px; border-radius: 14px; background: var(--card-2); color: var(--text-2); font-size: 15px; line-height: 1.45; text-align: center; }
.r-value.quiet { color: var(--text-2); font-size: 15px; font-weight: 500; }
.r.stack { display: block; }
.r.stack .r-top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }

/* Progress meter: track + fill */
.meter { height: 6px; border-radius: 99px; background: var(--card-2); overflow: hidden; margin-top: 10px; }
.meter > i { display: block; height: 100%; border-radius: 99px; background: var(--accent); }
.meter > i.good { background: var(--good); }
.meter > i.ok { background: var(--warn); }
.meter { position: relative; }
.meter > b { position: absolute; top: 0; bottom: 0; width: 3px; margin-left: -1px; background: var(--card); }

/* Recovery: a Rest-Easy-Normal-Hard scale, and one bar per signal */
.levels { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 3px; margin: 16px 0 6px; }
.lv i { display: block; height: 8px; border-radius: 2px; opacity: .2; }
.lv:first-child i { border-radius: 99px 2px 2px 99px; }
.lv:last-child i { border-radius: 2px 99px 99px 2px; }
.lv.low i { background: var(--bad); } .lv.ok i { background: var(--warn); } .lv.good i { background: var(--good); }
.lv.on i { opacity: 1; }
.lv span { display: block; margin-top: 6px; text-align: center; color: var(--muted); font-size: 13px; }
.lv.on span { color: var(--text); font-weight: 650; }
/* Bullet bar: the shaded part is your normal range, the dot is today */
.bullet { position: relative; height: 6px; margin: 12px 6px 0; border-radius: 99px; background: var(--card-2); }
.bullet .band { position: absolute; top: 0; bottom: 0; border-radius: 99px; background: rgba(62,207,142,.3); }
.bullet .dot { position: absolute; top: 50%; width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%;
  background: var(--good); box-shadow: 0 0 0 3px var(--card); }
.bullet .dot.ok { background: var(--warn); } .bullet .dot.low { background: var(--bad); }
.bullet .dot.neutral { background: var(--text-2); }
/* Small score bar inside a row */
.sbar { display: inline-block; width: 84px; height: 6px; margin-right: 12px; border-radius: 99px; overflow: hidden;
  background: var(--card-2); vertical-align: middle; }
.sbar i { display: block; height: 100%; border-radius: 99px; background: var(--accent); }
/* Best bedtime: one bar per asleep-by time, its length the score; the best one in orange */
.barlist .r-main { flex: 0 0 150px; }
.barlist .r-label { white-space: nowrap; }
.barlist .r-value { flex: 1; display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.barlist .sbar { flex: 1; width: auto; height: 8px; margin: 0; }
.barlist .sbar i { background: #4a525e; }
.barlist .r-value.accent .sbar i { background: var(--accent); }
.strip.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
/* Reasons list (workout) */
.why { list-style: none; margin: 14px 0 0; padding: 0; }
.why li { display: flex; align-items: flex-start; gap: 10px; padding: 3px 0; color: var(--text-2); font-size: 15px; line-height: 1.4; }
.why .ms { flex: none; color: var(--muted); font-size: 18px; margin-top: 1px; }

/* Tonight */
.plan { margin-top: 12px; font: 600 34px/1.15 var(--display); letter-spacing: -0.02em; color: var(--text); }
.plan b { color: var(--accent); font-weight: 650; }
.now-pill { display: inline-flex; align-items: center; gap: 6px; margin-top: 12px; padding: 5px 12px 5px 9px;
  border-radius: 99px; background: var(--accent-soft); color: var(--accent); font-size: 13px; font-weight: 600; }
.now-pill .ms { font-size: 17px; vertical-align: 0; }

/* Notice */
.notice { display: flex; gap: 10px; align-items: flex-start; padding: 13px 16px; border-radius: 16px;
  background: var(--card); color: var(--text-2); font-size: 15px; line-height: 1.45; }
.notice .ms { color: var(--muted); font-size: 20px; margin-top: 0; }
.notice b { color: var(--text); font-weight: 600; }

/* Stat strip */
.strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 18px; }
.strip > div { padding: 2px 8px; text-align: center; }
.strip > div + div { border-left: 1px solid var(--line); }
.strip-v { color: var(--text); font-size: 20px; font-weight: 600; line-height: 1.2; letter-spacing: -0.01em; }
.strip-v small { color: var(--muted); font-size: 13px; font-weight: 500; margin-left: 2px; }
.strip-k { color: var(--muted); font-size: 13px; line-height: 1.35; margin-top: 4px; }

/* Sport + activity rows */
.tile { flex: none; width: 42px; height: 42px; border-radius: 13px; background: var(--card-2);
  display: flex; align-items: center; justify-content: center; color: var(--text-2); }
.tile .ms { font-size: 22px; vertical-align: 0; }
a.act { display: flex; align-items: center; gap: 12px; margin: 0 -10px; padding: 11px 10px; border-radius: 14px;
  color: inherit; text-decoration: none; transition: background-color .16s ease-out; }
a.act:hover { background: rgba(255,255,255,.035); }
a.act + a.act { box-shadow: 0 -1px 0 var(--line); }
a.act:hover + a.act, a.act:hover { box-shadow: none; }
.act-name { color: var(--text); font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.act-stats { text-align: right; white-space: nowrap; color: var(--text); font-size: 15px; font-weight: 600;
  font-variant-numeric: tabular-nums; }
.act-stats div { color: var(--muted); font-size: 13px; font-weight: 500; margin-top: 2px; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 99px; background: var(--card-2); color: var(--text-2);
  font-size: 12px; font-weight: 600; margin-left: 6px; vertical-align: 1px; }
.chev { color: var(--muted); font-size: 20px; margin-left: -4px; }

/* Latest workout */
.stats4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }
.stats4 .strip-v { font-size: 19px; }
.stats4 > div { text-align: left; }

/* Tall segmented bar (easy / moderate / hard) */
.seg { position: relative; display: flex; gap: 2px; height: 28px; margin: 16px 0 12px; }
.seg .target { position: absolute; top: -5px; bottom: -5px; width: 2px; margin-left: -1px; border-radius: 1px;
  background: var(--text); box-shadow: 0 0 0 2px var(--card); }
.key.mark { width: 2px; height: 12px; border-radius: 1px; background: var(--text); vertical-align: -1px; }
/* A card whose list opens on click (the summary is the card's title row) */
details.list > summary { list-style: none; cursor: pointer; }
details.list > summary::-webkit-details-marker { display: none; }
details.list > summary .ms { font-size: 20px; margin-left: 4px; vertical-align: -5px; transition: transform .2s cubic-bezier(.2, .7, .2, 1); }
details.list[open] > summary .ms { transform: rotate(180deg); }
details.list > summary:hover .card-aside { color: var(--text); }
.card-aside a .ms { font-size: 15px; margin-left: 3px; vertical-align: -2px; }
.seg > div { border-radius: 4px; display: flex; align-items: center; padding-left: 8px; font-size: 12.5px;
  font-weight: 650; min-width: 0; overflow: hidden; white-space: nowrap; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; }
.legend span { color: var(--muted); font-size: 13px; }
.legend b { color: var(--text); font-weight: 600; }
.key { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: 0; }

/* Segmented controls (tabs and period) */
.st-key-tab, .st-key-tab [data-testid="stButtonGroup"] { width: 100% !important; }
[data-testid="stButtonGroup"] [role="radiogroup"] { display: flex; flex-wrap: nowrap; gap: 4px;
  background: var(--card); border-radius: 14px; padding: 4px; }
.st-key-tab [role="radiogroup"] { width: 100% !important; max-width: none !important; }
button[data-variant="segmented_control"] { flex: 1 1 0; min-width: 0; max-width: none !important;
  padding: 4px 12px !important; border: none !important; border-radius: 10px !important; justify-content: center;
  background: transparent !important; color: var(--muted) !important; min-height: 44px; box-shadow: none !important;
  transition: background-color .18s ease-out, color .18s ease-out; }
button[data-variant="segmented_control"] p { font-weight: 650; letter-spacing: .06em; font-size: 13px; white-space: nowrap; }
button[data-variant="segmented_control"][aria-checked="true"] { background: #4a525e !important; color: var(--text) !important; }
button[data-variant="segmented_control"]:hover { color: var(--text) !important; }
/* Clicking the tab that's already open does nothing (Streamlit would unselect it) */
.st-key-tab button[aria-checked="true"] { pointer-events: none; }
/* While the app redraws, Streamlit fades everything to a third of its opacity; on a dashboard that
   redraws often (tab switches, auto-sync) that reads as flicker, so keep cards fully visible */
.stApp [data-stale="true"] { opacity: 1 !important; transition: none !important; }

/* Cards ease in when they first appear (opening the app, switching tabs) instead of popping.
   The animation is on the element's outer box, which Streamlit keeps between redraws, so a card
   only fades in when it's new, not every time its numbers update. Charts fade in once drawn. */
@keyframes card-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
.stElementContainer:has(> div > div > .card),
.stElementContainer:has(.stMarkdown .card),
[class*="st-key-card"] {
  animation: card-in .32s cubic-bezier(.2, .7, .2, 1) both;
}
[class*="st-key-card"] .stElementContainer:has(.card) { animation: none; }
[class*="st-key-chart_"] .vega-embed { animation: fade-in .4s ease-out both; }
/* Opening the app or a tab: Streamlit sends the page in bursts, so it used to grow in jumps. Keep it
   hidden until it has all arrived, then fade it in once. A click's redraw ends within the 1.5s delay, so it
   never flickers; a sync (.sync-pill) or meal estimate (.task) keeps the page visible while it works. */
[class*="st-key-page_"] { transition: opacity .3s ease-out; }
.stApp:is([data-test-script-state="initial"], [data-test-script-state="running"]):not(:has(.sync-pill, .task))
  [class*="st-key-page_"] { opacity: 0; transition: opacity .15s ease-in 1.5s; }
/* Streamlit's fullscreen button stretches these small charts into tall spikes; they're sized to be
   read in their card, so hide it (and the chart's own ⋯ menu) */
[class*="st-key-chart_"] [data-testid="stElementToolbar"],
[class*="st-key-chart_"] .vega-embed details { display: none !important; }

/* Each chart's slot starts at the chart's final height (the `height` in charts.py), so cards
   don't grow and shove each other down as charts finish drawing */
.st-key-chart_recent { min-height: 112px; }
.st-key-chart_scores { min-height: 120px; }
.st-key-chart_vo2 { min-height: 140px; }
.st-key-chart_hours { min-height: 150px; }
.st-key-chart_stages { min-height: 150px; }
.st-key-chart_steps { min-height: 160px; }
.st-key-chart_bylength { min-height: 170px; }
.st-key-chart_weekly { min-height: 170px; }
.st-key-chart_burn { min-height: 170px; }
.st-key-chart_foodhist { min-height: 160px; }
.st-key-chartwarm { display: none; }  /* hidden chart that loads the chart code early (app.py) */
.st-key-chart_weight { min-height: 180px; }

/* Rows of buttons or inputs inside a card stay side by side on phones too. Streamlit otherwise
   draws them stacked first and then re-arranges them once it has measured the screen. */
[class*="st-key-card"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 10px; }
[class*="st-key-card"] [data-testid="stColumn"] { min-width: 0 !important; }

/* A card drawn twice, once per layout, so phones and desktops can each get the best order */
.stElementContainer:has(.phone-only) { display: none; }
@media (max-width: 640px) {
  .stElementContainer:has(.desk-only) { display: none; }
  .stElementContainer:has(.phone-only) { display: block; }
}
/* Weight units sit in the card's top-right corner, like the comparison corner on other cards */
.st-key-card_weight { position: relative; }
.st-key-wunit { position: absolute !important; top: 16px; right: 16px; z-index: 2; width: auto !important; }
.stApp .st-key-wunit button[data-variant="segmented_control"] { min-height: 30px; padding: 2px 12px !important; }

/* Drop-down sections (like "Update class schedule") match the inset panels */
[class*="st-key-card"] [data-testid="stExpander"] { padding: 0 6px; }
[class*="st-key-card"] [data-testid="stExpander"] details { border: none; border-radius: 14px; background: var(--card-2); }
[class*="st-key-card"] [data-testid="stExpander"] summary { padding: 12px 16px; border-radius: 14px; }
[class*="st-key-card"] [data-testid="stExpander"] summary:hover { color: var(--text); }
[class*="st-key-card"] [data-testid="stExpander"] summary p { font-weight: 600; }

/* Pill-style choices: period pickers and the calorie goal */
:is(.st-key-period, .st-key-wperiod, .st-key-goal, .st-key-wunit, [class*="st-key-f_slot"]) [role="radiogroup"] { background: transparent; padding: 0; gap: 6px; }
:is(.st-key-period, .st-key-wperiod, .st-key-goal, .st-key-wunit, [class*="st-key-f_slot"]) button[data-variant="segmented_control"] { flex: 0 0 auto; min-height: 36px;
  padding: 4px 14px !important; border-radius: 99px !important; background: var(--card) !important; }
[class*="st-key-card"] :is(.st-key-wperiod, .st-key-goal, .st-key-wunit, [class*="st-key-f_slot"]) button[data-variant="segmented_control"] { background: var(--card-2) !important; }
:is(.st-key-period, .st-key-wperiod, .st-key-goal, .st-key-wunit, [class*="st-key-f_slot"]) button[data-variant="segmented_control"] p { letter-spacing: 0; font-weight: 600; }
.stApp :is(.st-key-period, .st-key-wperiod, .st-key-goal, .st-key-wunit, [class*="st-key-f_slot"]) button[data-variant="segmented_control"][aria-checked="true"] {
  background: var(--accent-soft) !important; color: var(--accent) !important; }
:is(.st-key-wperiod, .st-key-goal, .st-key-wunit, [class*="st-key-f_slot"]) { padding: 0 6px; }

/* Buttons */
[data-testid="stBaseButton-secondary"] { border-radius: 99px; border: 1px solid var(--line); background: var(--card);
  color: var(--text); min-height: 40px; transition: background-color .16s ease-out, border-color .16s ease-out; }
[data-testid="stBaseButton-secondary"]:hover { border-color: #3a424d; background: var(--card-2); color: var(--text); }

/* Header row stays on one line, even on phones */
.st-key-header [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; align-items: center; }
.st-key-header [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
.st-key-header [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
.st-key-header_actions { flex-wrap: nowrap !important; }
/* "Phone" popover: a QR code to open the dashboard on your phone (pointless on the phone itself) */
.phone-qr { background: #fff; border-radius: 10px; padding: 14px; width: fit-content; margin: 0 auto; }
.phone-qr svg { display: block; width: 180px; height: 180px; shape-rendering: crispEdges; }
.phone-url { text-align: center; font-size: 13px; color: var(--text-2); margin: 10px 0 4px;
  font-variant-numeric: tabular-nums; user-select: all; }
.phone-steps { font-size: 13px; color: var(--text-2); padding-left: 18px; margin: 8px 0; }
.phone-steps li { margin: 4px 0; font-size: 13px !important; line-height: 1.45; }
[data-testid="stPopoverBody"]:has(.phone-qr) { max-width: 340px; }
@media (max-width: 640px) { .st-key-phone_btn { display: none !important; } }

/* Chart tooltips (Vega) */
#vg-tooltip-element { background: var(--card-2) !important; color: var(--text) !important; border: 1px solid #333b46 !important;
  border-radius: 12px !important; padding: 8px 12px !important; font-family: var(--sans) !important; font-size: 13px !important;
  box-shadow: 0 8px 24px rgba(0,0,0,.35) !important; }
/* Streamlit squeezes tooltip labels into tiny boxes; give each cell its normal table layout back */
#vg-tooltip-element table tr td { display: table-cell !important; width: auto !important; height: auto !important;
  max-width: none !important; overflow: visible !important; padding: 2px 0 !important; vertical-align: baseline; }
#vg-tooltip-element table tr td.key { color: var(--muted) !important; font-weight: 500 !important; padding-right: 14px !important;
  text-align: left !important; }
#vg-tooltip-element table tr td.value { color: var(--text) !important; font-weight: 600 !important; font-variant-numeric: tabular-nums; }

/* Floating "updating" panel with a progress bar */
.sync-pill { position: fixed; top: 14px; left: 50%; transform: translateX(-50%); z-index: 1000;
  width: min(340px, calc(100vw - 32px)); padding: 11px 16px 13px; border-radius: 16px; background: var(--card-2);
  box-shadow: 0 10px 30px rgba(0,0,0,.45); }
.sync-top { display: flex; align-items: center; gap: 8px; color: var(--text); font-size: 13px; font-weight: 600; }
.sync-top .ms { font-size: 17px; vertical-align: 0; color: var(--accent); animation: spin 1s linear infinite; }
.sync-step { margin-left: auto; color: var(--muted); font-weight: 500; white-space: nowrap; }
.sync-bar { height: 4px; border-radius: 99px; background: rgba(255,255,255,.08); margin-top: 10px; overflow: hidden; }
.sync-bar > i { display: block; height: 100%; border-radius: 99px; background: var(--accent); transition: width .4s ease-out; }
@keyframes spin { to { transform: rotate(360deg); } }
/* Progress inside a card, e.g. "Estimating your meal" on the Food tab */
.task { background: var(--card-2); border-radius: 12px; padding: 12px 14px; }
.task-found { list-style: none; margin: 10px 0 0; padding: 0; }
.task-found li { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-2);
  margin: 4px 0; animation: fade-in .25s ease-out both; }
.task-found .ms { font-size: 16px; color: var(--good); }

/* Sleep timeline (tonight): bars on a shared night-time axis */
.tl { margin-top: 18px; }
.tl-row + .tl-row { margin-top: 12px; }
.tl-head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-size: 13px; line-height: 1.3; }
.tl-name { color: var(--text-2); font-weight: 600; }
.tl-detail { color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tl-detail b { color: var(--text); font-weight: 600; }
.tl-track { position: relative; height: 12px; margin-top: 6px; border-radius: 99px; background: var(--card-2); }
.tl-track i { position: absolute; top: 0; bottom: 0; border-radius: 99px; background: var(--accent); }
.tl-track i.usual { background: #6b7482; }
.tl-track i.now { background: transparent; box-shadow: inset 0 0 0 2px var(--accent); }
.tl-axis { position: relative; height: 15px; margin-top: 8px; color: var(--muted); font-size: 11.5px; }
.tl-axis span { position: absolute; top: 0; transform: translateX(-50%); white-space: nowrap; }
.tl-axis span:first-child { transform: none; }
.tl-axis span:last-child { transform: translateX(-100%); }

/* Workout suggestion */
.plan-row { display: flex; align-items: center; gap: 14px; margin-top: 14px; }
.plan-row .plan { margin-top: 0; }
.tag.accent { background: var(--accent-soft); color: var(--accent); }

/* Form inputs (weight log) */
.stApp [data-testid="stWidgetLabel"] p { color: var(--muted); font-size: 13px; font-weight: 500; }
[class*="st-key-card"] [data-baseweb="input"], [class*="st-key-card"] [data-baseweb="base-input"],
[class*="st-key-card"] [data-baseweb="input"] input { background-color: var(--card-2) !important; }
[class*="st-key-card"] [data-baseweb="input"] { border-color: transparent !important; border-radius: 12px !important; }
[class*="st-key-card"] [data-testid="stNumberInputContainer"] { border-radius: 12px; background: var(--card-2); }
[class*="st-key-card"] [data-testid="stNumberInputStepDown"], [class*="st-key-card"] [data-testid="stNumberInputStepUp"] {
  background: var(--card-2); color: var(--text-2); }
.stApp input { font-variant-numeric: tabular-nums; }
[data-testid="stBaseButton-primaryFormSubmit"], [data-testid="stBaseButton-primary"] { border-radius: 99px; border: none;
  background: var(--accent); color: #14171c; font-weight: 650; min-height: 40px; transition: filter .16s ease-out; }
[data-testid="stBaseButton-primaryFormSubmit"]:hover, [data-testid="stBaseButton-primary"]:hover {
  background: var(--accent); color: #14171c; filter: brightness(1.08); }
[data-testid="stBaseButton-primaryFormSubmit"] p { font-weight: 650; }
[data-testid="stForm"] { padding: 0; border: none; }
.st-key-logform, .st-key-mealform, .st-key-reviewform { padding: 0 6px; }
[class*="st-key-card"] [data-testid="stFileUploaderDropzone"] { background: var(--card-2); border-radius: 14px; }
[data-testid="stFileUploaderDropzoneInstructions"] { display: none; }  /* "200MB per file • JPG…" */
/* Meal photos: the whole box is one big Upload button, easy to hit with a thumb */
.st-key-mealform [data-testid="stFileUploaderDropzone"] { padding: 0; border: none; background: none; }
.st-key-mealform [data-testid="stFileUploaderDropzone"] button:not([data-testid="stFileChip"] button) { width: 100%; min-height: 64px;
  justify-content: center; border-radius: 14px; border: 1.5px dashed var(--line-2, rgba(255,255,255,.18));
  background: var(--card-2); font-size: 15px; font-weight: 600; }
.st-key-mealform [data-testid="stFileUploaderDropzone"] button:not([data-testid="stFileChip"] button):hover,
.st-key-mealform [data-testid="stFileUploaderDropzone"] button:not([data-testid="stFileChip"] button):focus-visible { border-color: var(--accent); color: var(--text); }
.stMarkdown code { background: var(--card-2); color: var(--text); padding: 1px 6px; border-radius: 6px; font-size: 13px; }
.st-key-mealrows [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; border-top: 1px solid var(--line);
  margin: 0 6px; align-items: center; }
.st-key-mealrows [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
.st-key-mealrows [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
.st-key-mealrows .r { padding: 9px 0; }
.st-key-mealrows [data-testid="stBaseButton-tertiary"] [data-testid="stMarkdownContainer"] {
  position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.st-key-logform [data-testid="stHorizontalBlock"], .st-key-wrecent [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
.st-key-logform [data-testid="stColumn"] { min-width: 0 !important; }
.st-key-wrecent [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
.st-key-wrecent [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
.st-key-wrecent [data-testid="stHorizontalBlock"] { border-top: 1px solid var(--line); margin: 0 6px; align-items: center; }
.st-key-wrecent .r { padding: 9px 0; }
[data-testid="stBaseButton-tertiary"] { color: var(--muted); min-height: 40px; min-width: 40px; }
[data-testid="stBaseButton-tertiary"]:hover { color: var(--bad); }
/* Keep the button's words for screen readers, show only its icon */
.st-key-wrecent [data-testid="stBaseButton-tertiary"] [data-testid="stMarkdownContainer"] {
  position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.key.dash { width: 14px; height: 0; border-radius: 0; border-top: 2px dashed var(--text-2); vertical-align: 3px; }

@media (max-width: 640px) {
  .figure { font-size: 52px; }
  .plan { font-size: 30px; }
  .stMarkdown .h1 { font-size: 24px; }
  .hero { display: flex; flex-direction: column; align-items: center; }
  .corner { position: static; order: 10; margin-top: 10px; text-align: center; }
  .corner .k, .corner .v { display: inline; font-size: 13px; }
  .corner .v { margin-left: 4px; }
  .stats4 { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 14px; }
  button[data-variant="segmented_control"] p { font-size: 12px; letter-spacing: .03em; }
  .st-key-tab button[data-variant="segmented_control"] { padding: 4px 1px !important; }
  .st-key-tab button[data-variant="segmented_control"] p { font-size: 11px; letter-spacing: .02em; }
  .act-stats .opt { display: none; }
  .barlist .r-main { flex-basis: 166px; }
  .barlist .r-value { gap: 8px; }
  /* Weight log: weight + day side by side, Save full width below */
  .st-key-logform [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; row-gap: 10px; }
  .st-key-logform [data-testid="stColumn"] { flex: 1 1 calc(50% - 6px) !important; width: calc(50% - 6px) !important; }
  .st-key-logform [data-testid="stColumn"]:last-child { flex: 1 1 100% !important; width: 100% !important; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
""").substitute(
    BG=BG, CARD=CARD, CARD2=CARD2, LINE=LINE, TEXT=TEXT, TEXT2=TEXT2, MUTED=MUTED,
    ACCENT=ACCENT, GOOD=GOOD, WARN=WARN, BAD=BAD, SANS=SANS)


def inject_css():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def html(s):
    st.markdown(s, unsafe_allow_html=True)


# ---------- Formatting ----------
def clock(hours):
    """23.67 -> '11:40 pm', 25.5 -> '1:30 am' (12-hour, like the Windows setting)."""
    total = int(round(hours * 60)) % (24 * 60)
    h, m = divmod(total, 60)
    return f"{h % 12 or 12}:{m:02d} {'am' if h < 12 else 'pm'}"


def clock_range(a, b):
    """'10:30–11:40 pm' (shared am/pm written once)."""
    first, second = clock(a), clock(b)
    if first[-2:] == second[-2:]:
        first = first[:-3]
    return f"{first}–{second}"


def hhmm(t):
    """'01:30' -> '1:30 am'"""
    h, m = map(int, t.split(":"))
    return clock(h + m / 60)


def dur(hours):
    """7.27 -> '7h 16m'"""
    if hours is None or pd.isna(hours):
        return "–"
    total = int(round(hours * 60))
    h, m = divmod(abs(total), 60)
    sign = "-" if total < 0 else ""
    if h == 0:
        return f"{sign}{m} min"
    return f"{sign}{h}h {m}m" if m else f"{sign}{h}h"


def dur_min(minutes):
    return dur(minutes / 60)


def num(x, digits=0):
    if x is None or pd.isna(x):
        return "–"
    return f"{x:,.{digits}f}"


def day(ts, weekday=False):
    """'Nov 7' or 'Fri, Nov 7'."""
    ts = pd.Timestamp(ts)
    return (f"{ts:%a}, " if weekday else "") + f"{ts:%b} {ts.day}"


def pace(seconds):
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def ago(when, now):
    mins = int((now - when).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 60 * 24:
        return f"{mins // 60} h ago"
    return f"{day(when)}"


def join_words(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# ---------- Building blocks ----------
def icon(name, cls=""):
    return f'<span class="ms {cls}" aria-hidden="true">{name}</span>'


def tip_attr(tip):
    """Hover text for an element (the detail that used to be written out under it)."""
    return f' title="{escape(tip)}"' if tip else ""


def chip(status, text, tip=""):
    return f'<span class="chip {status}"{tip_attr(tip)}>{icon(STATUS_ICON[status])}{escape(text)}</span>'


def pill(name, text, cls="neutral", tip=""):
    """A chip with its own icon, for facts that aren't good/bad, like "by 10:30 pm"."""
    return f'<span class="chip {cls}"{tip_attr(tip)}>{icon(name)}{escape(text)}</span>'


def delta(change, text, good_when_up=True, tip="", small=0):
    """A small change marker: the arrow shows the direction, the colour whether that's good
    (good_when_up=None: neither, like weight). Changes of `small` or less stay grey, so noise
    doesn't look like news. `text` is the size of the change, without a sign."""
    arrow = "trending_flat" if change == 0 else "arrow_upward" if change > 0 else "arrow_downward"
    tone = ("neutral" if abs(change) <= small or good_when_up is None
            else "good" if (change > 0) == good_when_up else "low")
    said = f"{'no change' if change == 0 else 'up' if change > 0 else 'down'} {text}"
    return (f'<span class="delta {tone}" role="img" aria-label="{escape(said)}"{tip_attr(tip)}>'
            f'{icon(arrow)}{escape(text)}</span>')


def more(body, summary="How it works"):
    """An explanation that stays closed until clicked, so the card itself is just the visual."""
    return (f'<details class="more"><summary>{icon("expand_more")}{summary}</summary>'
            f'<div class="more-body">{body}</div></details>')


def meter(fraction, status=""):
    width = max(0.0, min(float(fraction), 1.0)) * 100
    # Past the target: the bar fills and a notch marks where the target was, so you can see how far over
    notch = f'<b style="left:{100 / fraction:.0f}%"></b>' if fraction > 1 else ""
    return f'<div class="meter" role="presentation"><i class="{status}" style="width:{width:.0f}%"></i>{notch}</div>'


def row(label, value, unit="", sub="", lead="", value_cls="", tip=""):
    unit_html = f"<small>{unit}</small>" if unit else ""
    sub_html = f'<div class="r-sub">{sub}</div>' if sub else ""
    return (f'<div class="r"{tip_attr(tip)}>{lead}<div class="r-main"><div class="r-label">{label}</div>{sub_html}</div>'
            f'<div class="r-value {value_cls}">{value}{unit_html}</div></div>')


def meter_row(label, value, unit, fraction, status="", tip=""):
    unit_html = f"<small>{unit}</small>" if unit else ""
    return (f'<div class="r stack"{tip_attr(tip)}><div class="r-top"><div class="r-label">{label}</div>'
            f'<div class="r-value">{value}{unit_html}</div></div>{meter(fraction, status)}</div>')


def card(inner, cls=""):
    return f'<div class="card {cls}">{inner}</div>'


def card_head(title, aside="", level=2):
    """Card title row. level is the HTML heading level (2 for cards, 3 under a section heading)."""
    aside_html = f'<span class="card-aside">{aside}</span>' if aside else ""
    return f'<div class="card-head"><h{level} class="h3">{title}</h{level}>{aside_html}</div>'


def notice(text, name="info"):
    return f'<div class="notice">{icon(name)}<div>{text}</div></div>'


def strip(items):
    """Stat tiles side by side. items: (value, label) or (value, label, hover text)."""
    cells = "".join(f'<div{tip_attr(tip[0] if tip else "")}><div class="strip-v">{v}</div><div class="strip-k">{k}</div></div>'
                    for v, k, *tip in items)
    return f'<div class="strip{" two" if len(items) == 2 else ""}">{cells}</div>'


LEVELS = [("Rest", "low"), ("Easy", "ok"), ("Normal", "good"), ("Hard", "good")]


def readiness_scale(level, said=""):
    """Four steps from Rest to Hard; today's step lit up (the words say it too, not just colour)."""
    cells = "".join(f'<div class="lv {status}{" on" if i == level else ""}"><i></i><span>{name}</span></div>'
                    for i, (name, status) in enumerate(LEVELS))
    return f'<div class="levels" role="img" aria-label="{escape(said or LEVELS[level][0])}">{cells}</div>'


def bullet(x, band, domain, status):
    """A bar with your normal range shaded and today's value as a dot."""
    lo, hi = domain

    def pct(v):
        return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))

    b0, b1 = pct(band[0]), pct(band[1])
    return (f'<div class="bullet" role="presentation"><i class="band" style="left:{b0:.1f}%; width:{b1 - b0:.1f}%"></i>'
            f'<i class="dot {status}" style="left:{pct(x):.1f}%"></i></div>')


def bullet_row(label, value, unit, x, band, domain, status, tip=""):
    unit_html = f"<small>{unit}</small>" if unit else ""
    return (f'<div class="r stack"{tip_attr(tip)}><div class="r-top"><div class="r-label">{label}</div>'
            f'<div class="r-value">{value}{unit_html}</div></div>{bullet(x, band, domain, status)}</div>')


def score_bar(score):
    return f'<span class="sbar"><i style="width:{max(0, min(100, score)):.0f}%"></i></span>'


def sync_pill(fraction, step):
    """The floating 'Updating from Garmin' panel with a progress bar."""
    pct = round(max(0.0, min(1.0, fraction)) * 100)
    return (f'<div class="sync-pill" role="status" aria-live="polite">'
            f'<div class="sync-top">{icon("progress_activity")}<span>Updating from Garmin</span>'
            f'<span class="sync-step">{escape(step)}</span></div>'
            f'<div class="sync-bar" role="progressbar" aria-label="Sync progress" aria-valuemin="0" '
            f'aria-valuemax="100" aria-valuenow="{pct}"><i style="width:{pct}%"></i></div></div>')


def task_progress(title, fraction, step, found=()):
    """A progress bar inside a card (same look as the sync panel), with what's found so far below."""
    pct = round(max(0.0, min(1.0, fraction)) * 100)
    items = "".join(f"<li>{icon('check')}<span>{escape(x)}</span></li>" for x in found)
    return (f'<div class="task" role="status" aria-live="polite">'
            f'<div class="sync-top">{icon("progress_activity")}<span>{escape(title)}</span>'
            f'<span class="sync-step">{escape(step)}</span></div>'
            f'<div class="sync-bar" role="progressbar" aria-label="{escape(title)}" aria-valuemin="0" '
            f'aria-valuemax="100" aria-valuenow="{pct}"><i style="width:{pct}%"></i></div>'
            + (f'<ul class="task-found">{items}</ul>' if items else "") + '</div>')


def hour_label(hours):
    """22 -> '10 pm', 24 -> '12 am'."""
    h = int(round(hours)) % 24
    return f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"


def sleep_timeline(rows, label):
    """Bars on a shared night-time axis (hours where 25 = 1 am).
    rows: (name, start, end, detail_html, css_class[, hover text]). label describes it for screen readers."""
    lo = math.floor(min(r[1] for r in rows) - 0.25)
    lo -= lo % 2                                   # start and end on even hours...
    hi = math.ceil(max(r[2] for r in rows) + 0.25)
    hi += hi % 2
    hi += (hi - lo) % 4                            # ...so a tick lands every 4 hours, ends included
    span = hi - lo

    def pos(h):
        return (h - lo) / span * 100

    bars = "".join(
        f'<div class="tl-row"{tip_attr(tip[0] if tip else "")}><div class="tl-head"><span class="tl-name">{name}</span>'
        f'<span class="tl-detail">{detail}</span></div>'
        f'<div class="tl-track"><i class="{cls}" style="left:{pos(a):.1f}%; width:{pos(b) - pos(a):.1f}%"></i></div></div>'
        for name, a, b, detail, cls, *tip in rows)
    ticks = "".join(f'<span style="left:{pos(h):.1f}%">{hour_label(h)}</span>' for h in range(lo, hi + 1, 4))
    return f'<div class="tl" role="img" aria-label="{escape(label)}">{bars}<div class="tl-axis">{ticks}</div></div>'


def activity_icon(activity_type, sport):
    return TYPE_ICON.get(activity_type, SPORT_ICON.get(sport, "exercise"))


def distance_text(km, sport):
    if not km:
        return ""
    return f"{km * 1000:,.0f} m" if sport == "swim" else f"{km:.1f} km"


def speed_text(speed, sport):
    if speed is None or pd.isna(speed):
        return ""
    if sport == "run":
        return f"{pace(speed)} /km"
    if sport == "swim":
        return f"{pace(speed)} /100 m"
    if sport == "bike":
        return f"{speed:.1f} km/h"
    return ""


def activity_link(a, sport, show_tag=True):
    """One workout as a row that opens it in Garmin Connect."""
    ic = activity_icon(a["type"], sport)
    main = distance_text(a["distance_km"], sport) or dur_min(a["duration_min"])
    extra = dur_min(a["duration_min"]) if a["distance_km"] else ""
    if not pd.isna(a.get("calories")):
        extra += f'<span class="opt">{" · " if extra else ""}{num(a["calories"])} cal</span>'
    tag = EFFECT_NAME.get(a.get("effect_label") or "", "")
    tag_html = f'<span class="tag">{tag}</span>' if tag and show_tag else ""
    url = f"https://connect.garmin.com/modern/activity/{int(a['id'])}"
    return (f'<a class="act" href="{url}" target="_blank" rel="noopener" title="Open in Garmin Connect">'
            f'<div class="tile">{icon(ic)}</div>'
            f'<div class="r-main"><div class="act-name">{escape(str(a["name"]))}</div>'
            f'<div class="r-sub">{day(a["date"], True)} · {hhmm(a["start_time"])}{tag_html}</div></div>'
            f'<div class="act-stats">{main}<div>{extra}</div></div>{icon("chevron_right", "chev")}</a>')

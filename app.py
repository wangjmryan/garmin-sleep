"""Fitness + sleep dashboard.  Run:  streamlit run app.py

What's where:
  app.py      - what goes on each tab (this file)
  insights.py - the calculations (sleep need, recovery check, training balance...)
  charts.py   - the charts
  ui.py       - colours, CSS, number formatting, small HTML pieces
  sync.py     - downloads data from Garmin into sleep.db
"""
import importlib
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import charts
import db
import food
import insights as I
import schedule
import ui

# Re-read the helper files on every refresh, so code changes show up without restarting the app
for module in (db, schedule, food, ui, I, charts):
    importlib.reload(module)
from db import (delete_meal, delete_weight, get_meta, load, load_classes, load_meals, load_sleep, load_weight,
                save_classes, save_meal, save_weight, set_meta)
from ui import (card, card_head, chip, clock, clock_range, day, dur, dur_min, hhmm, html, icon,
                join_words, meter_row, notice, num, row, strip)

st.set_page_config(page_title="Fitness", page_icon=":material/monitor_heart:", layout="wide")
ui.inject_css()


# ---------- Data ----------
@st.cache_data
def load_all():
    return {"sleep": load_sleep(), "daily": load("daily"), "hrv": load("hrv"), "vo2": load("vo2"),
            "acts": load("activities", order="date, start_time"), "weight": load_weight(),
            "classes": load_classes(), "meals": load_meals()}


data = load_all()
sleep, daily_all, hrv, vo2, acts, weights, classes, meals = (
    data[k] for k in ("sleep", "daily", "hrv", "vo2", "acts", "weight", "classes", "meals"))
now = datetime.now()
today = now.date()
END = pd.Timestamp(today)
# The day the watch last synced is only partly recorded (unless it's today), so leave it out
daily = daily_all
if not daily.empty and daily["date"].max().date() < today:
    daily = daily[daily["date"] < daily["date"].max()]
acts = I.with_sport(acts)


def sync_now(days):
    """Pull recent data from Garmin (showing a progress bar), then reload the page with it."""
    pill = st.empty()

    def show(fraction, step):
        pill.markdown(ui.sync_pill(fraction, step), unsafe_allow_html=True)

    show(0, "Starting")
    from sync import sync
    try:
        sync(days, progress=show)
        st.session_state.pop("sync_error", None)
    except (Exception, SystemExit) as e:  # offline, Garmin down, key expired...
        st.session_state["sync_error"] = str(e)
    pill.empty()
    st.cache_data.clear()
    st.rerun(scope="app")


def days_to_sync():
    newest = sleep["date"].max().date() if not sleep.empty else None
    return 30 if newest is None else max(7, min(365, (today - newest).days + 3))


def home_network_address():
    """This computer's address on your Wi-Fi (e.g. 192.168.1.23), or None if it isn't on one.
    Connecting a UDP socket sends nothing; it just makes Windows pick the network it would use."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def phone_panel():
    ip = home_network_address()
    if not ip:
        html('<div class="r-sub">This computer isn\'t on a Wi-Fi or wired network right now.</div>')
        return
    import segno
    url = f"http://{ip}:{st.get_option('server.port')}"
    qr = segno.make(url, error="m").svg_inline(border=0, omitsize=True,dark="#0d1015", light="#ffffff")
    html(f'<div class="phone-qr">{qr}</div>'
         f'<div class="phone-url">{url}</div>'
         '<ol class="phone-steps"><li>Point your phone\'s camera at the code and tap the link.</li>'
         '<li>Then use the browser\'s Share or ⋮ menu and choose <b>Add to Home Screen</b>, '
         'so it opens like an app next time.</li></ol>'
         '<div class="r-sub">Your phone needs to be on the same Wi-Fi, and this computer needs to be on '
         'with the dashboard open. Campus Wi-Fi often blocks this.</div>')


def request_sync():
    # The Sync button only sets this; the sync itself runs after the page is drawn (see auto_sync)
    st.session_state["sync_requested"] = True


# Keep data fresh without anyone pressing Sync: on open, and every 15 minutes while open
@st.fragment(run_every="15m")
def auto_sync():
    if st.session_state.pop("sync_requested", False):
        sync_now(days_to_sync())
    last = get_meta("last_sync")
    stale = not last or (datetime.now() - datetime.fromisoformat(last)).total_seconds() > 20 * 60
    if stale and not st.session_state.get("sync_error"):
        sync_now(days_to_sync())


def chart(name, figure, width="stretch"):
    """Draw a chart in a slot that already has the chart's height (set in ui.py), so the cards
    around it don't jump when it finishes drawing."""
    with st.container(key=f"chart_{name}"):
        st.altair_chart(figure, width=width)


# ---------- Header ----------
first = get_meta("first_name")
greeting = ("Still up" if now.hour < 5 else "Good morning" if now.hour < 12
            else "Good afternoon" if now.hour < 17 else "Good evening")
last_sync = get_meta("last_sync")
updated = f"updated {ui.ago(datetime.fromisoformat(last_sync), now)}" if last_sync else "not synced yet"
with st.container(key="header"):
    left, right = st.columns([6, 1], vertical_alignment="center")
    with left:
        html(f'<h1 class="h1">{greeting}{", " + first if first else ""}{"?" if now.hour < 5 else ""}</h1>'
             f'<div class="sub">{now:%a}, {now:%b} {now.day} · {updated}</div>')
    with right:
        with st.container(horizontal=True, gap="small", key="header_actions"):
            with st.container(key="phone_btn", width="content"):
                with st.popover("Phone", icon=":material/smartphone:", help="Open this dashboard on your phone"):
                    phone_panel()
            st.button("Sync", icon=":material/sync:", key="sync_btn", help="Get the latest data from Garmin",
                      on_click=request_sync)

if st.session_state.get("sync_error"):
    html(notice("<b>Couldn't reach Garmin.</b> Showing the data saved on this computer. "
                "Check your internet connection, then try Sync again.", "cloud_off"))

if sleep.empty:
    html(notice("<b>No data yet.</b> Tap <b>Sync</b> to download your sleep and training from Garmin.", "download"))
    auto_sync()
    st.stop()

TABS = ["TODAY", "SLEEP", "TRAINING", "FOOD", "WEIGHT"]
start_tab = st.query_params.get("tab", "today").upper()  # e.g. ?tab=sleep opens the Sleep tab
with st.container(key="nav"):
    tab = st.segmented_control("Section", TABS, default=start_tab if start_tab in TABS else "TODAY",
                               label_visibility="collapsed", key="tab") or "TODAY"

flash = st.session_state.pop("flash", None)  # "Saved..." message from the last action
if flash:
    st.toast(flash, icon=":material/check_circle:")

PERIODS = {"30 days": 30, "90 days": 90, "1 year": 365}


def period_picker():
    choice = st.segmented_control("Period", list(PERIODS), default=st.session_state.get("period_keep", "30 days"),
                                  label_visibility="collapsed", key="period") or "30 days"
    st.session_state["period_keep"] = choice
    return choice, PERIODS[choice]


# ================= TODAY =================
def today_tab():
    night = sleep.iloc[-1]
    night_day = night["date"].date()

    # Is anything missing? Say so plainly instead of quietly showing old data.
    watch_synced_today = not daily_all.empty and daily_all["date"].max().date() == today
    if night_day < today and now.hour >= 10:
        if watch_synced_today:
            html(notice("<b>No sleep recorded for last night.</b> Your watch synced today, but Garmin has no "
                        "sleep for last night. If you wore it to bed, check the Garmin Connect app."))
        else:
            html(notice("<b>Your watch hasn't synced today.</b> Open the Garmin Connect app on your phone, "
                        "then tap Sync here."))

    # After midnight, "tonight" is the night you're already in
    night_of = today - timedelta(days=1) if now.hour < 5 else today
    t = I.tonight(sleep, night_of + timedelta(days=1), classes, wake_buffer())
    rec = I.recovery(sleep, hrv, daily, acts, END)

    left, right = st.columns(2)  # fixed columns: cards never jump between them while loading
    with left:  # split chosen so both columns end at about the same height
        last_night_card(night, night_day)
        tonight_card(t, night_of)
        week_card("desk-only")   # desktop: here, so the two columns end at about the same height
    with right:
        recovery_card(rec)
        workout_card(rec, t)
        week_card("phone-only")  # phone: last, after "should I push today?"


HELD_CHIP = {  # the parts of the night Garmin rated only Fair or Poor, as one-word chips
    "not enough sleep": "Short", "stress while asleep": "Stress", "waking up during the night": "Wakeful",
    "restless sleep": "Restless", "little deep sleep": "Low deep", "little REM sleep": "Low REM",
    "a lot of light sleep": "Light",
}


def last_night_card(night, night_day):
    before = sleep[sleep["date"] < night["date"]].tail(30)
    usual = before["sleep_score"].mean()
    score = night["sleep_score"]
    status, word = (("good", "Excellent") if score >= 90 else ("good", "Good") if score >= 80
                    else ("ok", "Fair") if score >= 60 else ("low", "Poor"))
    chips = chip(status, word) + "".join(chip("ok", HELD_CHIP.get(h, h.capitalize()), tip=f"Held back by {h}")
                                         for h in I.held_back_by(night))
    corner = ""
    if pd.notna(score - usual):  # no usual yet, or a night Garmin didn't score
        vs = round(score - usual)
        corner = (f'<div class="corner"><div class="k">vs usual</div><div class="v">'
                  f'{ui.delta(vs, str(abs(vs)), tip=f"Your usual is {usual:.0f}", small=1)}</div></div>')
    week = I.in_window(sleep, night["date"], 7)
    with st.container(key="card_night"):
        html(f'<div class="hero">{corner}<h2 class="h3">{I.night_name(night_day, today)}</h2>'
             f'<div class="figure">{score:.0f}<small>sleep score</small></div><div class="chips">{chips}</div>'
             f'<div class="hero-meta">{dur(night["total_sleep_hours"])} · '
             f'{clock_range(I.clock_hours(night["bedtime"]), I.clock_hours(night["wake_time"]))}</div></div>')
        chart("recent", charts.recent_scores(week, usual, night["date"] - pd.Timedelta(days=6), night["date"]),
                        width="stretch")


def tonight_card(t, night_of):
    """The best time to fall asleep tonight, and what it gets you compared with your usual."""
    need_h = t["need_min"] / 60
    now_h = now.hour + now.minute / 60 + (24 if night_of < today else 0)  # same scale as t: 1 am = 25
    best, latest, wake = t["best"], t["latest"], t["wake"]

    pill = ""
    if latest and best <= now_h <= latest:
        pill = f'<div class="now-pill">{icon("bedtime")}Bedtime now</div>'
    elif latest and latest < now_h < wake:
        pill = f'<div class="now-pill">{icon("bedtime")}Past bedtime</div>'
    elif 0 < best - now_h <= 3:
        pill = f'<div class="now-pill">{icon("schedule")}In {dur(best - now_h)}</div>'

    def span(a):
        return f"{clock_range(a, wake)} · <b>{dur(I.sleep_between(t, a))}</b>"

    gain = I.sleep_between(t, best) - I.sleep_between(t, t["usual_bed"])
    extra_sleep = f" {ui.delta(gain, dur(gain), tip='More sleep than your usual night')}" if gain >= 0.25 else ""
    bars = [("Best", best, wake, span(best) + extra_sleep, "best",
             f"Garmin's bedtime window ends {clock(latest)}" if latest else "")]
    if best < now_h < wake - 1:  # the best time has passed: show what's still possible
        bars.append(("Now", now_h, wake, span(now_h), "now", "If you fall asleep now"))
    bars.append(("Usual", t["usual_bed"], wake, span(t["usual_bed"]), "usual", f"Your usual {night_of:%A} night"))
    timeline = ui.sleep_timeline(bars, f"Asleep at {clock(best)} gives {dur(I.sleep_between(t, best))} of sleep; "
                                       f"your usual {clock(t['usual_bed'])} gives {dur(I.sleep_between(t, t['usual_bed']))}.")

    extra = t["extra_min"]
    if extra >= 10:
        need_tip = (f"{dur_min(extra)} above your usual {dur_min(t['base_min'])}"
                    + (f", because of {join_words(t['reasons'])}" if t["reasons"] else ""))
    else:
        need_tip = "Your usual need"
    if not t["fresh"]:
        need_tip += f" · Garmin's latest estimate ({day(t['estimate_from'])})"
    need = dur(need_h) + (f" {ui.delta(extra, dur_min(extra), None)}" if extra >= 10 else "")
    fc = t["first_class"]
    wake_tip = (f"{wake_buffer()} min before {class_name(fc)} at {clock(fc['start'])}" if fc
                else f"Your usual on {t['wake_day']:%A}s" + (" (no class)" if classes else ""))
    tiles = strip([(need, "Sleep need", need_tip), (clock(wake), "Wake-up", f"{t['wake_day']:%A}: {wake_tip}")])
    html(card(card_head("Tonight") + f'<div class="plan">Bed by <b>{clock(best)}</b></div>' + pill + timeline + tiles))


def workout_card(rec, t):
    """One suggested workout: how hard, which sport, how long and when to finish."""
    level = rec["level"]
    now_h = now.hour + now.minute / 60
    when = "Today"
    p = I.workout_plan(acts, level, today, t["best"])
    if p and p["kind"] in ("easy", "hard") and now_h + p["main"]["minutes"] / 60 > p["finish_by"]:
        when = "Tomorrow"  # too late to fit it in before bed, so plan tomorrow
        p = I.workout_plan(acts, level, today + timedelta(days=1), t["best"])
    elif p and p["kind"] == "rest" and now_h >= 20:
        when = "Tomorrow"
        p = I.workout_plan(acts, level, today + timedelta(days=1), t["best"])
    if not p:
        return

    rows, chips, why = "", "", p.get("why", [])
    if p["kind"] == "done":
        ic, plan = "task_alt", "Done for today"
        chips = "".join(ui.pill(ui.SPORT_ICON[a["sport"]], f"{ui.SPORT_NAME[a['sport']]} {dur_min(a['duration_min'])}")
                        for _, a in p["done"].iterrows())
        how = "Eat well and get to bed on time."
    elif p["kind"] == "rest":
        ic, plan = "self_improvement", "Rest day"
        chips = ui.pill("directions_walk", "Walk 20–30 min", tip="Optional, at an easy pace")
        how = "Skip training, or go for an easy 20–30 min walk. Your body gets fitter while it recovers."
    else:
        m = p["main"]
        ic, plan = ui.SPORT_ICON[m["sport"]], f'{m["name"]} <b>{m["minutes"]} min</b>'
        timing = ("Hard efforts in the 2 hours before bed can make it harder to fall asleep." if p["kind"] == "hard"
                  else "Finish an hour before bed so you can wind down.")
        late = p["usual_start"] and p["usual_start"] + m["minutes"] / 60 > p["finish_by"]
        if late:
            timing += f" You usually start around {clock(p['usual_start'])}, so go earlier if you can."
        chips = ui.pill("schedule", f"by {clock(p['finish_by'])}", "ok" if late else "neutral", tip=timing)
        how = f"{m['how']} {timing}"
        if p["kind"] == "easy" and m["sport"] in ("run", "bike") and p["hr_limit"]:
            chips += ui.pill("favorite", f"under {p['hr_limit']} bpm", tip="Heart-rate zone 2")
            how += f" Keep your heart rate under about {p['hr_limit']} bpm (zone 2)."
        why = p["why"][:3] + ([(ui.SPORT_ICON[m["sport"]], p["sport_note"])] if p["sport_note"] else [])
        a = p["alt"]
        if a:
            alt_how = (f"Heart rate under about {p['hr_limit']} bpm" if p["kind"] == "easy" and a["sport"] != "swim"
                       and p["hr_limit"] else a["how"])
            rows = row(f"Or {a['name'].lower()}", f"{a['minutes']} min", tip=alt_how,
                       lead=f'<div class="tile">{icon(ui.SPORT_ICON[a["sport"]])}</div>')
    foot = "The app's suggestion from your recovery, recent workouts and training balance."
    if when == "Tomorrow" and p["kind"] != "done":
        foot = "It's late to train today, so this is for tomorrow. It updates after tonight's sleep syncs. " + foot
    reasons = "".join(f"<li>{icon(i)}<span>{text}</span></li>" for i, text in why)
    html(card(card_head("Workout", when)
              + f'<div class="plan-row"><div class="tile">{icon(ic)}</div><div class="plan">{plan}</div></div>'
              + f'<div class="chips">{chips}</div>' + (f'<div class="rows">{rows}</div>' if rows else "")
              + ui.more(f"<p>{how}</p>" + (f'<ul class="why">{reasons}</ul>' if reasons else "") + f"<p>{foot}</p>",
                        "Why?")))


SIGNAL_LABEL = {"hrv": "HRV", "rhr": "Resting HR", "load": "7-day load"}  # short names for the bars


def recovery_card(r):
    if not r["verdict"]:
        return
    status, title, text = r["verdict"]
    rows = "".join(ui.bullet_row(SIGNAL_LABEL.get(s["key"], s["label"]), s["value"], s["unit"], s["x"], s["band"],
                                 s["domain"], s["status"], tip=f'{s["label"]}: {s["note"]}') for s in r["signals"])
    notes = "".join(f'<li>{s["label"]}: {s["note"]}</li>' for s in r["signals"])
    html(card(card_head("Recovery") + ui.readiness_scale(r["level"], f"{title}. {text}")
              + f'<div class="rows">{rows}</div>'
              + ui.more(f"<p><b>{title}.</b> {text}</p><ul>{notes}</ul>"
                        "<p>Green shading is your normal range; the dot is today. It turns <b>Hard</b> when sleep, "
                        "HRV and resting heart rate all look normal. This is the app's own check: Garmin doesn't "
                        "share its Training Readiness score.</p>")))


def week_card(where=""):
    rs = I.recent_sleep(sleep, END, 7)
    d7 = I.in_window(daily, END, 7)
    a7 = I.in_window(acts, END, 7)
    rows = ""
    if rs:
        met = rs["avg_hours"] >= rs["avg_need"] - 0.25
        rows += meter_row("Sleep", dur(rs["avg_hours"]), f"/ {dur(rs['avg_need'])}", rs["avg_hours"] / rs["avg_need"],
                          status="good" if met else "",
                          tip=f"Average a night against your need. Met it on {rs['nights_met']} of {rs['nights']} nights")
    if not d7.empty:
        minutes = (d7["intensity_moderate"] + 2 * d7["intensity_vigorous"]).sum()
        rows += meter_row("Intensity minutes", num(minutes), "/ 150", minutes / 150,
                          status="good" if minutes >= 150 else "", tip="Vigorous minutes count double")
    by_sport = a7.groupby("sport")["duration_min"].sum() if not a7.empty else pd.Series(dtype=float)
    detail = " · ".join(f"{ui.SPORT_NAME[s]} {dur_min(m)}" for s, m in by_sport.items()) or "No workouts"
    rows += row("Workouts", str(len(a7)), "", sub=detail)
    html(card(card_head("Past 7 days") + f'<div class="rows">{rows}</div>', where))


# ================= SLEEP =================
def sleep_tab():
    label, days = period_picker()
    cur = I.in_window(sleep, END, days)
    prev = I.in_window(sleep, END - pd.Timedelta(days=days), days)
    if cur.empty:
        html(notice("No sleep recorded in this period."))
        return

    avg = cur["sleep_score"].mean()
    status, word = (("good", "Good") if avg >= 80 else ("ok", "Fair") if avg >= 60 else ("low", "Poor"))
    need = cur.apply(I.need_hours, axis=1).mean()
    corner = ""
    before = prev["sleep_score"].mean() if len(prev) >= 5 else None
    if before is not None and pd.notna(avg - before):
        vs = round(avg - before)
        corner = (f'<div class="corner"><div class="k">vs previous</div><div class="v">'
                  f'{ui.delta(vs, str(abs(vs)), tip=f"Previous {label}: {before:.0f}", small=1)}</div></div>')
    wake = cur["wake_time"].map(I.clock_hours).mean()
    html(card(f'<div class="hero">{corner}<h2 class="h3">Sleep score</h2>'
              f'<div class="figure">{avg:.0f}<small>avg</small></div><div class="chips">{chip(status, word)}</div>'
              f'<div class="hero-note">{len(cur)} nights</div></div>'
              + strip([(dur(cur["total_sleep_hours"].mean()), "Asleep", f"Average a night; your need is about {dur(need)}"),
                       (clock(cur["bedtime_hours"].mean()), "Bedtime", "When you usually fall asleep"),
                       (clock(wake), "Wake-up", "When you usually wake up")])))

    left, right = st.columns(2)  # fixed columns: cards never jump between them while loading
    with left:
        with st.container(key="card_nightly"):
            html('<div class="inset">' + card_head("Night by night") + '</div>')
            first_day = END - pd.Timedelta(days=days - 1)
            chart("hours", charts.nightly_hours(cur, need, first_day, END), width="stretch")
            chart("scores", charts.nightly_scores(cur, first_day, END), width="stretch")
        stages_card(cur, first_day)
        drivers_card(cur, label)
    with right:
        bedtime_card()
        week_card_sleep()


STAGE_INK = {"Deep": "#ffffff", "Light": "#0b0b0b", "REM": "#0b0b0b"}  # readable text on each colour
STAGE_MEANING = {"Deep": "body repair and recovery", "Light": "most of the night", "REM": "memory and mood"}


def stages_card(cur, first_day):
    """Average split of deep, light and REM sleep, then the same night by night."""
    s = I.stage_summary(cur)
    if not s:
        return
    weakest = min((n for n in s if s[n]["good"] is not None), key=lambda n: s[n]["good"], default=None)
    if weakest and s[weakest]["good"] >= 0.8:
        weakest = None

    def tip(n, v):
        text = f"{n}: {v['share']:.0%}, {dur(v['hours'])} a night"
        if v["good"] is not None:
            text += f", rated good on {v['good']:.0%} of nights"
        if n == weakest:
            text += (f". {n} ({STAGE_MEANING[n]}) is the stage Garmin most often rates below good."
                     + (" REM comes mostly late in the night, so short nights cut it first." if n == "REM" else ""))
        return text

    blocks = "".join(
        f'<div style="flex:{v["share"]}; background:{charts.STAGE_COLORS[n]}; color:{STAGE_INK[n]}"'
        f'{ui.tip_attr(tip(n, v))}>{v["share"]:.0%}</div>' for n, v in s.items())
    legend = "".join(
        f'<span{ui.tip_attr(tip(n, v))}><i class="key" style="background:{charts.STAGE_COLORS[n]}"></i><b>{n}</b></span>'
        for n, v in s.items())
    flag = (f'<div class="chips">{chip("ok", f"{weakest} often low", tip=tip(weakest, s[weakest]))}</div>'
            if weakest else "")
    with st.container(key="card_stages"):
        html('<div class="inset">' + card_head("Sleep stages", "average")
             + f'<div class="seg" role="img" aria-label="'
             + ", ".join(f'{n} {v["share"]:.0%}' for n, v in s.items()) + f'">{blocks}</div>'
             + f'<div class="legend">{legend}</div>{flag}</div>')
        chart("stages", charts.nightly_stages(cur, first_day, END), width="stretch")


CLASS_KIND = {"LEC": "lecture", "TUT": "tutorial", "LAB": "lab", "SEM": "seminar", "TST": "test"}


def class_name(c):
    """'MATH 101 lecture'"""
    return f"{c['course']} {CLASS_KIND.get(c['component'], '').strip()}".strip()


def save_schedule():
    found = schedule.parse(st.session_state.get("sched_text", ""))
    if not found:
        st.session_state["flash"] = "Couldn't find any class times in that. Copy the whole class schedule from your student portal."
        return
    save_classes(found)
    st.session_state["flash"] = f"Saved {len(found)} class times"
    st.session_state["sched_text"] = ""
    st.cache_data.clear()


def clear_schedule():
    save_classes([])
    st.session_state["flash"] = "Removed your class schedule"
    st.cache_data.clear()


def wake_buffer():
    """Minutes between waking up and your first class (set on the Sleep tab)."""
    try:
        return int(get_meta("wake_buffer", schedule.WAKE_BEFORE_MIN))
    except ValueError:
        return schedule.WAKE_BEFORE_MIN


def save_buffer():
    set_meta("wake_buffer", st.session_state["buffer"])
    st.cache_data.clear()


def week_card_sleep():
    """The next 7 days: first class, wake-up, and when to be asleep the night before."""
    buffer = wake_buffer()
    start = today if now.hour >= 5 else today - timedelta(days=1)
    plan = I.week_plan(sleep, classes, start, buffer_min=buffer)
    with st.container(key="card_week"):
        rows = ""
        for i, p in enumerate(plan):
            fc = p["first_class"]
            tip = ((f"{class_name(fc)} at {clock(fc['start'])} · up {clock(p['wake'])}" if fc
                    else f"No class · usually up {clock(p['wake'])}") + f" · asleep by this on {p['night']:%A} night")
            label = (f"{p['morning']:%a}" + (f'{icon("school")}<small>{clock(fc["start"])}</small>' if fc else "")
                     + ('<span class="tag accent">Tomorrow</span>' if i == 0 else ""))
            rows += row(label, clock(p["asleep_by"]), value_cls="accent" if i == 0 else "", tip=tip)
        html('<div class="inset">' + card_head("Your week", f"bed by · {dur(plan[0]['need'])} sleep")
             + f'<div class="rows tight">{rows}</div></div>')
        end = schedule.term_end(classes)
        with st.expander("Class schedule", expanded=not classes):
            if classes:
                st.number_input("Wake up before first class (min)", min_value=10, max_value=180,
                                value=buffer, step=5, key="buffer", on_change=save_buffer)
            st.text_area("Paste your schedule", key="sched_text", height=140,
                         placeholder="In your student portal, open your class schedule (List View), select everything, copy, and paste it here.")
            c1, c2 = st.columns(2)
            c1.button("Save schedule", type="primary", on_click=save_schedule, width="stretch")
            if classes:
                c2.button("Remove schedule", on_click=clear_schedule, width="stretch")
            if end:
                html(f'<div class="card-foot" style="margin-top:4px">{len(classes)} class times saved, '
                     f'running until {day(end)}.</div>')


def bedtime_card():
    """Weeknight bedtimes for each amount of sleep, with the score you usually get from it."""
    g = I.bedtime_guide(sleep, classes, today, wake_buffer())
    if not g:
        return
    need = round(I.need_hours(sleep.iloc[-1]))
    pick = max((r["hours"] for r in g["rows"] if r["hours"] <= need), default=None)
    usual = round(g["usual_hours"])
    rows = ""
    for r in g["rows"]:
        best = r["hours"] == pick
        hours = f'{r["hours"]}h{"+" if r["hours"] == 9 else ""}'
        label = (f'{clock(r["asleep_by"])}<small>{hours}</small>' + ('<span class="tag accent">Best</span>' if best else "")
                 + ('<span class="tag">Usual</span>' if r["hours"] == usual else ""))
        score = f'{ui.score_bar(r["score"])}{r["score"]:.0f}' if r["score"] is not None else "–"
        rows += row(label, score, value_cls="accent" if best else "",
                    tip=f'Asleep by {clock(r["asleep_by"])}: {hours} of sleep, average score '
                        + (f'{r["score"]:.0f}' if r["score"] is not None else "–") + f' over {r["nights"]} nights like this')
    days = "class days" if g["from_classes"] else "weeknights"
    html(card(card_head("Best bedtime", f'<span{ui.tip_attr(f"Your wake-up on {days}")}>up {clock(g["wake"])}</span>')
              + f'<div class="rows tight barlist">{rows}</div>'
              + ui.more("With a fixed wake-up, bedtime decides how long you sleep. Each bar is your average sleep "
                        f"score with that much sleep, on {days} when you're up at {clock(g['wake'])}. On weeknights you "
                        f"usually fall asleep around {clock(g['usual_bed'])} and get about {dur(g['usual_hours'])}.")))


def drivers_card(cur, label):
    # Needs plenty of nights to be trustworthy; fall back to your whole history if the period is short
    use, scope = (cur, f"the last {label}") if len(cur) >= 40 else (sleep, "all your nights")
    dr = I.sleep_drivers(use)
    if not dr:
        return
    slept, later = dr["per_hour_slept"], dr["per_hour_later"]
    later_words = ("barely changes it" if abs(later) < 2 else "changes it a little" if abs(later) < 4
                   else "changes it a lot")
    faded = " Faded bars rest on fewer than 5 nights." if (dr["by_length"]["nights"].between(1, 4)).any() else ""
    with st.container(key="card_drivers"):
        html('<div class="inset">' + card_head("Score by hours asleep", f'{dr["nights"]} nights') + '</div>')
        chart("bylength", charts.score_by_length(dr["by_length"]), width="stretch")
        html('<div class="inset">' + ui.more(
            f"Each extra hour of sleep adds about <b>{slept:+.0f} points</b>. Falling asleep an hour later with the "
            f"same amount of sleep {later_words} (<b>{later:+.0f}</b>). <b>How long</b> you sleep matters, not when. "
            f"From {scope}.{faded}") + '</div>')


# ================= TRAINING =================
def training_tab():
    if acts.empty:
        html(notice("No workouts yet. They'll appear after your next sync."))
        return
    week = I.in_window(acts, END, 7)
    lc = I.load_check(acts, END)

    # Past 7 days: what you did and how it compares
    by_sport = week.groupby("sport")["duration_min"].sum()
    # One chip per sport, only when there's more than one (otherwise it repeats the total)
    sports = ("".join(ui.pill(ui.SPORT_ICON[s], f"{ui.SPORT_NAME[s]} {dur_min(m)}") for s, m in by_sport.items())
              if len(by_sport) > 1 else "")
    load_rows = ""
    if lc:
        advice = {"good": "A steady build. Keep it up.",
                  "ok": "Big jumps make injury more likely. Build up gradually.",
                  "neutral": "An easier week. Fine if planned, or a chance to build."}[lc["status"]]
        arrow = "trending_down" if lc["ratio"] < 0.8 else "trending_up" if lc["ratio"] > 1.3 else "trending_flat"
        load_rows = ui.bullet_row("Training load", icon(arrow, lc["status"]) + num(lc["week"]), "", lc["week"],
                                  lc["band"], lc["domain"], lc["status"],
                                  tip=f"{lc['text']} {num(lc['usual'])} a week. {advice}")
    html(card(f'<div class="hero"><h2 class="h3">Past 7 days</h2>'
              f'<div class="figure">{dur_min(week["duration_min"].sum()) if len(week) else "0 min"}<small>training</small></div>'
              f'<div class="hero-meta">{len(week)} workout{"s" if len(week) != 1 else ""}</div>'
              + (f'<div class="chips">{sports}</div>' if sports else "")
              + f'</div><div class="rows" style="margin-top:14px">{load_rows}</div>'))

    latest_workout_card(acts.iloc[-1])

    html('<h2 class="h2">Trends</h2>')
    label, days = period_picker()
    cur = I.in_window(acts, END, days)
    prev = I.in_window(acts, END - pd.Timedelta(days=days), days)
    left, right = st.columns(2)  # fixed columns: cards never jump between them while loading
    with left:
        weekly = I.weekly_training(cur, END - pd.Timedelta(days=days - 1), END)
        avg_h = weekly.loc[weekly["week"] != I.week_start(END), "hours"].mean()
        with st.container(key="card_weekly"):
            html('<div class="inset">' + card_head("Weekly training", f"avg {dur(avg_h)}", level=3) + '</div>')
            chart("weekly", charts.weekly_hours(weekly, I.week_start(END)), width="stretch")
        movement_card(days)
    with right:  # split chosen so both columns end at about the same height
        sport_card(cur, prev, label)
        intensity_card(cur, label)
        fitness_card(days)
        workouts_card(cur)


EFFECT_MEANING = {
    "RECOVERY": "Easy effort that helps you recover",
    "BASE": "Builds your endurance base",
    "AEROBIC_BASE": "Builds your endurance base",
    "TEMPO": "Builds speed you can hold for a while",
    "LACTATE_THRESHOLD": "Raises the pace you can hold for a long time",
    "VO2MAX": "Boosts your top-end aerobic fitness",
    "ANAEROBIC_CAPACITY": "Builds power for short, hard efforts",
    "SPRINT": "Builds sprint speed",
}


def latest_workout_card(a):
    sport = a["sport"]
    stats = [(ui.distance_text(a["distance_km"], sport) or "–", "Distance"),
             (dur_min(a["duration_min"]), "Time")]
    totals = I.sport_totals(pd.DataFrame([a]))
    speed = totals[0]["speed"] if totals else None
    if sport in ("run", "swim", "bike") and speed:
        stats.append((ui.speed_text(speed, sport), "Pace" if sport != "bike" else "Speed"))
    stats.append((f'{num(a["avg_hr"])}<small>bpm</small>' if not pd.isna(a["avg_hr"]) else "–", "Avg HR"))
    cells = "".join(f'<div><div class="strip-v">{v}</div><div class="strip-k">{k}</div></div>' for v, k in stats)
    effect = a.get("effect_label")
    tag = (f'<span class="tag"{ui.tip_attr(EFFECT_MEANING.get(effect, "") + f" · training load {num(a["training_load"])}")}>'
           f'{ui.EFFECT_NAME[effect]}</span>' if effect in ui.EFFECT_NAME else "")
    url = f"https://connect.garmin.com/modern/activity/{int(a['id'])}"
    html(card(card_head("Latest workout", f'<a class="accent" href="{url}" target="_blank" rel="noopener" '
                                          f'title="Open in Garmin Connect" style="text-decoration:none">'
                                          f'Garmin{icon("open_in_new")}</a>')
              + f'<div class="r" style="padding-bottom:0"{ui.tip_attr(f"{ui.SPORT_NAME[sport]} at {hhmm(a["start_time"])}")}>'
              + f'<div class="tile">{icon(ui.activity_icon(a["type"], sport))}</div>'
              + f'<div class="r-main"><div class="act-name">{ui.escape(str(a["name"]))}</div>'
              + f'<div class="r-sub">{day(a["date"], True)}{tag}</div></div></div>'
              + f'<div class="stats4">{cells}</div>'))


def sport_card(cur, prev, label):
    now_rows = {r["sport"]: r for r in I.sport_totals(cur)}
    before = {r["sport"]: r for r in I.sport_totals(prev)}
    if not now_rows:
        html(card(card_head("By sport", level=3) + '<div class="r-sub" style="margin-top:8px">No workouts in this period.</div>'))
        return
    rows = ""
    for sport, r in now_rows.items():
        speed = ui.speed_text(r["speed"], sport)
        change = ""
        b = before.get(sport)
        if speed and b and b["speed"] and r["sessions"] >= 2 and b["sessions"] >= 2:
            diff = r["speed"] - b["speed"]
            if sport == "bike":
                if abs(diff) >= 0.3:
                    change = ui.delta(diff, f"{abs(diff):.1f} km/h",
                                      tip=f"{'Faster' if diff > 0 else 'Slower'} than the previous {label}")
            elif abs(diff) >= 3:  # pace: fewer seconds is faster
                change = ui.delta(diff, f"{abs(diff):.0f} s", good_when_up=False,
                                  tip=f"{abs(diff):.0f} s {'slower' if diff > 0 else 'faster'} than the previous {label}")
        what = "pace" if sport in ("run", "swim") else "speed"
        sub = " · ".join(x for x in (ui.distance_text(r["km"], sport), speed) if x) + (f" {change}" if change else "")
        rows += row(ui.SPORT_NAME[sport], dur_min(r["minutes"]), sub=sub,
                    lead=f'<div class="tile">{icon(ui.SPORT_ICON[sport])}</div>',
                    tip=f'{r["sessions"]} session{"s" if r["sessions"] != 1 else ""}' + (f", average {what}" if speed else ""))
    html(card(card_head("By sport", level=3) + f'<div class="rows">{rows}</div>'))


def intensity_card(cur, label):
    mix = I.intensity_mix(cur)
    if not mix:
        return
    blocks = ""
    for name, m in mix.items():
        if m["share"] <= 0:
            continue
        text = f"{m['share']:.0%}" if m["share"] >= 0.12 else ""
        blocks += (f'<div style="flex:{m["share"]}; background:{ui.INTENSITY[name]}; color:{ui.INTENSITY_INK[name]}" '
                   f'title="{name}: {m["share"]:.0%}, {dur_min(m["minutes"])}">{text}</div>')
    zones = {"Easy": "zones 1–2", "Moderate": "zone 3", "Hard": "zones 4–5"}
    legend = "".join(f'<span title="{n}: {zones[n]} · {dur_min(m["minutes"])}"><i class="key" '
                     f'style="background:{ui.INTENSITY[n]}"></i><b>{n}</b></span>' for n, m in mix.items())
    legend += ('<span title="Endurance coaches aim for about 80% of training time at an easy effort">'
               '<i class="key mark"></i>Goal: 80% easy</span>')
    easy, hard = mix["Easy"]["share"], mix["Hard"]["share"]
    if easy >= 0.7:
        status, word, take = "good", "Mostly easy", "Mostly easy: a strong base. Add a few hard sessions to get faster."
    elif hard >= 0.5:
        status, word = "ok", "Mostly hard"
        take = ("<b>Most of your training time is hard.</b> Endurance coaches often aim for about 80% easy. "
                "Slowing some sessions down helps you recover and build endurance.")
    else:
        status, word, take = "neutral", "Mixed", "A mix of easy and hard. Endurance coaches often aim for about 80% easy."
    minutes = "; ".join(f"{n} ({zones[n]}) {dur_min(m['minutes'])}" for n, m in mix.items())
    html(card(card_head("Easy vs hard", f'<span class="{status}">{word}</span>', level=3)
              + f'<div class="seg" role="img" aria-label="Easy {easy:.0%}, hard {hard:.0%}, goal 80% easy">'
                f'{blocks}<i class="target" style="left:80%"></i></div>'
              + f'<div class="legend">{legend}</div>'
              + ui.more(f"<p>{take}</p><p>Time in each heart-rate zone during workouts, last {label}: {minutes}.</p>")))


def fitness_card(days):
    if vo2.empty:
        return
    latest = vo2.iloc[-1]
    span = max(days, 120)
    recent = I.in_window(vo2, END, span)
    change = latest["vo2max"] - recent.iloc[0]["vo2max"] if len(recent) >= 2 else 0
    since = f"since {day(recent.iloc[0]['date'])}"
    trend = ui.delta(round(change, 1), f"{abs(change):.1f}", small=0.29,
                     tip=f"Holding steady {since}" if abs(change) < 0.3 else f"{change:+.1f} {since}")
    with st.container(key="card_fitness"):
        html('<div class="inset">' + card_head("Fitness", f'<span{ui.tip_attr(f"Updated {day(latest["date"])}")}>'
                                                           'VO₂ max</span>', level=3)
             + '<div class="plan" style="margin-top:8px" title="VO₂ max estimates your aerobic fitness; '
               f'Garmin updates it after outdoor runs.">{latest["vo2max"]:.1f}{trend}</div></div>')
        if len(recent) >= 3:
            chart("vo2", charts.vo2_trend(recent), width="stretch")


def movement_card(days):
    # Full days only: today isn't over, so its steps and calories would pull the averages down
    cur = I.in_window(daily[daily["date"] < END], END - pd.Timedelta(days=1), days)
    if cur.empty:
        return
    hit = (cur["steps"] >= cur["step_goal"]).mean()
    goal = cur["step_goal"].dropna().iloc[-1] if cur["step_goal"].notna().any() else None
    with st.container(key="card_movement"):
        html('<div class="inset">' + card_head("Daily movement", "avg", level=3)
             + strip([(num(cur["steps"].mean()), "Steps", f"Goal hit on {hit:.0%} of days"),
                      (f'{num(cur["cal_active"].mean())}<small>cal</small>', "Active", "Active calories"),
                      (f'{num(cur["cal_total"].mean())}<small>cal</small>', "Burned", "Total calories burned")])
             + '</div>')
        weekly = days > 90  # a year of daily bars is too thin to read, so show weekly averages
        chart("steps", charts.daily_steps(cur, goal, END - pd.Timedelta(days=days), END - pd.Timedelta(days=1),
                                           weekly), width="stretch")
        if goal:  # bars that reach the dashed line hit the goal (they're orange too)
            html(f'<div class="inset legend"><span><i class="key dash"></i>Goal <b>{num(goal)}</b></span></div>')


def workouts_card(cur):
    items = cur.iloc[::-1]
    if items.empty:
        html(card(card_head("Workouts", "none", level=3)))
        return
    shown = items.head(12)
    links = "".join(ui.activity_link(a, a["sport"]) for _, a in shown.iterrows())
    more = (f'<div class="card-foot">{len(items) - len(shown)} more in Garmin Connect</div>'
            if len(items) > len(shown) else "")
    # The list opens on click: the latest workout is already shown in full above
    html(card(f'<details class="list"><summary class="card-head"><h3 class="h3">Workouts</h3>'
              f'<span class="card-aside">{len(items)}{icon("expand_more")}</span></summary>'
              f'<div class="rows">{links}</div>{more}</details>'))


# ================= WEIGHT =================
UNITS = {"lb": 2.20462, "kg": 1.0}  # weights are saved in kg; this converts for display


def weight_unit():
    unit = get_meta("weight_unit", "lb")
    return unit if unit in UNITS else "lb"


def weight_tab():
    w = I.weight_series(weights) if not weights.empty else weights
    unit = weight_unit()
    c = I.calorie_needs(daily, acts, today)
    left, right = st.columns(2)  # fixed columns: cards never jump between them while loading
    with left:
        weight_card(w, unit)
        weight_trend_card(w, unit)
    with right:
        burn_card(c)
        if c:
            eat_card(c, unit)


def save_weight_entry():
    unit = weight_unit()
    value, when = st.session_state[f"w_val_{unit}"], st.session_state["w_date"]
    save_weight(when.isoformat(), value / UNITS[unit])
    st.session_state["flash"] = f"Saved {value:.1f} {unit} for {'today' if when == today else day(when)}"
    st.cache_data.clear()


def delete_weight_entry(date_text, label):
    delete_weight(date_text)
    st.session_state["flash"] = f"Deleted {label}"
    st.cache_data.clear()


def set_unit():
    set_meta("weight_unit", st.session_state["wunit"] or weight_unit())


def weight_card(w, unit):
    f = UNITS[unit]
    with st.container(key="card_weight"):
        if w.empty:
            html('<div class="hero"><h2 class="h3">Weight</h2><div class="figure">–</div>'
                 '<div class="hero-meta">Log your first weigh-in below.</div></div>')
        else:
            latest = w.iloc[-1]
            rate = I.weight_rate(w, END)
            trend = ""  # weight going up or down is neither good nor bad by itself, so the arrow stays grey
            if rate is not None:
                steady = abs(rate) < 0.1
                trend = ui.delta(0 if steady else rate, f"{abs(rate) * f:.1f} {unit}/wk", None,
                                 tip="Steady over the last 4 weeks" if steady else
                                 f"{'Losing' if rate < 0 else 'Gaining'} about {abs(rate) * f:.1f} {unit} a week")
            elif len(w) >= 2:
                diff, before = (latest["kg"] - w.iloc[-2]["kg"]) * f, day(w.iloc[-2]["date"])
                trend = ui.delta(0 if abs(diff) < 0.05 else diff, f"{abs(diff):.1f} {unit}", None,
                                 tip=f"Same as {before}" if abs(diff) < 0.05 else f"{diff:+.1f} {unit} since {before}")
            days_ago = (END - latest["date"]).days
            logged = ("Today" if days_ago == 0 else "Yesterday" if days_ago == 1
                      else day(latest["date"]) + (f" · {days_ago} days ago" if days_ago > 7 else ""))
            html(f'<div class="hero"><h2 class="h3">Weight</h2>'
                 f'<div class="figure">{latest["kg"] * f:.1f}<small>{unit}</small></div>'
                 + (f'<div class="chips">{trend}</div>' if trend else "")
                 + f'<div class="hero-note{" ok" if days_ago > 7 else ""}">{logged}</div></div>')
        st.segmented_control("Units", list(UNITS), default=unit, key="wunit", label_visibility="collapsed",
                             on_change=set_unit)
        default = round(float(w.iloc[-1]["kg"]) * f, 1) if not w.empty else round(70.0 * f, 1)
        with st.container(key="logform"):
            with st.form("log_weight", border=False, enter_to_submit=True):
                c1, c2, c3 = st.columns([1.1, 1.1, 0.8], vertical_alignment="bottom")
                # One input per unit, so switching units starts from a sensible number
                c1.number_input(f"Weight ({unit})", min_value=float(round(25 * f)), max_value=float(round(300 * f)),
                                value=default, step=0.1, format="%.1f", key=f"w_val_{unit}")
                c2.date_input("Day", value=today, max_value=today, format="YYYY-MM-DD", key="w_date")
                c3.form_submit_button("Save", type="primary", width="stretch", on_click=save_weight_entry,
                                      help="Saving a day again replaces it. Weigh in first thing in the morning "
                                           "for the steadiest numbers.")


def weight_trend_card(w, unit):
    if w.empty:
        return
    f = UNITS[unit]
    with st.container(key="card_wtrend"):
        html('<div class="inset">' + card_head("Trend") + '</div>')
        ranges = [*PERIODS, "All"]
        saved = st.session_state.get("wperiod_keep", "90 days")
        choice = st.segmented_control("Range", ranges, default=saved if saved in ranges else "90 days",
                                      label_visibility="collapsed", key="wperiod") or "90 days"
        st.session_state["wperiod_keep"] = choice
        # The chart always covers exactly the range you picked
        if choice == "All":
            start, cur = min(w["date"].min(), END - pd.Timedelta(days=29)), w
        else:
            start = END - pd.Timedelta(days=PERIODS[choice] - 1)
            cur = w[w["date"] >= start]
        if cur.empty:
            html(f'<div class="inset"><div class="empty">No weigh-ins in the last {choice}</div></div>')
        else:
            # A 7-day average only makes sense with regular weigh-ins (the chart's hover says which line is which)
            smooth = len(cur) >= 7 and cur["date"].diff().dt.days.median() <= 3
            chart("weight", charts.weight_trend(cur, start, END, unit, f, smooth), width="stretch")

        with st.expander("Recent weigh-ins"), st.container(key="wrecent"):
            for _, e in w.iloc[::-1].head(5).iterrows():
                older = w[w["date"] < e["date"]]
                diff = (e["kg"] - older.iloc[-1]["kg"]) * f if not older.empty else None
                change = "" if diff is None else "0.0" if abs(diff) < 0.05 else f"{diff:+.1f}"
                source = " · from Garmin" if e["source"] == "garmin" else ""
                label = f'{e["kg"] * f:.1f} {unit} on {day(e["date"])}'
                c1, c2 = st.columns([1, 0.12], vertical_alignment="center")
                with c1:
                    html(row(f'{e["kg"] * f:.1f} {unit}', change, unit if change else "",
                             sub=f'{day(e["date"], True)}{source}', value_cls="quiet"))
                with c2:
                    st.button("Delete", icon=":material/delete:", type="tertiary", key=f"del_{e['date']:%Y%m%d}",
                              help=f"Delete {label}", on_click=delete_weight_entry,
                              args=(e["date"].strftime("%Y-%m-%d"), label))


def burn_card(c):
    """What you burn: the daily average, and each of the last 30 days (workout days in orange)."""
    if not c:
        html(card(card_head("Calories you burn") + '<div class="empty">Needs a week of watch data</div>'))
        return
    d = I.burn_by_day(daily, acts, today, 30)
    with st.container(key="card_cal"):
        html('<div class="inset"><div class="hero"><h2 class="h3">Calories you burn</h2>'
             f'<div class="figure"{ui.tip_attr(f"Average of your last {c["days"]} full days, from your watch: about {num(c["resting"])} at rest, the rest from moving and workouts")}>'
             f'{num(c["avg"])}<small>a day</small></div></div></div>')
        if len(d) >= 3:
            chart("burn", charts.daily_burn(d, d["cal_total"].mean(), END - pd.Timedelta(days=30),
                                            END - pd.Timedelta(days=1)), width="stretch")
            kinds = [(ui.ACCENT, "Workout days", c["train"]), (charts.REST_GREY, "Rest days", c["rest"])]
            html('<div class="inset legend">'
                 + "".join(f'<span><i class="key" style="background:{color}"></i>{name}'
                           + (f' <b>{num(v)}</b>' if v else "") + '</span>' for color, name, v in kinds)
                 + '<span><i class="key dash"></i>Average</span></div>')


def eat_card(c, unit):
    saved = get_meta("weight_goal", "Maintain")
    saved = saved if saved in I.GOALS else "Maintain"
    with st.container(key="card_eat"):
        html('<div class="inset">' + card_head("How much to eat") + '</div>')
        goal = st.segmented_control("Goal", list(I.GOALS), default=saved, label_visibility="collapsed",
                                    key="goal") or saved
        if goal != saved:
            set_meta("weight_goal", goal)
        rate = I.GOALS[goal]

        def target(burn):
            return num(round(I.calorie_target(burn, rate) / 50) * 50)

        pace = "half a pound" if unit == "lb" else "0.25 kg"
        aim = {"Lose": f"To lose about {pace} a week", "Maintain": "To keep your weight steady",
               "Gain": f"To gain about {pace} a week"}[goal]
        cells = ([(f'{target(c["train"])}<small>cal</small>', "Workout days"),
                  (f'{target(c["rest"])}<small>cal</small>', "Rest days")] if c["train"] and c["rest"]
                 else [(f'{target(c["avg"])}<small>cal</small>', "A day")])
        text = f"{aim}: about {target(c['avg'])} a day on average."
        if goal == "Lose":
            text += " Keep the cut this small so training and recovery don't suffer."
        html('<div class="inset">' + strip(cells)
             + ui.more(f"<p>{text}</p><p>Your watch estimates calories from heart rate and movement, so treat these "
                       "as a starting point. If your weight trend doesn't match your goal after 2–3 weeks, adjust by "
                       "100–200 cal a day.</p>") + '</div>')


# ================= FOOD =================
NUTRIENTS = [("calories", "Calories", "cal"), ("protein_g", "Protein", "g"), ("carbs_g", "Carbs", "g"),
             ("fat_g", "Fat", "g"), ("fibre_g", "Fibre", "g"), ("sugar_g", "Sugar", "g")]


def food_tab():
    goal = get_meta("weight_goal", "Maintain")
    rate = I.GOALS.get(goal, 0.0)
    kg = float(weights.iloc[-1]["kg"]) if not weights.empty else None
    targets = I.food_targets(daily, acts, today, rate, kg)
    eaten = I.food_day(meals, today)
    left, right = st.columns(2)  # fixed columns: cards never jump between them while loading
    with left:  # on a phone this column comes first: totals, then adding a meal
        food_today_card(targets, eaten, goal)
        add_meal_card()
    with right:
        meals_card(eaten)


def food_today_card(targets, eaten, goal):
    if not targets:
        html(card(card_head("Today") + '<div class="empty">Targets need a week of watch data</div>'))
        return
    left_cal = targets["calories"] - eaten["calories"]
    big = (f'{num(left_cal)}<small>cal left</small>' if left_cal >= 0 else f'{num(-left_cal)}<small>cal over</small>')
    kind = "Workout day" if targets["trained"] else "Rest day"
    rows = meter_row("Eaten", num(eaten["calories"]), f"/ {num(targets['calories'])} cal",
                     eaten["calories"] / targets["calories"], status="good" if 0 <= left_cal <= 150 else "")
    for key, name in (("protein", "Protein"), ("carbs", "Carbs"), ("fat", "Fat")):
        rows += meter_row(name, num(eaten[key]), f"/ {num(targets[key])} g", eaten[key] / targets[key],
                          status="good" if eaten[key] >= targets[key] * 0.9 else "")
    extra = (f'Fibre <b>{num(eaten["fibre"])}</b> / {targets["fibre"]} g · Sugar <b>{num(eaten["sugar"])}</b> g'
             if eaten["calories"] else "")
    html(card(f'<div class="hero"><h2 class="h3">Today</h2><div class="figure">{big}</div><div class="chips">'
              + ui.pill("fitness_center" if targets["trained"] else "self_improvement", kind,
                        tip=f"{kind} target for your goal ({goal.lower()})")
              + f'</div></div><div class="rows" style="margin-top:14px">{rows}</div>'
              + (f'<div class="r-sub" style="margin-top:2px">{extra}</div>' if extra else "")
              + ui.more(f"<p>Your {kind.lower()} target is {num(targets['calories'])} cal for your goal "
                        f"({goal.lower()}). Targets come from what your watch says you burn (change the goal on the "
                        "Weight tab). Workout days switch on once your workout syncs. Protein 1.6 g and carbs 5–6 g "
                        "per kg of body weight suit endurance training.</p>", "How targets work")))


def meals_card(eaten):
    m = eaten["meals"]
    with st.container(key="card_meals"):
        html('<div class="inset">' + card_head("Meals today", str(len(m)) if len(m) else "") + '</div>')
        if m.empty:
            html('<div class="inset"><div class="empty">No meals yet</div></div>')
            return
        with st.container(key="mealrows"):
            for _, r in m.sort_values("time").iterrows():
                c1, c2 = st.columns([1, 0.12], vertical_alignment="center")
                with c1:
                    macros = f'P {num(r["protein_g"])} · C {num(r["carbs_g"])} · F {num(r["fat_g"])} g'
                    html(row(ui.escape(str(r["name"])), num(r["calories"]), "cal",
                             sub=f'{r["meal"]} · {hhmm(r["time"])} · {macros}'))
                with c2:
                    st.button("Delete", icon=":material/delete:", type="tertiary", key=f"delmeal_{r['id']}",
                              help=f"Delete {r['name']}", on_click=delete_meal_entry, args=(r["id"], r["name"]))


def delete_meal_entry(meal_id, name):
    delete_meal(meal_id)
    st.session_state["flash"] = f"Deleted {name}"
    st.cache_data.clear()


def save_meal_entry():
    p = st.session_state.pop("pending")
    n = p["n"]
    meal = {"date": today.isoformat(), "time": now.strftime("%H:%M"), "meal": st.session_state.get(f"f_slot_{n}") or
            I.meal_slot(now.hour), "name": st.session_state.get(f"f_name_{n}") or "Meal"}
    for key, _, _ in NUTRIENTS:
        meal[key] = float(st.session_state.get(f"f_{key}_{n}", 0) or 0)
    save_meal(meal)
    st.session_state["flash"] = f"Logged {meal['name']} ({num(meal['calories'])} cal)"
    st.cache_data.clear()


def start_manual():
    st.session_state["pending"] = {"n": st.session_state.get("pending_n", 0) + 1, "name": "", "items": [],
                                   "notes": "", **{k: 0.0 for k, _, _ in NUTRIENTS}}
    st.session_state["pending_n"] = st.session_state["pending"]["n"]


def add_meal_card():
    with st.container(key="card_addmeal"):
        pending = st.session_state.get("pending")
        if pending:
            review_meal(pending)
            return
        html('<div class="inset">' + card_head("Add a meal") + '</div>')
        if not food.has_key():
            html('<div class="inset"><div class="notice" style="background:var(--card-2); margin-top:10px">'
                 f'{icon("key")}<div><b>Photo estimates need a free Gemini key.</b></div></div>'
                 + ui.more('Get a free key at <a class="accent" href="https://aistudio.google.com/apikey" '
                           'target="_blank" rel="noopener">aistudio.google.com/apikey</a>, run '
                           '<code>setx GEMINI_API_KEY "your-key"</code> in a terminal, then close and reopen the '
                           'dashboard. Until then you can enter meals by hand.', "Set it up") + '</div>')
        with st.container(key="mealform"):
            # Several photos are fine: each dish, or one plate from a few angles
            photos = st.file_uploader("Photos", type=["jpg", "jpeg", "png", "webp", "heic"],
                                      accept_multiple_files=True, disabled=not food.has_key())
            note = st.text_input("Describe it", placeholder="e.g. chicken burrito, large, and a coke",
                                 disabled=not food.has_key())
            c1, c2 = st.columns(2)
            go = c1.button("Estimate", type="primary", icon=":material/auto_awesome:", width="stretch",
                           disabled=not food.has_key())
            c2.button("Enter by hand", on_click=start_manual, width="stretch")
            busy = st.empty()  # the "Estimating…" line goes here, right under the buttons
        if go:
            try:
                meal = estimate_with_progress(busy, [(p.getvalue(), p.type or "image/jpeg") for p in photos or []],
                                              note)
            except food.FoodError as e:
                busy.empty()
                html(notice(f"<b>Couldn't estimate that.</b> {ui.escape(str(e))}", "error"))
                return
            n = st.session_state.get("pending_n", 0) + 1
            st.session_state["pending_n"] = n
            st.session_state["pending"] = {"n": n, "name": meal.name, "notes": meal.notes,
                                           "items": [(i.name, i.calories) for i in meal.items],
                                           "calories": meal.calories, "protein_g": meal.protein_g,
                                           "carbs_g": meal.carbs_g, "fat_g": meal.fat_g, "fibre_g": meal.fibre_g,
                                           "sugar_g": meal.sugar_g}
            st.rerun()
        html('<div class="inset">' + ui.more(
            "Photos go to Google's Gemini to be estimated and aren't saved here. On the free tier, Google may use them "
            "to improve its products. Estimates can be off by 20% or more, so fix anything that looks wrong. You can "
            "add several photos: each dish, or one plate from a few angles.", "Privacy") + '</div>')


def estimate_with_progress(slot, images, note):
    """Run food.estimate in the background and keep a progress bar moving in `slot` meanwhile.
    Gemini doesn't say how far along it is, so the bar eases forward while it's thinking, then
    follows the answer as it streams in, listing each food as Gemini names it."""
    import concurrent.futures
    import math
    import re
    import time

    state = {"step": "send", "text": "", "since": time.time()}

    def report(step, detail=""):
        if step != state["step"]:
            state["since"] = time.time()
        state["step"], state["text"] = step, detail

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    job = pool.submit(food.estimate, images, note, report, st.session_state.get("gemini_model"))
    shown = 0.0
    while True:
        waited = time.time() - state["since"]
        step, text = state["step"], state["text"]
        if step == "shrink":
            target, label = 0.05, "Shrinking photos"
        elif step == "read":
            # The answer is ~500-900 characters of JSON; 0.7 → 0.97 as it arrives
            target, label = 0.7 + 0.27 * (1 - math.exp(-len(text) / 450)), "Reading the answer"
        else:
            # Waiting on Gemini (usually 2–6 s): ease 0.08 → 0.7, never quite stopping
            target = 0.08 + 0.62 * (1 - math.exp(-waited / 3.5))
            label = "Trying another model" if step == "retry" else ("Looking at your photos" if images
                                                                    else "Working it out")
        shown = max(shown, target)  # never slide backwards
        found = re.findall(r'"name"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"calories"', text)
        with slot:
            html(ui.task_progress("Estimating your meal", shown, label, found))
        if job.done():
            break
        time.sleep(0.15)
    pool.shutdown()
    meal = job.result()  # re-raises FoodError from the background thread
    st.session_state["gemini_model"] = food.last_model
    with slot:
        html(ui.task_progress("Estimating your meal", 1.0, "Done", [i.name for i in meal.items]))
    return meal


def review_meal(p):
    n = p["n"]
    items = "".join(f"<li>{icon('restaurant')}<span>{ui.escape(name)} · {num(cal)} cal</span></li>"
                    for name, cal in p["items"])
    html('<div class="inset">' + card_head("Check and save")
         + (f'<ul class="why">{items}</ul>' if items else "")
         + (f'<div class="r-sub" style="margin-top:6px">{ui.escape(p["notes"])}</div>' if p["notes"] else "")
         + '</div>')
    with st.container(key="reviewform"):
        st.text_input("Name", value=p["name"], key=f"f_name_{n}", placeholder="e.g. Oatmeal with banana")
        st.segmented_control("Meal", I.MEAL_SLOTS, default=I.meal_slot(now.hour), key=f"f_slot_{n}")
        cols = st.columns(3)
        for i, (key, label, unit) in enumerate(NUTRIENTS):
            cols[i % 3].number_input(f"{label} ({unit})", min_value=0.0, max_value=5000.0,
                                     value=float(round(p.get(key, 0) or 0)), step=10.0 if key == "calories" else 1.0,
                                     format="%.0f", key=f"f_{key}_{n}")
        c1, c2 = st.columns(2)
        c1.button("Save meal", type="primary", icon=":material/check:", on_click=save_meal_entry, width="stretch")
        c2.button("Discard", on_click=lambda: st.session_state.pop("pending", None), width="stretch")


# ---------- Page ----------
# Each tab draws into its own container. Switching tabs swaps the whole container at once, so the
# old tab's cards never linger next to the new tab's while it loads.
with st.container(key=f"page_{tab.lower()}"):
    if tab == "TODAY":
        today_tab()
    elif tab == "SLEEP":
        sleep_tab()
    elif tab == "TRAINING":
        training_tab()
    elif tab == "FOOD":
        food_tab()
    else:
        weight_tab()

auto_sync()

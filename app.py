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


def last_night_card(night, night_day):
    before = sleep[sleep["date"] < night["date"]].tail(30)
    usual = before["sleep_score"].mean()
    score = night["sleep_score"]
    status, word = (("good", "Excellent") if score >= 90 else ("good", "Good") if score >= 80
                    else ("ok", "Fair") if score >= 60 else ("low", "Poor"))
    held = I.held_back_by(night)
    note = (f"Held back by {join_words(held)}." if held
            else "Every part of your sleep rated Good or better.")
    week = I.in_window(sleep, night["date"], 7)
    with st.container(key="card_night"):
        html(f'<div class="hero"><div class="corner"><div class="k">Your usual</div><div class="v">{usual:.0f}</div></div>'
             f'<h2 class="h3">{I.night_name(night_day, today)}</h2>'
             f'<div class="figure">{score:.0f}<small>sleep score</small></div>{chip(status, word)}'
             f'<div class="hero-meta">{dur(night["total_sleep_hours"])} asleep · '
             f'{hhmm(night["bedtime"])} – {hhmm(night["wake_time"])}</div>'
             f'<div class="hero-note">{note}</div></div>')
        chart("recent", charts.recent_scores(week, usual, night["date"] - pd.Timedelta(days=6), night["date"]),
                        width="stretch")


def tonight_card(t, night_of):
    """The best time to fall asleep tonight, and what it gets you compared with your usual."""
    need_h = t["need_min"] / 60
    now_h = now.hour + now.minute / 60 + (24 if night_of < today else 0)  # same scale as t: 1 am = 25
    best, latest, wake = t["best"], t["latest"], t["wake"]
    evening_name = f"{night_of:%A} night"

    pill = ""
    if latest and best <= now_h <= latest:
        pill = f'<div class="now-pill">{icon("bedtime")}You\'re in your bedtime window now</div>'
    elif latest and latest < now_h < wake:
        pill = f'<div class="now-pill">{icon("bedtime")}Past your bedtime window</div>'
    elif 0 < best - now_h <= 3:
        pill = f'<div class="now-pill">{icon("schedule")}Bedtime in {dur(best - now_h)}</div>'

    def span(a):
        return f"{clock(a)} – {clock(wake)} · <b>{dur(I.sleep_between(t, a))}</b>"

    bars = [("Best", best, wake, span(best), "best")]
    if best < now_h < wake - 1:  # the best time has passed: show what's still possible
        bars.append(("If you fall asleep now", now_h, wake, span(now_h), "now"))
    bars.append((f"Your usual {evening_name}", t["usual_bed"], wake, span(t["usual_bed"]), "usual"))
    gain = I.sleep_between(t, best) - I.sleep_between(t, t["usual_bed"])
    timeline = ui.sleep_timeline(bars, f"Asleep at {clock(best)} gives {dur(I.sleep_between(t, best))} of sleep; "
                                       f"your usual {clock(t['usual_bed'])} gives {dur(I.sleep_between(t, t['usual_bed']))}.")
    sub = f"Latest {clock(latest)}, the end of Garmin's bedtime window" if latest else ""
    if gain >= 0.25:
        sub += f"{'. ' if sub else ''}That's {dur(gain)} more sleep than your usual {evening_name}."

    extra = t["extra_min"]
    if extra >= 10:
        need_sub = (f"{dur_min(extra)} above your usual {dur_min(t['base_min'])}"
                    + (f", because of {join_words(t['reasons'])}" if t["reasons"] else ""))
    else:
        need_sub = "Your usual need"
    if not t["fresh"]:
        need_sub += f" · Garmin's latest estimate ({day(t['estimate_from'])})"
    rows = row("Sleep need", dur(need_h), sub=need_sub)
    fc = t["first_class"]
    wake_sub = (f"{wake_buffer()} min before {class_name(fc)} at {clock(fc['start'])}" if fc
                else "Your usual on " + f"{t['wake_day']:%A}s" + (" (no class)" if classes else ""))
    rows += row(f"{t['wake_day']:%A} wake-up", clock(wake), sub=wake_sub)
    html(card(card_head("Tonight", evening_name)
              + f'<div class="plan">Best bedtime <b>{clock(best)}</b></div>'
              + (f'<div class="plan-sub">{sub}</div>' if sub else "") + pill + timeline
              + f'<div class="rows" style="margin-top:10px">{rows}</div>'))


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

    rows, foot = "", "The app's suggestion from your recovery, recent workouts and training balance."
    if p["kind"] == "done":
        did = join_words(f"a {dur_min(a['duration_min'])} {ui.SPORT_NAME[a['sport']].lower()}"
                         for _, a in p["done"].iterrows())
        body = (f'<div class="plan-row"><div class="tile">{icon("task_alt")}</div><div class="plan">Done for today</div></div>'
                f'<div class="body plan-note">You did {did} today. Eat well and get to bed on time.</div>')
    elif p["kind"] == "rest":
        body = (f'<div class="plan-row"><div class="tile">{icon("self_improvement")}</div><div class="plan">Rest day</div></div>'
                '<div class="body plan-note">Skip training, or go for an easy 20–30 min walk. '
                'Your body gets fitter while it recovers.</div>'
                + '<ul class="why">' + "".join(f"<li>{icon(ic)}<span>{t_}</span></li>" for ic, t_ in p["why"]) + "</ul>")
    else:
        m = p["main"]
        how = m["how"]
        if p["kind"] == "easy" and m["sport"] in ("run", "bike") and p["hr_limit"]:
            how += f" Keep your heart rate under about {p['hr_limit']} bpm (zone 2)."
        reasons = p["why"][:3] + ([(ui.SPORT_ICON[m["sport"]], p["sport_note"])] if p["sport_note"] else [])
        why = "".join(f"<li>{icon(ic)}<span>{text}</span></li>" for ic, text in reasons)
        body = (f'<div class="plan-row"><div class="tile">{icon(ui.SPORT_ICON[m["sport"]])}</div>'
                f'<div class="plan">{m["name"]} <b>{m["minutes"]} min</b></div></div>'
                f'<div class="body plan-note">{how}</div><ul class="why">{why}</ul>')
        hard = p["kind"] == "hard"
        timing = ("Hard efforts in the 2 hours before bed can make it harder to fall asleep." if hard
                  else "Finish an hour before bed so you can wind down.")
        if p["usual_start"] and p["usual_start"] + m["minutes"] / 60 > p["finish_by"]:
            timing += f" You usually start around {clock(p['usual_start'])}, so go earlier if you can."
        rows += row("Best time", f"by {clock(p['finish_by'])}", sub=timing,
                    lead=icon("schedule", "r-ic accent"))
        a = p["alt"]
        if a:
            alt_how = (f"Heart rate under about {p['hr_limit']} bpm" if p["kind"] == "easy" and a["sport"] != "swim"
                       and p["hr_limit"] else a["how"])
            rows += row(f"Or: {a['name'].lower()}", f"{a['minutes']} min", sub=alt_how,
                        lead=f'<div class="tile">{icon(ui.SPORT_ICON[a["sport"]])}</div>')
    if when == "Tomorrow" and p["kind"] != "done":
        foot = "It's late to train today, so this is for tomorrow. It updates after tonight's sleep syncs."
    html(card(card_head("Workout", when) + body + (f'<div class="rows">{rows}</div>' if rows else "")
              + f'<div class="card-foot">{foot}</div>'))


def recovery_card(r):
    if not r["verdict"]:
        return
    status, title, text = r["verdict"]
    rows = "".join(ui.bullet_row(s["label"], s["value"], s["unit"], s["x"], s["band"], s["domain"],
                                 s["status"], s["note"]) for s in r["signals"])
    html(card(card_head("Recovery", "Should you push today?")
              + f'<div class="statement">{title}</div>' + ui.readiness_scale(r["level"])
              + f'<div class="statement-text">{text}</div>'
              + f'<div class="rows">{rows}</div>'
              + '<div class="card-foot">Green shading is your normal range; the dot is today. It turns '
                '<b>Hard</b> when sleep, HRV and resting heart rate all look normal. This is the app\'s own '
                "check: Garmin doesn't share its Training Readiness score.</div>"))


def week_card(where=""):
    rs = I.recent_sleep(sleep, END, 7)
    d7 = I.in_window(daily, END, 7)
    a7 = I.in_window(acts, END, 7)
    rows = ""
    if rs:
        met = rs["avg_hours"] >= rs["avg_need"] - 0.25
        rows += meter_row("Sleep", dur(rs["avg_hours"]), f"/ {dur(rs['avg_need'])} need", rs["avg_hours"] / rs["avg_need"],
                          sub=f"Met your need on {rs['nights_met']} of {rs['nights']} nights",
                          status="good" if met else "")
    if not d7.empty:
        minutes = (d7["intensity_moderate"] + 2 * d7["intensity_vigorous"]).sum()
        rows += meter_row("Intensity minutes", num(minutes), "/ 150", minutes / 150,
                          sub="Vigorous minutes count double", status="good" if minutes >= 150 else "")
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
    corner = (f'<div class="corner"><div class="k">Previous {label}</div><div class="v">{prev["sleep_score"].mean():.0f}</div></div>'
              if len(prev) >= 5 else "")
    wake = cur["wake_time"].map(I.clock_hours).mean()
    html(card(f'<div class="hero">{corner}<h2 class="h3">Average sleep score</h2>'
              f'<div class="figure">{avg:.0f}</div>{chip(status, word)}'
              f'<div class="hero-meta">{len(cur)} nights recorded</div></div>'
              + strip([(dur(cur["total_sleep_hours"].mean()), f"Asleep a night<br>(need {dur(need)})"),
                       (clock(cur["bedtime_hours"].mean()), "Usually<br>asleep by"),
                       (clock(wake), "Usually<br>up at")])))

    left, right = st.columns(2)  # fixed columns: cards never jump between them while loading
    with left:
        with st.container(key="card_nightly"):
            html('<div class="inset">' + card_head("Night by night")
                 + '<div class="r-sub">Short nights pull the score down. Hover a night for details.</div></div>')
            first_day = END - pd.Timedelta(days=days - 1)
            chart("hours", charts.nightly_hours(cur, need, first_day, END), width="stretch")
            chart("scores", charts.nightly_scores(cur, first_day, END), width="stretch")
        stages_card(cur, label, first_day)
        drivers_card(cur, label)
    with right:
        bedtime_card()
        week_card_sleep()


STAGE_INK = {"Deep": "#ffffff", "Light": "#0b0b0b", "REM": "#0b0b0b"}  # readable text on each colour
STAGE_MEANING = {"Deep": "body repair and recovery", "Light": "most of the night", "REM": "memory and mood"}


def stages_card(cur, label, first_day):
    """Average split of deep, light and REM sleep, then the same night by night."""
    s = I.stage_summary(cur)
    if not s:
        return
    blocks = "".join(
        f'<div style="flex:{v["share"]}; background:{charts.STAGE_COLORS[n]}; color:{STAGE_INK[n]}" '
        f'title="{n}: {v["share"]:.0%}, {dur(v["hours"])} a night">{v["share"]:.0%}</div>' for n, v in s.items())
    rows = "".join(
        f'<span><i class="key" style="background:{charts.STAGE_COLORS[n]}"></i><b>{n}</b> {dur(v["hours"])}'
        + (f' · rated good {v["good"]:.0%} of nights' if v["good"] is not None else "") + "</span>"
        for n, v in s.items())
    weakest = min((n for n in s if s[n]["good"] is not None), key=lambda n: s[n]["good"], default=None)
    note = ""
    if weakest and s[weakest]["good"] < 0.8:
        note = (f"<b>{weakest}</b> ({STAGE_MEANING[weakest]}) is the stage Garmin most often rates below good. "
                + ("REM comes mostly late in the night, so short nights cut it first." if weakest == "REM" else ""))
    with st.container(key="card_stages"):
        html('<div class="inset">' + card_head("Sleep stages", f"average, last {label}")
             + f'<div class="seg" role="img" aria-label="'
             + ", ".join(f'{n} {v["share"]:.0%}' for n, v in s.items()) + f'">{blocks}</div>'
             + f'<div class="legend" style="flex-direction:column; gap:6px">{rows}</div>'
             + (f'<div class="body small" style="margin-top:12px">{note}</div>' if note else "") + '</div>')
        chart("stages", charts.nightly_stages(cur, first_day, END), width="stretch")
        html('<div class="inset card-foot" style="margin-top:0">Hours in each stage, night by night. '
             'Hover a bar for details.</div>')


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
        html('<div class="inset">' + card_head("Your week", f"asleep by, for {dur(plan[0]['need'])} of sleep")
             + '<div class="r-sub" style="margin-top:6px">'
             + ("Each day's first class and wake-up, and when to be asleep the night before. "
                "Days without class use your usual wake-up." if classes
                else "Add your class schedule below to plan wake-ups around your classes.")
             + '</div></div>')
        rows = ""
        for i, p in enumerate(plan):
            fc = p["first_class"]
            sub = (f"{class_name(fc)} at {clock(fc['start'])} · up {clock(p['wake'])}" if fc
                   else f"No class · usually up {clock(p['wake'])}")
            label = f"{p['morning']:%A}" + ('<span class="tag accent">Tomorrow</span>' if i == 0 else "")
            rows += row(label, clock(p["asleep_by"]), f"{p['night']:%a} night", sub=sub,
                        value_cls="accent" if i == 0 else "")
        html(f'<div class="inset"><div class="rows">{rows}</div></div>')
        if classes:
            with st.container(key="bufferbox"):
                st.number_input("Wake up this many minutes before your first class", min_value=10, max_value=180,
                                value=buffer, step=5, key="buffer", on_change=save_buffer)
        end = schedule.term_end(classes)
        with st.expander("Update class schedule" if classes else "Add your class schedule", expanded=not classes):
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
    rows = ""
    for r in g["rows"]:
        best = r["hours"] == pick
        label = f'Asleep by {clock(r["asleep_by"])}' + ('<span class="tag accent">Best</span>' if best else "")
        sleep_words = f'{r["hours"]}h{"+" if r["hours"] == 9 else ""} of sleep'
        score = f'{ui.score_bar(r["score"])}{r["score"]:.0f}' if r["score"] is not None else "–"
        rows += row(label, score, sub=f'{sleep_words} · {r["nights"]} nights like this',
                    value_cls="accent" if best else "")
    html(card(card_head("Best bedtime for you", f"Class days · up {clock(g['wake'])}" if g["from_classes"]
                        else f"Weeknights · up {clock(g['wake'])}")
              + '<div class="r-sub" style="margin-top:6px">With a fixed wake-up, bedtime decides how long you sleep. '
                'Each bedtime, and your average sleep score with that much sleep.</div>'
              + f'<div class="rows">{rows}</div>'
              + f'<div class="card-foot">On weeknights you usually fall asleep around {clock(g["usual_bed"])} '
                f'and get about {dur(g["usual_hours"])}.</div>'))


def drivers_card(cur, label):
    # Needs plenty of nights to be trustworthy; fall back to your whole history if the period is short
    use, scope = (cur, f"the last {label}") if len(cur) >= 40 else (sleep, "all your nights")
    dr = I.sleep_drivers(use)
    if not dr:
        return
    slept, later = dr["per_hour_slept"], dr["per_hour_later"]
    later_words = ("barely changes it" if abs(later) < 2 else "changes it a little" if abs(later) < 4
                   else "changes it a lot")
    with st.container(key="card_drivers"):
        html('<div class="inset">' + card_head("What drives your score")
             + f'<div class="body" style="margin-top:8px">Each extra hour of sleep adds about <b>{slept:+.0f} points</b>. '
             + f'Falling asleep an hour later with the same amount of sleep {later_words} '
             + f'(<b>{later:+.0f}</b>). <b>How long</b> you sleep matters, not when.</div></div>')
        chart("bylength", charts.score_by_length(dr["by_length"]), width="stretch")
        faded = " Faded bars rest on fewer than 5 nights." if (dr["by_length"]["nights"].between(1, 4)).any() else ""
        html(f'<div class="inset card-foot" style="margin-top:2px">Average score by hours asleep, from {scope} '
             f'({dr["nights"]} nights).{faded}</div>')


# ================= TRAINING =================
def training_tab():
    if acts.empty:
        html(notice("No workouts yet. They'll appear after your next sync."))
        return
    week = I.in_window(acts, END, 7)
    lc = I.load_check(acts, END)

    # Past 7 days: what you did and how it compares
    by_sport = week.groupby("sport")["duration_min"].sum()
    sports = "".join(f'<span class="chip neutral" style="margin:12px 4px 0">{icon(ui.SPORT_ICON[s])}'
                     f'{ui.SPORT_NAME[s]} {dur_min(m)}</span>' for s, m in by_sport.items())
    load_rows = ""
    if lc:
        advice = {"good": "A steady build. Keep it up.",
                  "ok": "Big jumps make injury more likely. Build up gradually.",
                  "neutral": "An easier week. Fine if planned, or a chance to build."}[lc["status"]]
        load_rows = ui.bullet_row("Training load", num(lc["week"]), "", lc["week"], lc["band"], lc["domain"],
                                  lc["status"], f"{lc['text']} {num(lc['usual'])} a week. {advice}")
    html(card(f'<div class="hero"><h2 class="h3">Past 7 days</h2>'
              f'<div class="figure">{dur_min(week["duration_min"].sum()) if len(week) else "0 min"}<small>training</small></div>'
              f'<div class="hero-meta">{len(week)} workout{"s" if len(week) != 1 else ""}</div>'
              f'<div>{sports}</div></div><div class="rows" style="margin-top:14px">{load_rows}</div>'))

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
            html('<div class="inset">' + card_head("Weekly training", f"avg {dur(avg_h)} a week", level=3)
                 + '<div class="r-sub">Hours per week. This week is faded until it\'s done.</div></div>')
            chart("weekly", charts.weekly_hours(weekly, I.week_start(END)), width="stretch")
        movement_card(days)
        fitness_card(days)
    with right:
        sport_card(cur, prev, label)
        intensity_card(cur, label)
        workouts_card(cur, label)


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
    stats.append((f'{num(a["avg_hr"])}<small>bpm</small>' if not pd.isna(a["avg_hr"]) else "–", "Avg heart rate"))
    cells = "".join(f'<div><div class="strip-v">{v}</div><div class="strip-k">{k}</div></div>' for v, k in stats)
    effect = a.get("effect_label")
    effect_html = ""
    if effect in ui.EFFECT_NAME:
        effect_html = (f'<div class="r" style="margin-top:14px; border-top:1px solid var(--line)">'
                       f'{icon("bolt", "r-ic accent")}<div class="r-main"><div class="r-label">'
                       f'{ui.EFFECT_NAME[effect]} workout</div><div class="r-sub">{EFFECT_MEANING.get(effect, "")}'
                       f' · training load {num(a["training_load"])}</div></div></div>')
    url = f"https://connect.garmin.com/modern/activity/{int(a['id'])}"
    html(card(card_head("Latest workout", f'<a class="accent" href="{url}" target="_blank" rel="noopener" '
                                          f'style="text-decoration:none">Open in Garmin Connect</a>')
              + f'<div class="r" style="padding-bottom:0"><div class="tile">{icon(ui.activity_icon(a["type"], sport))}</div>'
              + f'<div class="r-main"><div class="act-name">{ui.escape(str(a["name"]))}</div>'
              + f'<div class="r-sub">{ui.SPORT_NAME[sport]} · {day(a["date"], True)} · {hhmm(a["start_time"])}</div></div></div>'
              + f'<div class="stats4">{cells}</div>{effect_html}'))


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
                    change = f", {abs(diff):.1f} km/h {'faster' if diff > 0 else 'slower'} than the previous {label}"
            elif abs(diff) >= 3:
                change = f", {abs(diff):.0f} s {'slower' if diff > 0 else 'faster'} than the previous {label}"
        what = "pace" if sport in ("run", "swim") else "speed"
        sub = f'{r["sessions"]} session{"s" if r["sessions"] != 1 else ""}'
        if r["km"]:
            sub += f" · {ui.distance_text(r['km'], sport)}"
        if speed:
            sub += f" · avg {what} {speed}{change}"
        rows += row(ui.SPORT_NAME[sport], dur_min(r["minutes"]), sub=sub,
                    lead=f'<div class="tile">{icon(ui.SPORT_ICON[sport])}</div>')
    html(card(card_head("By sport", f"last {label}", level=3) + f'<div class="rows">{rows}</div>'))


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
    legend = "".join(f'<span><i class="key" style="background:{ui.INTENSITY[n]}"></i><b>{n}</b> {zones[n]} · '
                     f'{dur_min(m["minutes"])}</span>' for n, m in mix.items())
    easy, hard = mix["Easy"]["share"], mix["Hard"]["share"]
    if easy >= 0.7:
        take = "Mostly easy: a strong base. Add a few hard sessions to get faster."
    elif hard >= 0.5:
        take = ("<b>Most of your training time is hard.</b> Endurance coaches often aim for about 80% easy. "
                "Slowing some sessions down helps you recover and build endurance.")
    else:
        take = "A mix of easy and hard. Endurance coaches often aim for about 80% easy."
    html(card(card_head("Easy vs hard", f"last {label}", level=3)
              + f'<div class="seg" role="img" aria-label="Easy {easy:.0%}, hard {hard:.0%}">{blocks}</div>'
              + f'<div class="legend">{legend}</div><div class="body small" style="margin-top:14px">{take}</div>'
              + '<div class="card-foot">Time in each heart-rate zone during workouts.</div>'))


def fitness_card(days):
    if vo2.empty:
        return
    latest = vo2.iloc[-1]
    span = max(days, 120)
    recent = I.in_window(vo2, END, span)
    change = latest["vo2max"] - recent.iloc[0]["vo2max"] if len(recent) >= 2 else 0
    trend = ("Holding steady" if abs(change) < 0.3 else
             f"Up {change:.1f} since {day(recent.iloc[0]['date'])}" if change > 0 else
             f"Down {abs(change):.1f} since {day(recent.iloc[0]['date'])}")
    with st.container(key="card_fitness"):
        html('<div class="inset">' + card_head("Fitness", f"VO₂ max · {day(latest['date'])}", level=3)
             + f'<div class="plan" style="margin-top:8px">{latest["vo2max"]:.1f}</div>'
             + f'<div class="r-sub">{trend}. VO₂ max estimates your aerobic fitness; '
             + 'Garmin updates it after outdoor runs.</div></div>')
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
        html('<div class="inset">' + card_head("Daily movement", "average per day", level=3)
             + strip([(num(cur["steps"].mean()), f"Steps<br>(goal hit {hit:.0%} of days)"),
                      (f'{num(cur["cal_active"].mean())}<small>cal</small>', "Active<br>calories"),
                      (f'{num(cur["cal_total"].mean())}<small>cal</small>', "Total<br>burned")]) + '</div>')
        weekly = days > 90  # a year of daily bars is too thin to read, so show weekly averages
        chart("steps", charts.daily_steps(cur, goal, END - pd.Timedelta(days=days), END - pd.Timedelta(days=1),
                                           weekly), width="stretch")
        per = "Average steps a day, week by week" if weekly else "Steps each day"
        legend = ("" if weekly else
                  f'<span><i class="key" style="background:{ui.ACCENT}"></i>Goal hit</span>'
                  f'<span><i class="key" style="background:{charts.REST_GREY}"></i>Under goal</span>')
        if goal:
            legend += f'<span><i class="key dash"></i>Goal <b>{num(goal)}</b></span>'
        html(f'<div class="inset legend">{legend}</div>'
             f'<div class="inset card-foot" style="margin-top:6px">{per}. Hover a bar for details.</div>')


def workouts_card(cur, label):
    items = cur.iloc[::-1]
    shown = items.head(12)
    links = "".join(ui.activity_link(a, a["sport"]) for _, a in shown.iterrows())
    more = (f'<div class="card-foot">{len(items) - len(shown)} more in this period. See them all in Garmin Connect.</div>'
            if len(items) > len(shown) else "")
    body = links or '<div class="r-sub" style="margin-top:8px">No workouts in this period.</div>'
    html(card(card_head("Workouts", f"{len(items)} in the last {label}", level=3) + f'<div class="rows">{body}</div>{more}'))


# ================= WEIGHT =================
UNITS = {"lb": 2.20462, "kg": 1.0}  # weights are saved in kg; this converts for display


def weight_unit():
    unit = get_meta("weight_unit", "lb")
    return unit if unit in UNITS else "lb"


def weight_tab():
    w = I.weight_series(weights) if not weights.empty else weights
    unit = weight_unit()
    left, right = st.columns(2)  # fixed columns: cards never jump between them while loading
    with left:
        weight_card(w, unit)
        weight_trend_card(w, unit)
    with right:
        calories_card(unit)
        burn_card()


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
            trend = ""
            if rate is not None:
                trend = (ui.trend_chip(0, "Steady") if abs(rate) < 0.1 else
                         ui.trend_chip(rate, f"{'Losing' if rate < 0 else 'Gaining'} about {abs(rate) * f:.1f} {unit} a week"))
            elif len(w) >= 2:
                diff, before = (latest["kg"] - w.iloc[-2]["kg"]) * f, day(w.iloc[-2]["date"])
                trend = (ui.trend_chip(0, f"Same as {before}") if abs(diff) < 0.05
                         else ui.trend_chip(diff, f"{diff:+.1f} {unit} since {before}"))
            days_ago = (END - latest["date"]).days
            logged = ("Logged today" if days_ago == 0 else "Logged yesterday" if days_ago == 1
                      else f"Logged {day(latest['date'])}" + (f", {days_ago} days ago" if days_ago > 7 else ""))
            html(f'<div class="hero"><h2 class="h3">Weight</h2>'
                 f'<div class="figure">{latest["kg"] * f:.1f}<small>{unit}</small></div>'
                 f'{trend}<div class="hero-meta">{logged}</div></div>')
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
                c3.form_submit_button("Save", type="primary", width="stretch", on_click=save_weight_entry)
        html('<div class="inset card-foot" style="margin-top:4px">Weigh in first thing in the morning for the '
             'steadiest numbers. Saving a day again replaces it.</div>')


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
            last = w.iloc[-1]
            html(f'<div class="inset"><div class="empty">No weigh-ins in the last {choice}. Your last one was '
                 f'{last["kg"] * f:.1f} {unit} on {day(last["date"])}. Log today\'s above, or pick a longer range.</div></div>')
        else:
            # A 7-day average only makes sense with regular weigh-ins
            smooth = len(cur) >= 7 and cur["date"].diff().dt.days.median() <= 3
            chart("weight", charts.weight_trend(cur, start, END, unit, f, smooth), width="stretch")
            explain = ("Dots are weigh-ins. The line is your 7-day average, which evens out day-to-day water changes."
                       if smooth else "Your weigh-ins. Log a few times a week and a smoothed 7-day average appears.")
            html(f'<div class="inset card-foot" style="margin-top:0">{explain}</div>')

        with st.container(key="wrecent"):
            html('<div class="inset" style="margin-top:10px"><h3 class="h3">Recent weigh-ins</h3></div>')
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


def calories_card(unit):
    c = I.calorie_needs(daily, acts, today)
    if not c:
        html(card(card_head("Calories") + '<div class="r-sub" style="margin-top:8px">'
                  'Not enough days from your watch yet. Check back after a week of wearing it.</div>'))
        return
    saved = get_meta("weight_goal", "Maintain")
    saved = saved if saved in I.GOALS else "Maintain"
    bars = [(label, c["resting"], total) for label, total in (("Workout days", c["train"]), ("Rest days", c["rest"]))
            if total is not None]

    with st.container(key="card_cal"):
        html('<div class="inset"><div class="hero"><h2 class="h3">Calories you burn</h2>'
             f'<div class="figure">{num(c["avg"])}<small>a day</small></div>'
             f'<div class="hero-meta">Average of your last {c["days"]} full days, from your watch</div></div>'
             + (ui.burn_bars(bars) if bars else "")
             + '<div class="legend" style="margin-top:10px"><span><i class="key" style="background:#4a525e"></i>'
               f'At rest <b>{num(c["resting"])}</b></span><span><i class="key" style="background:{ui.ACCENT}"></i>'
               'From moving and workouts</span></div>'
             + '<h3 class="h3" style="margin-top:24px">How much to eat</h3></div>')
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
        cells = ([(f'{target(c["train"])}<small>cal</small>', "on workout days"),
                  (f'{target(c["rest"])}<small>cal</small>', "on rest days")] if c["train"] and c["rest"]
                 else [(f'{target(c["avg"])}<small>cal</small>', "a day")])
        text = f"{aim}: about {target(c['avg'])} a day on average."
        if goal == "Lose":
            text += " Keep the cut this small so training and recovery don't suffer."
        html('<div class="inset">' + strip(cells)
             + f'<div class="body" style="margin-top:14px">{text}</div>'
             '<div class="card-foot">Your watch estimates calories from heart rate and movement, so treat these as a '
             "starting point. If your weight trend doesn't match your goal after 2–3 weeks, adjust by 100–200 cal "
             'a day.</div></div>')


def burn_card():
    d = I.burn_by_day(daily, acts, today, 30)
    if len(d) < 3:
        return
    avg = d["cal_total"].mean()
    with st.container(key="card_burn"):
        html('<div class="inset">' + card_head("Calories burned", "past 30 days")
             + '<div class="r-sub">Workout days burn more, so they need more food. Hover a day for details.</div></div>')
        chart("burn", charts.daily_burn(d, avg, END - pd.Timedelta(days=30), END - pd.Timedelta(days=1)),
                        width="stretch")
        html(f'<div class="inset legend"><span><i class="key" style="background:{ui.ACCENT}"></i>Workout day</span>'
             f'<span><i class="key" style="background:{charts.REST_GREY}"></i>Rest day</span>'
             f'<span><i class="key dash"></i>Average <b>{num(avg)}</b> a day</span></div>')


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
        html(card(card_head("Today") + '<div class="r-sub" style="margin-top:8px">Your targets appear after a week '
                  'of wearing your watch.</div>'))
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
    html(card(f'<div class="hero"><h2 class="h3">Today</h2><div class="figure">{big}</div>'
              f'<div class="hero-meta">{kind} target {num(targets["calories"])} cal · goal: {goal.lower()}</div></div>'
              f'<div class="rows" style="margin-top:14px">{rows}</div>'
              + (f'<div class="r-sub" style="margin-top:2px">{extra}</div>' if extra else "")
              + '<div class="card-foot">Targets come from what your watch says you burn (change the goal on the '
                'Weight tab). Workout days switch on once your workout syncs. Protein 1.6 g and carbs 5–6 g per kg '
                'of body weight suit endurance training.</div>'))


def meals_card(eaten):
    m = eaten["meals"]
    with st.container(key="card_meals"):
        html('<div class="inset">' + card_head("Meals today", f"{len(m)} logged" if len(m) else "") + '</div>')
        if m.empty:
            html('<div class="inset"><div class="empty">Nothing logged yet today. Add a meal with a photo or a '
                 'quick description.</div></div>')
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
        html('<div class="inset">' + card_head("Add a meal") + '<div class="r-sub" style="margin-top:6px">'
             'Snap or upload photos, describe it, or both. You can check the numbers before saving.</div></div>')
        if not food.has_key():
            html('<div class="inset"><div class="notice" style="background:var(--card-2); margin-top:10px">'
                 f'{icon("key")}<div><b>Add a Gemini key to estimate from photos.</b> Get a free key at '
                 '<a class="accent" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">'
                 'aistudio.google.com/apikey</a>, run <code>setx GEMINI_API_KEY "your-key"</code> in a terminal, '
                 'then close and reopen the dashboard. Until then you can enter meals by hand.</div></div></div>')
        with st.container(key="mealform"):
            photos = st.file_uploader("Photos of your meal", type=["jpg", "jpeg", "png", "webp", "heic"],
                                      accept_multiple_files=True, disabled=not food.has_key(),
                                      help="Add as many as you like: each dish, or one plate from a few angles")
            note = st.text_input("Describe it, or add a note", placeholder="e.g. chicken burrito, large, and a coke",
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
        html('<div class="inset card-foot">Photos go to Google\'s Gemini to be estimated and aren\'t saved here. '
             'On the free tier, Google may use them to improve its products. Estimates can be off by 20% or more, '
             'so fix anything that looks wrong.</div>')


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
    html('<div class="inset">' + card_head("Check and save", "edit anything that's off")
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

"""Plain-language findings computed from the stored Garmin data.

Every function takes pandas DataFrames from db.py and returns plain numbers or dicts,
so the logic can be tried out in a Python shell without running the app:

    >>> from db import load_sleep
    >>> from insights import tonight
    >>> tonight(load_sleep(), date.today())
"""
from datetime import timedelta

import numpy as np
import pandas as pd

import schedule

DEFAULT_NEED_MIN = 540  # 9 h - only used if Garmin hasn't reported a sleep need

SPORT_OF = {
    "lap_swimming": "swim", "open_water_swimming": "swim",
    "road_biking": "bike", "cycling": "bike", "indoor_cycling": "bike",
    "mountain_biking": "bike", "gravel_cycling": "bike", "virtual_ride": "bike",
    "running": "run", "treadmill_running": "run", "trail_running": "run",
    "track_running": "run", "indoor_running": "run",
}

# Parts of Garmin's sleep score, and how to say "this part was weak" in plain words
SCORE_PARTS = [
    ("q_duration", "not enough sleep"),
    ("q_stress", "stress while asleep"),
    ("q_awake", "waking up during the night"),
    ("q_restless", "restless sleep"),
    ("q_deep", "little deep sleep"),
    ("q_rem", "little REM sleep"),
    ("q_light", "a lot of light sleep"),
]


# ---------- small helpers ----------
def sport_of(activity_type):
    return SPORT_OF.get(activity_type, "other")


def clock_hours(hhmm):
    """'07:40' -> 7.67"""
    h, m = map(int, hhmm.split(":"))
    return h + m / 60


def first_valid(*values):
    for v in values:
        if v is not None and not pd.isna(v):
            return v
    return None


def in_window(df, end, days):
    """Rows dated within the `days` days ending at `end` (inclusive)."""
    if df.empty:
        return df
    end = pd.Timestamp(end)
    return df[(df["date"] > end - pd.Timedelta(days=days)) & (df["date"] <= end)]


# ---------- sleep ----------
def night_name(calendar_day, today):
    """Garmin dates a night by the morning you woke up. Name it the way people talk."""
    calendar_day = pd.Timestamp(calendar_day).date()
    if calendar_day == today:
        return "Last night"
    evening = calendar_day - timedelta(days=1)
    if (today - calendar_day).days < 7:
        return f"{evening:%A} night"
    return f"Night of {evening:%b} {evening.day}"


def need_hours(night):
    return first_valid(night.get("need_min"), DEFAULT_NEED_MIN) / 60


def held_back_by(night):
    """Parts of the score Garmin rated only Fair or Poor, in plain words."""
    return [label for col, label in SCORE_PARTS if night.get(col) in ("FAIR", "POOR")]


def evening(hours):
    """Put a clock time on a night-time scale where 1 am is 25, so 'later' always sorts later."""
    return hours + 24 if hours < 12 else hours


def usual_wake(sleep, weekday):
    """Typical wake-up time (in hours) on a given weekday (Mon=0), from recent weeks."""
    wake = sleep["wake_time"].map(clock_hours)
    same_day = wake[sleep["date"].dt.day_of_week == weekday].tail(6)
    return float(same_day.median() if len(same_day) >= 3 else wake.tail(14).median())


def usual_bedtime(sleep, weekday):
    """Typical time you fall asleep (night-time scale) before a given weekday's morning."""
    bed = sleep["bedtime_hours"]
    same_day = bed[sleep["date"].dt.day_of_week == weekday].tail(6)
    return float(same_day.median() if len(same_day) >= 3 else bed.tail(14).median())


def awake_hours(sleep):
    """Typical time spent awake during the night (Garmin leaves it out of 'asleep')."""
    return float(sleep["awake_min"].tail(30).median() or 0) / 60


NEED_REASONS = [  # column, plain words
    ("next_need_history", "recent short nights"),
    ("next_need_training", "recent training"),
    ("next_need_hrv", "your HRV"),
    ("next_need_nap", "naps"),
]


def tonight(sleep, wake_day, classes=(), buffer_min=schedule.WAKE_BEFORE_MIN):
    """The best time to fall asleep tonight (the night before `wake_day`), from Garmin's
    sleep need and recommended bedtime window plus your usual wake-up time.

    Times are on the night-time scale (see `evening`): 22.5 = 10:30 pm, 31.7 = 7:42 am.
    """
    last = sleep.iloc[-1]
    # Garmin reports the need for the *next* night with each night's data. It's exactly
    # tonight's need only if the latest night synced is last night; otherwise it's
    # Garmin's most recent estimate.
    fresh = last.get("next_need_date") == wake_day.isoformat()
    base_min = first_valid(last.get("next_need_base_min"), last.get("need_base_min"), DEFAULT_NEED_MIN)
    need_min = first_valid(last.get("next_need_min"), base_min)
    reasons = [words for col, words in NEED_REASONS
               if last.get(col) not in (None, "NO_CHANGE") and not pd.isna(last.get(col))]
    window = None
    if not pd.isna(last.get("next_bed_start_min")) and not pd.isna(last.get("next_bed_end_min")):
        window = (evening(last["next_bed_start_min"] / 60), evening(last["next_bed_end_min"] / 60))
    # Wake-up: `buffer_min` before your first class if you have one, otherwise your usual for that weekday
    first = schedule.first_class(classes, wake_day) if classes else None
    wake = (schedule.class_wake(classes, wake_day, buffer_min) if first else usual_wake(sleep, wake_day.weekday())) + 24
    awake = awake_hours(sleep)
    ideal = wake - need_min / 60 - awake  # asleep then covers your whole need
    # Garmin's window is the earliest it thinks you'll actually fall asleep, so stay inside it
    best = min(max(ideal, window[0]), window[1]) if window else ideal
    usual_bed = usual_bedtime(sleep, wake_day.weekday())
    return {
        "fresh": fresh, "need_min": need_min, "base_min": base_min, "extra_min": need_min - base_min,
        "reasons": reasons, "estimate_from": last["date"],
        "window": window, "best": best, "latest": window[1] if window else None,
        "wake": wake, "wake_day": wake_day, "awake_h": awake, "usual_bed": usual_bed, "first_class": first,
    }


def week_plan(sleep, classes, start, days=7, buffer_min=schedule.WAKE_BEFORE_MIN):
    """For each of the next `days` nights: first class next morning, wake-up and asleep-by time
    for your usual sleep need. Nights before a day off use your usual wake-up for that weekday."""
    base_need = first_valid(sleep.iloc[-1].get("next_need_base_min"), sleep.iloc[-1].get("need_base_min"),
                            DEFAULT_NEED_MIN) / 60
    awake = awake_hours(sleep)
    plan = []
    for i in range(days):
        night = start + timedelta(days=i)
        morning = night + timedelta(days=1)
        first = schedule.first_class(classes, morning)
        wake = (schedule.class_wake(classes, morning, buffer_min) if first else usual_wake(sleep, morning.weekday())) + 24
        plan.append({"night": night, "morning": morning, "first_class": first, "wake": wake,
                     "asleep_by": round((wake - base_need - awake) * 12) / 12, "need": base_need})
    return plan


def sleep_between(t, asleep_at):
    """Hours of sleep from falling asleep at `asleep_at` until your usual wake-up (a tonight() result)."""
    return max(0.0, t["wake"] - asleep_at - t["awake_h"])


def bedtime_guide(sleep, classes=(), today=None, buffer_min=schedule.WAKE_BEFORE_MIN):
    """When to fall asleep on weeknights for each amount of sleep, with the score you
    usually get from that much sleep. Weeknights = nights before a Monday-Friday morning.
    With a class schedule, the wake-up is the usual one for your class days (`buffer_min` before class)."""
    df = sleep.dropna(subset=["sleep_score", "total_sleep_hours"])
    weeknights = df[df["date"].dt.day_of_week < 5].tail(40)
    if len(df) < 20 or len(weeknights) < 8:
        return None
    wake = weeknights["wake_time"].map(clock_hours).median() + 24
    from_classes = False
    if classes and today:
        wakes = [schedule.class_wake(classes, today + timedelta(days=i), buffer_min) for i in range(1, 8)]
        wakes = [w for w in wakes if w is not None]
        if wakes:
            wake, from_classes = float(np.median(wakes)) + 24, True
    awake = awake_hours(df)
    rows = []
    for hours, low, high in ((9, 9, 24), (8, 8, 9), (7, 7, 8), (6, 6, 7)):
        band = df[(df["total_sleep_hours"] >= low) & (df["total_sleep_hours"] < high)]
        asleep_by = round((wake - hours - awake) * 12) / 12  # to the nearest 5 minutes
        rows.append({"hours": hours, "asleep_by": asleep_by, "nights": len(band),
                     "score": band["sleep_score"].mean() if len(band) >= 3 else None})
    return {"wake": wake, "rows": rows, "nights": len(df), "from_classes": from_classes,
            "usual_bed": weeknights["bedtime_hours"].median(),
            "usual_hours": weeknights["total_sleep_hours"].median()}


def recent_sleep(sleep, end, days=7):
    """Average sleep vs need over the last `days` days of data."""
    recent = in_window(sleep, end, days)
    if recent.empty:
        return None
    need = recent.apply(need_hours, axis=1)
    return {
        "nights": len(recent),
        "avg_hours": recent["total_sleep_hours"].mean(),
        "avg_need": need.mean(),
        "nights_met": int((recent["total_sleep_hours"] >= need - 0.25).sum()),
    }


def sleep_drivers(sleep):
    """Separate the effect of sleep length from the effect of bedtime on the score."""
    df = sleep.dropna(subset=["sleep_score", "total_sleep_hours", "bedtime_hours"])
    if len(df) < 12:
        return None
    X = np.column_stack([np.ones(len(df)), df["total_sleep_hours"], df["bedtime_hours"]])
    coef, *_ = np.linalg.lstsq(X, df["sleep_score"].to_numpy(dtype=float), rcond=None)
    bands = pd.cut(df["total_sleep_hours"], [0, 6, 7, 8, 9, 24],
                   labels=["Under 6h", "6–7h", "7–8h", "8–9h", "9h+"], right=False)
    by_length = (df.assign(band=bands).groupby("band", observed=False)["sleep_score"]
                 .agg(score="mean", nights="size").reset_index())
    by_length["band"] = by_length["band"].astype(str)
    return {"per_hour_slept": coef[1], "per_hour_later": coef[2], "nights": len(df),
            "by_length": by_length}


STAGES = [("Deep", "deep_hours", "q_deep"), ("Light", "light_hours", "q_light"), ("REM", "rem_hours", "q_rem")]


def stage_summary(sleep):
    """Average hours and share of each sleep stage, and how often Garmin rated it Good or better."""
    df = sleep.dropna(subset=["deep_hours", "light_hours", "rem_hours"])
    if df.empty:
        return None
    total = sum(df[col].mean() for _, col, _ in STAGES)
    out = {}
    for name, col, rating in STAGES:
        rated = df[rating].dropna()
        out[name] = {"hours": df[col].mean(), "share": df[col].mean() / total,
                     "good": rated.isin(["GOOD", "EXCELLENT"]).mean() if len(rated) else None}
    return out


# ---------- recovery ----------
def recovery(sleep, hrv, daily, acts=None, end=None):
    """A few simple signals and a suggestion. This is the app's own check,
    not Garmin's Training Readiness (which the API doesn't provide)."""
    signals = []
    if not sleep.empty:
        night = sleep.iloc[-1]
        score = night["sleep_score"]
        status = "good" if score >= 80 else "ok" if score >= 60 else "low"
        word = "Excellent" if score >= 90 else "Good" if score >= 80 else "Fair" if score >= 60 else "Poor"
        signals.append({"key": "sleep", "label": "Sleep score", "value": f"{score:.0f}", "unit": "",
                        "status": status, "note": f"{word} · good is 80 or more", "date": night["date"],
                        # for the bar: today's value, the good range, and the scale
                        "x": score, "band": (80, 100), "domain": (min(40, score - 5), 100)})

    h = hrv.dropna(subset=["hrv_last_night", "hrv_balanced_low", "hrv_balanced_high"]) if not hrv.empty else hrv
    if not h.empty:
        last = h.iloc[-1]
        v, low, high = last["hrv_last_night"], last["hrv_balanced_low"], last["hrv_balanced_high"]
        if last.get("hrv_status") in ("LOW", "POOR"):
            status, note = "low", "Low for a week or more"
        elif v < low:
            status, note = "ok", f"Below your normal {low:.0f}–{high:.0f}"
        else:
            status, note = "good", f"Within your normal {low:.0f}–{high:.0f}" if v <= high else "Above your normal"
        pad = max(4, (high - low) * 0.6)
        signals.append({"key": "hrv", "label": "Heart rate variability", "value": f"{v:.0f}", "unit": "ms",
                        "status": status, "note": note, "date": last["date"],
                        "x": v, "band": (low, high), "domain": (min(low, v) - pad, max(high, v) + pad)})

    rhr = daily.dropna(subset=["resting_hr"]) if not daily.empty else daily
    if len(rhr) >= 8:
        today_rhr = rhr["resting_hr"].iloc[-1]
        usual = rhr["resting_hr"].iloc[-31:-1].mean()
        diff = today_rhr - usual
        status = "good" if diff <= 2 else "ok" if diff <= 5 else "low"
        note = (f"Normal · usually {usual:.0f}" if status == "good"
                else f"{diff:.0f} above your usual {usual:.0f}")
        lo, hi = min(usual - 8, today_rhr - 3), max(usual + 8, today_rhr + 3)
        signals.append({"key": "rhr", "label": "Resting heart rate", "value": f"{today_rhr:.0f}", "unit": "bpm",
                        "status": status, "note": note, "date": rhr["date"].iloc[-1],
                        "x": today_rhr, "band": (lo, usual + 2), "domain": (lo, hi)})  # lower is fine

    load = load_check(acts, end) if acts is not None and end is not None else None
    if load:
        signals.append({"key": "load", "label": "Training load, past 7 days", "value": f"{load['week']:.0f}",
                        "unit": "", "status": load["status"],
                        "note": f"{load['text']} {load['usual']:.0f} a week", "date": None,
                        "x": load["week"], "band": load["band"], "domain": load["domain"]})

    lows = sum(s["status"] == "low" for s in signals)
    oks = sum(s["status"] == "ok" for s in signals)
    # level: 0 = rest, 1 = easy to moderate, 2 = normal training, 3 = ready for a hard session
    if not signals:
        verdict, level = None, None
    elif lows >= 2:
        verdict, level = ("low", "Take it easy today", "Two signals say you haven't recovered. Rest or keep it very light."), 0
    elif lows == 1 or oks >= 2:
        verdict, level = ("ok", "Keep it easy to moderate", "Some signals are below your normal. Save the hard session for another day."), 1
    elif oks == 1:
        verdict, level = ("good", "Fine for normal training", "Mostly recovered. A regular session is fine."), 2
    else:
        verdict, level = ("good", "Good day for a hard session", "Sleep, HRV and resting heart rate all look normal."), 3
    return {"signals": signals, "verdict": verdict, "level": level}


# ---------- training ----------
def with_sport(acts):
    return acts.assign(sport=acts["type"].map(sport_of)) if not acts.empty else acts


def load_check(acts, end):
    """Training load in the last 7 days compared with your recent average week."""
    if acts.empty:
        return None
    week = in_window(acts, end, 7)["training_load"].sum()
    usual = in_window(acts, end, 28)["training_load"].sum() / 4
    if usual <= 0:
        return None
    ratio = week / usual
    if ratio < 0.8:
        status, text = "neutral", "Lighter than your usual"
    elif ratio <= 1.3:
        status, text = "good", "About your usual"
    elif ratio <= 1.5:
        status, text = "ok", "A bit above your usual"
    else:
        status, text = "ok", "Well above your usual"
    return {"week": week, "usual": usual, "ratio": ratio, "status": status, "text": text,
            # for the bar: 0.8-1.3x your usual week is the steady-build range
            "band": (0.8 * usual, 1.3 * usual), "domain": (0, max(1.8 * usual, 1.1 * week))}


def sport_totals(acts):
    """Sessions, time and distance per sport, plus a speed measure people actually use."""
    rows = []
    acts = with_sport(acts)
    for sport in ("swim", "bike", "run", "other"):
        a = acts[acts["sport"] == sport] if not acts.empty else acts
        if a.empty:
            continue
        km = a["distance_km"].sum()
        moving_h = a["moving_min"].fillna(a["duration_min"]).sum() / 60
        measured = a[a["distance_km"] > 0]
        m_km = measured["distance_km"].sum()
        m_h = measured["moving_min"].fillna(measured["duration_min"]).sum() / 60
        speed = None
        if m_km > 0 and m_h > 0:
            if sport == "run":
                speed = m_h * 3600 / m_km            # seconds per km
            elif sport == "swim":
                speed = m_h * 3600 / (m_km * 10)     # seconds per 100 m
            elif sport == "bike":
                speed = m_km / m_h                   # km/h
        rows.append({"sport": sport, "sessions": len(a), "minutes": a["duration_min"].sum(),
                     "km": km, "moving_h": moving_h, "speed": speed})
    return rows


def intensity_mix(acts):
    """Share of workout time spent easy (zones 1–2), moderate (3) and hard (4–5)."""
    if acts.empty:
        return None
    z = acts[[f"zone{i}_s" for i in range(1, 6)]].fillna(0).sum()
    total = z.sum()
    if total <= 0:
        return None
    parts = {"Easy": z["zone1_s"] + z["zone2_s"], "Moderate": z["zone3_s"], "Hard": z["zone4_s"] + z["zone5_s"]}
    return {name: {"minutes": s / 60, "share": s / total} for name, s in parts.items()}


def week_start(day):
    """Weeks start on Sunday (the Windows setting on this PC)."""
    day = pd.Timestamp(day).normalize()
    return day - pd.Timedelta(days=(day.weekday() + 1) % 7)


def weekly_training(acts, start, end):
    """Training hours, load and sessions per week (Sunday to Saturday), zero weeks included."""
    weeks = pd.date_range(week_start(start), week_start(end), freq="7D")
    out = pd.DataFrame({"week": weeks})
    if not acts.empty:
        a = acts.assign(week=acts["date"].map(week_start))
        g = a.groupby("week").agg(minutes=("duration_min", "sum"), load=("training_load", "sum"),
                                  sessions=("id", "count")).reset_index()
        out = out.merge(g, on="week", how="left")
    for col in ("minutes", "load", "sessions"):
        out[col] = out.get(col, 0)
        out[col] = out[col].fillna(0)
    out["hours"] = out["minutes"] / 60
    return out


# ---------- today's workout ----------
TRI = ("swim", "bike", "run")
HARD_EFFECTS = {"TEMPO", "LACTATE_THRESHOLD", "VO2MAX", "ANAEROBIC_CAPACITY", "SPEED", "SPRINT"}
LAST_ONE = {"swim": "swim", "bike": "ride", "run": "run"}

# (sport, kind) -> name, how to do it, minutes (None = your usual length for that sport)
WORKOUTS = {
    ("run", "easy"): ("Easy run", "Conversational pace: you could talk in full sentences.", None),
    ("bike", "easy"): ("Easy ride", "Light gears and a steady, relaxed effort.", None),
    ("swim", "easy"): ("Easy swim", "Relaxed laps with smooth technique. Rest at the wall whenever you like.", None),
    ("run", "hard"): ("Run intervals", "10 min easy, then 5 × 3 min hard with 2 min of easy jogging between, "
                                       "then 5 min easy.", 40),
    ("bike", "hard"): ("Bike intervals", "15 min easy, then 4 × 4 min hard with 3 min easy between, "
                                         "then 5 min easy.", 50),
    ("swim", "hard"): ("Swim intervals", "200 m easy, then 8 × 50 m fast with 30 s rest between, "
                                         "then 200 m easy.", 30),
}


def hard_sessions(acts):
    """Workouts that were hard: a tempo, threshold, VO2 max... training effect, or aerobic effect 3.5+."""
    return acts[acts["effect_label"].isin(HARD_EFFECTS) | (acts["training_effect"].fillna(0) >= 3.5)]


def easy_hr_limit(acts):
    """The top of heart-rate zone 2, estimated from your runs and rides: the lowest max
    heart rate of any workout that reached zone 3. None without enough data."""
    a = acts[acts["sport"].isin(["run", "bike"])].dropna(subset=["max_hr"])
    reached = a[a["zone3_s"].fillna(0) > 5]
    if len(reached) < 3:
        return None
    return int(reached["max_hr"].min() // 5 * 5)


def workout_plan(acts, level, day, bedtime):
    """Suggest one workout for `day`.

    How hard: from the recovery level (see `recovery`), recent hard workouts, training load
    and your easy/hard balance. Which sport: the one you've done least in the last two weeks.
    When: finished early enough not to cost you sleep (`bedtime` is tonight's best bedtime).
    """
    day = pd.Timestamp(day).normalize()
    tri = acts[acts["sport"].isin(TRI)] if not acts.empty else acts
    if tri.empty:
        return None
    done = tri[tri["date"] == day]
    if not done.empty:
        return {"kind": "done", "done": done}
    past = tri[tri["date"] < day]
    level = 2 if level is None else level

    hard = hard_sessions(past)
    days_since_hard = (day - hard["date"].max()).days if not hard.empty else None
    hard_week = len(hard[hard["date"] >= day - pd.Timedelta(days=7)])
    load = load_check(acts, day - pd.Timedelta(days=1))
    mix = intensity_mix(in_window(past, day - pd.Timedelta(days=1), 30))
    hard_share = mix["Hard"]["share"] if mix else 0

    why = []  # (icon, reason), most important first; the app shows the top few
    if level == 0:
        kind = "rest"
        why.append(("monitor_heart", "Your recovery check says you haven't recovered"))
    else:
        if days_since_hard == 1:
            why.append(("bolt", "Hard workout yesterday"))
        if hard_week >= 2:
            why.append(("bolt", f"{hard_week} hard workouts in the past week"))
        if load and load["ratio"] > 1.5:
            why.append(("trending_up", f"Training load is {load['ratio']:.1f}× your usual week"))
        if level == 1:
            why.append(("monitor_heart", "Some recovery signals are below your normal"))
        if hard_share >= 0.5:
            why.append(("donut_large", f"{hard_share:.0%} of this month's training was hard"))
        kind = "easy" if why else "hard"
        if kind == "hard":
            why.append(("check_circle", "Recovered" + (f", and {days_since_hard} days since your last hard workout"
                                                        if days_since_hard else "")))

    # Which sport: balance the three, using the ones you've actually done in the last 2 months
    recent = past[past["date"] >= day - pd.Timedelta(days=60)]
    pool = recent if not recent.empty else past
    sports = [s for s in TRI if (pool["sport"] == s).any()]
    last14 = past[past["date"] >= day - pd.Timedelta(days=14)]
    minutes = {s: last14.loc[last14["sport"] == s, "duration_min"].sum() for s in sports}
    last_date = {s: pool.loc[pool["sport"] == s, "date"].max() for s in sports}
    order = sorted(sports, key=lambda s: (minutes[s], last_date[s]))

    def describe(sport):
        name, how, length = WORKOUTS[(sport, "hard" if kind == "hard" else "easy")]
        if length is None:  # your usual length for this sport, 20-60 min
            usual = pool.loc[pool["sport"] == sport, "duration_min"].tail(6).median()
            length = int(min(60, max(20, round(usual / 5) * 5)))
        return {"sport": sport, "name": name, "how": how, "minutes": length}

    pick = order[0]
    gap = (day - last_date[pick]).days
    starts = past["start_time"].tail(8).map(clock_hours)
    return {
        "kind": kind, "why": why,
        "main": describe(pick) if kind != "rest" else None,
        "alt": describe(order[1]) if kind != "rest" and len(order) > 1 else None,
        "sport_note": f"Last {LAST_ONE[pick]} was {gap} days ago" if gap >= 5 and len(sports) > 1 else "",
        "hr_limit": easy_hr_limit(acts),
        # Hard efforts close to bedtime can delay sleep, so finish those earlier
        "finish_by": bedtime - (2 if kind == "hard" else 1),
        "usual_start": float(starts.median()) if len(starts) >= 4 else None,
    }


# ---------- weight and calories ----------
KCAL_PER_KG = 7700  # about the energy in 1 kg of body weight
GOALS = {"Lose": -0.25, "Maintain": 0.0, "Gain": 0.25}  # kg per week: slow enough to keep training well


def weight_series(weight):
    """Weigh-ins oldest first, plus a 7-day average that evens out day-to-day water swings."""
    w = weight.sort_values("date").reset_index(drop=True)
    w["trend"] = w.set_index("date")["kg"].rolling("7D").mean().to_numpy()
    return w


def weight_rate(w, end, days=28):
    """kg per week over the last `days` days, from a straight-line fit (None if too few weigh-ins)."""
    r = w[w["date"] > pd.Timestamp(end) - pd.Timedelta(days=days)]
    if len(r) < 4 or (r["date"].max() - r["date"].min()).days < 14:
        return None
    x = (r["date"] - r["date"].min()).dt.days.to_numpy(dtype=float)
    return float(np.polyfit(x, r["kg"].to_numpy(dtype=float), 1)[0] * 7)


def workout_days(acts):
    """Dates with a real workout (swim, bike, run or strength), not just a walk."""
    if acts.empty:
        return set()
    real = acts["sport"].isin(TRI) | (acts["type"] == "strength_training")
    return set(acts.loc[real, "date"])


def burn_by_day(daily, acts, today, days=30):
    """Calories burned on each full day (today isn't over yet, so it's left out)."""
    if daily.empty:
        return daily
    end = pd.Timestamp(today) - pd.Timedelta(days=1)
    d = in_window(daily.dropna(subset=["cal_total"]), end, days).copy()
    d["trained"] = d["date"].isin(workout_days(acts))
    return d


def calorie_needs(daily, acts, today, days=30):
    """Average daily burn: Garmin's resting + active calories. Eating about this much keeps
    your weight steady. Training days burn more than rest days, so they need more."""
    d = burn_by_day(daily, acts, today, days)
    if len(d) < 7:
        return None
    train, rest = d[d["trained"]], d[~d["trained"]]
    return {"avg": d["cal_total"].mean(), "resting": d["cal_resting"].mean(), "days": len(d),
            "train": train["cal_total"].mean() if len(train) >= 2 else None,
            "rest": rest["cal_total"].mean() if len(rest) >= 2 else None}


MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]


def meal_slot(hour):
    """A sensible default label for a meal eaten at `hour`."""
    return "Breakfast" if 5 <= hour < 11 else "Lunch" if 11 <= hour < 15 else "Dinner" if 17 <= hour < 22 else "Snack"


def food_targets(daily, acts, today, goal_rate, weight_kg):
    """Today's calorie and nutrition targets. Workout days get the workout-day calories and
    more carbs; protein and fibre stay the same every day."""
    c = calorie_needs(daily, acts, today)
    if not c:
        return None
    trained = pd.Timestamp(today) in workout_days(acts)
    burn = (c["train"] if trained else c["rest"]) or c["avg"]
    calories = round(calorie_target(burn, goal_rate) / 10) * 10
    kg = weight_kg or 60
    protein = 1.6 * kg                    # endurance athletes: about 1.2-2.0 g per kg
    carbs = (6 if trained else 5) * kg    # fuel for training: about 5-7 g per kg
    fat = max(0.8 * kg, (calories - protein * 4 - carbs * 4) / 9)
    return {"calories": calories, "trained": trained, "protein": protein, "carbs": carbs, "fat": fat, "fibre": 30}


def food_day(meals, day):
    """Totals eaten on `day`, plus that day's meals."""
    if meals.empty:
        return {"meals": meals, "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fibre": 0, "sugar": 0}
    m = meals[meals["date"] == pd.Timestamp(day)]
    cols = {"calories": "calories", "protein": "protein_g", "carbs": "carbs_g", "fat": "fat_g",
            "fibre": "fibre_g", "sugar": "sugar_g"}
    return {"meals": m, **{k: float(m[c].fillna(0).sum()) for k, c in cols.items()}}


def calorie_target(burn, kg_per_week):
    """Calories a day to gain (+) or lose (-) `kg_per_week`; 0 keeps your weight steady."""
    return burn + kg_per_week * KCAL_PER_KG / 7

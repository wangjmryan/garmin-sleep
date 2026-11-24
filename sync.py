"""Download everything useful from Garmin into sleep.db.

Run:  python sync.py          (last 30 days)
      python sync.py 365      (last year - do this once to fill in history)
"""
import sys
from datetime import date, datetime, timedelta

import requests

from db import save_garmin_weights, set_meta, upsert
from get_sleep import chunks, fetch_nights, to_row
from get_token import get_token

BASE = "https://personal.connectapi.garmin.com"


def get(headers, path, params=None):
    response = requests.get(BASE + path, headers=headers, params=params, timeout=60)
    if response.status_code != 200:
        raise SystemExit(f"Garmin request failed ({response.status_code}) for {path}: {response.text[:200]}")
    return response.json()


def fetch_daily(headers, start, end):
    """Steps, calories, resting HR, stress, Body Battery... one row per day."""
    data = get(headers, "/usersummary-service/v2/dailysummaries",
               {"startDate": start.isoformat(), "endDate": end.isoformat()})["data"]
    rows = []
    for d in data:
        steps = d.get("movement", {}).get("steps", {})
        cal = d.get("calories", {})
        hr = d.get("heartRate", {})
        im = d.get("intensityMinutes", {})
        stress = d.get("stress", {})
        bb = d.get("bodyBattery", {})
        if not steps.get("value") and not cal.get("burnedTotal"):
            continue  # watch not worn that day
        rows.append({
            "date": d["calendarDate"],
            "steps": steps.get("value"),
            "step_goal": steps.get("goal"),
            "distance_km": round((steps.get("distanceInMeters") or 0) / 1000, 2),
            "cal_total": cal.get("burnedTotal"),
            "cal_active": cal.get("burnedActive"),
            "cal_resting": cal.get("burnedResting"),
            "resting_hr": hr.get("restingValue"),
            "max_hr": hr.get("maxValue"),
            "intensity_moderate": im.get("moderate") or 0,
            "intensity_vigorous": im.get("vigorous") or 0,
            "intensity_goal": im.get("goal"),
            "stress_avg": stress.get("avgLevel"),
            "body_battery_high": bb.get("maxValue"),
            "body_battery_low": bb.get("minValue"),
            "body_battery_charged": bb.get("chargedValue"),
            "body_battery_drained": bb.get("drainedValue"),
            "respiration_avg": d.get("respiration", {}).get("avgValue"),
        })
    return rows


def fetch_hrv(headers, start, end):
    data = get(headers, f"/hrv-service/hrv/daily/{start.isoformat()}/{end.isoformat()}")
    rows = []
    for h in data.get("hrvSummaries", []):
        base = h.get("baseline") or {}
        rows.append({
            "date": h["calendarDate"],
            "hrv_last_night": h.get("lastNightAvg"),
            "hrv_weekly": h.get("weeklyAvg"),
            "hrv_balanced_low": base.get("balancedLow"),
            "hrv_balanced_high": base.get("balancedUpper"),
            "hrv_status": h.get("status"),
        })
    return rows


def fetch_vo2(headers, start, end):
    data = get(headers, f"/metrics-service/metrics/maxmet/daily/{start.isoformat()}/{end.isoformat()}")
    return [{"date": v["generic"]["calendarDate"], "vo2max": v["generic"]["vo2MaxPreciseValue"]}
            for v in data if v.get("generic")]


def fetch_activities(headers, start):
    """Page through the activity list (newest first) until we pass `start`.
    Also returns the account's first name, which the activity list includes."""
    rows, offset, name = [], 0, None
    while True:
        page = get(headers, "/activitylist-service/activities/search/activities",
                   {"start": offset, "limit": 50})
        if not page:
            break
        for a in page:
            name = name or (a.get("ownerFullName") or "").split(" ")[0] or None
            day = a["startTimeLocal"][:10]
            if day < start.isoformat():
                return rows, name
            rows.append({
                "id": a["activityId"],
                "date": day,
                "start_time": a["startTimeLocal"][11:16],
                "name": a.get("activityName"),
                "type": a["activityType"]["typeKey"],
                "distance_km": round((a.get("distance") or 0) / 1000, 2),
                "duration_min": round((a.get("duration") or 0) / 60, 1),
                "moving_min": round((a.get("movingDuration") or a.get("duration") or 0) / 60, 1),
                "avg_speed": a.get("averageSpeed"),                 # metres per second
                "calories": a.get("calories"),
                "avg_hr": a.get("averageHR"),
                "max_hr": a.get("maxHR"),
                "training_effect": a.get("aerobicTrainingEffect"),
                "training_load": a.get("activityTrainingLoad"),
                "effect_label": a.get("trainingEffectLabel"),       # e.g. "LACTATE_THRESHOLD"
                "elevation_gain": a.get("elevationGain"),
                # Seconds spent in each heart-rate zone (1 = easiest, 5 = hardest)
                **{f"zone{z}_s": a.get(f"hrTimeInZone_{z}") for z in range(1, 6)},
            })
        offset += len(page)
    return rows, name


def fetch_weight(headers, start, end):
    """Weigh-ins entered in Garmin Connect (or from a Garmin scale): the last one each day, in kg."""
    data = get(headers, f"/weight-service/weight/range/{start.isoformat()}/{end.isoformat()}",
               {"includeAll": "true"})
    rows = []
    for d in data.get("dailyWeightSummaries", []):
        grams = (d.get("latestWeight") or {}).get("weight")
        if grams:
            rows.append({"date": d["summaryDate"], "kg": round(grams / 1000, 2), "source": "garmin"})
    return rows


def sync(days_back=30, progress=None):
    """Download the last `days_back` days from Garmin and save them in sleep.db.

    progress(fraction, message), if given, is called as each step starts (fraction goes
    from 0 to 1), so the app can show a progress bar.
    """
    report = progress or (lambda fraction, message: None)
    end = date.today()
    start = end - timedelta(days=days_back)
    total = len(chunks(start, end)) + 6  # sign in, sleep (in chunks), daily, HRV, VO2 max, weight, workouts
    done = 0

    def step(message):
        nonlocal done
        report(done / total, message)
        done += 1

    step("Signing in")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {get_token()}"}

    def sleep_step(i, n):  # sleep comes in month-sized chunks, so a long sync has several steps
        step(f"Sleep {i} of {n}" if n > 1 else "Sleep")

    nights = [to_row(n) for n in fetch_nights(headers, start, end, on_chunk=sleep_step) if n.get("sleepTimeSeconds")]
    upsert("sleep", nights, "date")

    step("Daily stats")
    daily = fetch_daily(headers, start, end)
    upsert("daily", daily, "date")

    step("Heart rate variability")
    upsert("hrv", fetch_hrv(headers, start, end), "date")

    step("VO2 max")
    upsert("vo2", fetch_vo2(headers, start, end), "date")

    step("Weight")
    try:  # weigh-ins are few, so always look two years back
        save_garmin_weights(fetch_weight(headers, end - timedelta(days=max(days_back, 730)), end))
    except SystemExit:
        pass  # not essential: weight can still be logged in the app

    step("Workouts")
    activities, name = fetch_activities(headers, start)
    upsert("activities", activities, "id")

    if name:
        set_meta("first_name", name)
    set_meta("last_sync", datetime.now().isoformat(timespec="seconds"))
    report(1.0, "Done")
    return {"nights": len(nights), "days": len(daily), "activities": len(activities)}


def print_progress(fraction, message):
    """A text progress bar for the terminal: [##########..........]  50%  Daily stats"""
    filled = round(fraction * 20)
    print(f"[{'#' * filled}{'.' * (20 - filled)}] {fraction:4.0%}  {message}")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    result = sync(days, progress=print_progress)
    print(f"Done: {result['nights']} nights, {result['days']} days, {result['activities']} activities")

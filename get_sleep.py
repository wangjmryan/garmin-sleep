import csv
import sys
from datetime import date, datetime, timedelta, timezone

import requests

from db import save_sleep
from get_token import get_token

SLEEP_URL = "https://personal.connectapi.garmin.com/sleep-service/sleep/dailySleepSummariesByDate"
MAX_SPAN = 31  # Garmin rejects requests spanning more than ~32 days, so fetch in chunks


def chunks(start, end):
    """Split start..end into (from, to) date ranges Garmin will accept."""
    ranges = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=MAX_SPAN), end)
        ranges.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return ranges


def fetch_nights(headers, start, end, on_chunk=None):
    """Download every night between start and end, one chunk at a time.
    on_chunk(i, n), if given, is called before each request (used for progress bars)."""
    nights = []
    ranges = chunks(start, end)
    for i, (chunk_start, chunk_end) in enumerate(ranges, 1):
        if on_chunk:
            on_chunk(i, len(ranges))
        params = {"startDate": chunk_start.isoformat(), "endDate": chunk_end.isoformat()}
        response = requests.get(SLEEP_URL, headers=headers, params=params, timeout=60)
        if response.status_code != 200:
            raise SystemExit(f"Sleep request failed ({response.status_code}): {response.text}")
        nights.extend(response.json())  # a list with one dictionary per night
    return nights


def to_clock(ms):
    """Garmin's *Local timestamps are milliseconds; turn one into 'HH:MM'."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%H:%M")


def to_hours(seconds):
    return round(seconds / 3600, 1)


BASIC_FIELDS = ["date", "bedtime", "wake_time", "total_sleep_hours", "deep_hours", "rem_hours", "sleep_score"]


def to_row(night):
    scores = night.get("sleepScores") or {}
    need = night.get("sleepNeed") or {}           # Garmin's sleep need for this night
    next_need = night.get("nextSleepNeed") or {}  # ...and for the following night

    def rating(part):
        """Garmin rates each part of the score, e.g. 'EXCELLENT', 'GOOD', 'FAIR', 'POOR'."""
        return (scores.get(part) or {}).get("qualifierKey")

    return {
        # The basics (same columns as sample_sleep.csv)
        "date": night["calendarDate"],
        "bedtime": to_clock(night["sleepStartTimestampLocal"]),
        "wake_time": to_clock(night["sleepEndTimestampLocal"]),
        "total_sleep_hours": to_hours(night["sleepTimeSeconds"]),
        "deep_hours": to_hours(night["deepSleepSeconds"]),
        "rem_hours": to_hours(night["remSleepSeconds"]),
        "sleep_score": scores.get("overall", {}).get("value"),
        # Extra detail for the dashboard
        "awake_min": round((night.get("awakeSleepSeconds") or 0) / 60),
        "sleep_stress": night.get("avgSleepStress"),
        "need_min": need.get("actual"),            # minutes Garmin said you needed
        "need_base_min": need.get("baseline"),     # your normal need, before adjustments
        "next_need_date": next_need.get("calendarDate"),
        "next_need_min": next_need.get("actual"),
        "next_need_base_min": next_need.get("baseline"),
        "next_bed_start_min": next_need.get("recommendedBedtimeStartMins"),  # minutes after midnight
        "next_bed_end_min": next_need.get("recommendedBedtimeEndMins"),
        # Why Garmin raised or lowered the need ("NO_CHANGE", "INCREASING", ...)
        "next_need_history": next_need.get("sleepHistoryAdjustment"),
        "next_need_hrv": next_need.get("hrvAdjustment"),
        "next_need_training": next_need.get("trainingFeedback"),
        "next_need_nap": next_need.get("napAdjustment"),
        "q_duration": rating("totalDuration"),
        "q_stress": rating("stress"),
        "q_awake": rating("awakeCount"),
        "q_restless": rating("restlessness"),
        "q_deep": rating("deepPercentage"),
        "q_rem": rating("remPercentage"),
        "q_light": rating("lightPercentage"),
    }


if __name__ == "__main__":
    # How many days back to fetch: `python get_sleep.py 180`, or 30 by default
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    end = date.today()
    start = end - timedelta(days=days_back)

    token = get_token()
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    nights = fetch_nights(headers, start, end)

    # Nights with no data (watch not worn / not synced yet) come back empty - skip them
    rows = [to_row(n) for n in nights if n.get("sleepTimeSeconds")]
    if not rows:
        raise SystemExit("No sleep data in that range. Has your watch synced?")

    # Same columns as sample_sleep.csv, so your practice code works on real data
    with open("my_sleep.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BASIC_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Also store in the database, which keeps every night you've ever fetched
    save_sleep(rows)

    print(f"Saved {len(rows)} nights ({rows[0]['date']} to {rows[-1]['date']}) to my_sleep.csv and sleep.db")

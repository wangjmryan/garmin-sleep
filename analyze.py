"""Print sleep patterns and save charts to the charts/ folder.

Run:  python analyze.py
"""
import os

import matplotlib
matplotlib.use("Agg")  # draw to files, no window needed
import matplotlib.pyplot as plt

from db import format_bedtime, load_sleep

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

df = load_sleep()
if df.empty:
    raise SystemExit("No data yet - run `python get_sleep.py` first.")

os.makedirs("charts", exist_ok=True)

# ---------- Summary numbers ----------
print(f"Nights: {len(df)}  ({df['date'].min():%b %d} to {df['date'].max():%b %d, %Y})\n")
print(f"Average sleep:     {df['total_sleep_hours'].mean():.1f} h")
print(f"Average score:     {df['sleep_score'].mean():.0f}")
print(f"Average bedtime:   {format_bedtime(df['bedtime_hours'].mean())}")
print(f"Nights under 7h:   {(df['total_sleep_hours'] < 7).sum()} ({(df['total_sleep_hours'] < 7).mean():.0%})")

best = df.loc[df["sleep_score"].idxmax()]
worst = df.loc[df["sleep_score"].idxmin()]
print(f"Best night:        {best['date']:%a %b %d} - score {best['sleep_score']}, {best['total_sleep_hours']}h, bed {best['bedtime']}")
print(f"Worst night:       {worst['date']:%a %b %d} - score {worst['sleep_score']}, {worst['total_sleep_hours']}h, bed {worst['bedtime']}")

# ---------- What goes with a good score? ----------
print("\nHow strongly each thing moves with your sleep score (-1 to +1):")
corr = df[["bedtime_hours", "total_sleep_hours", "deep_hours", "rem_hours"]].corrwith(df["sleep_score"])
labels = {"bedtime_hours": "Later bedtime", "total_sleep_hours": "More total sleep",
          "deep_hours": "More deep sleep", "rem_hours": "More REM sleep"}
for col, value in corr.sort_values().items():
    print(f"  {labels[col]:<18} {value:+.2f}")

# Bedtime buckets
df["bed_bucket"] = df["bedtime_hours"].apply(
    lambda h: "before 00:00" if h < 24 else "00:00-01:59" if h < 26 else "02:00 or later")
print("\nBy bedtime:")
print(df.groupby("bed_bucket")[["sleep_score", "total_sleep_hours"]].mean().round(1)
        .assign(nights=df["bed_bucket"].value_counts()).to_string())

by_day = df.groupby("weekday")[["sleep_score", "total_sleep_hours"]].mean().reindex(WEEKDAYS)
print("\nBy day of the week (the night before that date):")
print(by_day.round(1).to_string())

# ---------- Charts ----------
# 1. Score over time with a 7-night rolling average
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(df["date"], df["sleep_score"], marker="o", markersize=3, alpha=0.4, label="Nightly")
ax.plot(df["date"], df["sleep_score"].rolling(7, min_periods=3).mean(), linewidth=2.5, label="7-night average")
ax.set_title("Sleep score over time")
ax.set_ylabel("Score")
ax.legend()
fig.tight_layout()
fig.savefig("charts/score_over_time.png", dpi=120)

# 2. Bedtime vs score
fig, ax = plt.subplots(figsize=(7, 5))
ax.scatter(df["bedtime_hours"], df["sleep_score"], alpha=0.7)
ticks = range(21, 30)
ax.set_xticks(list(ticks), [format_bedtime(t) for t in ticks])
ax.set_title("Does going to bed later hurt your score?")
ax.set_xlabel("Bedtime")
ax.set_ylabel("Sleep score")
fig.tight_layout()
fig.savefig("charts/bedtime_vs_score.png", dpi=120)

# 3. Sleep stages per night
fig, ax = plt.subplots(figsize=(10, 4))
light = df["total_sleep_hours"] - df["deep_hours"] - df["rem_hours"]
ax.bar(df["date"], df["deep_hours"], label="Deep")
ax.bar(df["date"], df["rem_hours"], bottom=df["deep_hours"], label="REM")
ax.bar(df["date"], light, bottom=df["deep_hours"] + df["rem_hours"], label="Light")
ax.axhline(7, color="gray", linestyle="--", linewidth=1, label="7 h")
ax.set_title("Sleep stages per night")
ax.set_ylabel("Hours")
ax.legend(ncol=4)
fig.tight_layout()
fig.savefig("charts/sleep_stages.png", dpi=120)

# 4. Average score by weekday
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar([d[:3] for d in WEEKDAYS], by_day["sleep_score"])
ax.set_ylim(by_day["sleep_score"].min() - 10, 100)
ax.set_title("Average sleep score by day")
fig.tight_layout()
fig.savefig("charts/score_by_weekday.png", dpi=120)

print("\nCharts saved in charts/")

# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person: the owner, who trains for triathlon (swim, bike, run) and general fitness and wears a Garmin watch. They open the dashboard on both their phone (over home Wi-Fi) and their computer. The project is also their Python learning project.

## Product Purpose

A personal dashboard over the owner's own Garmin data. It helps with five jobs, all confirmed as wanted:

1. **Quick daily check-in:** how did I sleep, and how recovered am I?
2. **Sleep more and earlier:** what's the best time to fall asleep tonight, and am I getting enough over the week?
3. **Train smarter:** what workout should I do today (how hard, which sport, finished by when), and is my swim/bike/run mix and intensity balanced?
4. **See progress:** am I getting fitter and faster over weeks and months?
5. **Weight and fuel:** log weight quickly, see its trend, and know how many calories I burn and should eat for my goal.

Success means one glance answers "what should I do today and tonight", and every trend can be read without sports-science knowledge.

## Positioning

Garmin Connect spreads this data across many screens of raw metrics. This app answers a few plain-language questions using findings computed from the owner's own history, such as which habits actually move their sleep score.

## Operating Context

- **Where it runs:** locally. `app.py` is a Streamlit app on the owner's Windows PC, launched from a desktop shortcut (`Sleep Dashboard.bat`) and viewed in a browser on the PC or on the phone over the local network.
- **How data arrives:** `sync.py` pulls from the Garmin Connect Personal API into SQLite (`sleep.db`). The watch syncs to Garmin through the phone app, so the dashboard can only show what Garmin's servers have.
- **When it's used:** typical moments are the morning check-in, evening bedtime planning, and after workouts.

## Capabilities and Constraints

- **Available from the API:**
  - Sleep summaries: score, stages, the score's component ratings, Garmin's personal sleep need, and its recommended bedtime window.
  - Daily summaries: steps, calories, resting HR, intensity minutes, stress, Body Battery.
  - Nightly HRV with its balanced range, and running VO₂ max.
  - Activities: distance, duration, speed, HR, training load, training-effect label, and time in each HR zone.
  - Weigh-ins entered in Garmin Connect (`/weight-service/weight/range/{start}/{end}`), and account settings (metric units).
- **Not available from the API:** Garmin's Training Readiness and Training Status, heart-rate zone settings, and the user profile (height, age). Anything the app computes must not be presented as Garmin's own metric. The API is read-only, so weight logged in the app stays in `sleep.db`.
- **API limits:** the API key lives in the `GARMIN_API_KEY` environment variable, tokens last 24 hours, and sleep range requests are limited to about 32 days.
- **Stack:** Python, Streamlit, Altair, pandas, SQLite. Code must stay readable for a learner.
- **Locale:** follows the Windows settings (12-hour clock).
- **Scope:** single user, no accounts, no external hosting.

## Brand Commitments

The owner supplied a visual reference: a dark native fitness-app screen with dark slate cards, an orange accent, large numerals and a segmented section control. It is binding direction for the look.

## Evidence on Hand

The owner's real data lives in `sleep.db` on their computer and is never committed: months of sleep, daily stats, HRV and VO₂ max history, activities, weigh-ins and meals. It has gaps (the watch wasn't always worn), so every view must handle missing days.

No synthetic or demo data may be shown as real.

## Product Principles

1. **Answer first, evidence second.** Each screen leads with the decision it supports, such as "be asleep by…" or "push or ease off", with the supporting data underneath.
2. **Personal baselines over generic norms.** Compare against the owner's own normal ranges and Garmin's personalized targets.
3. **Plain language and honest uncertainty.** Say when a finding rests on few nights or workouts, and never invent metrics or pass computed ones off as Garmin's.
4. **Calm and quick.** A morning check-in takes one glance on a phone. Anything that doesn't change a decision or show progress stays off the screen.
5. **Readable code.** The owner is learning Python from this codebase.

"""Everything that talks to the SQLite database (sleep.db) lives here."""
import sqlite3

import pandas as pd

DB_FILE = "sleep.db"

HABITS = {
    "caffeine_late": "Caffeine after 2pm",
    "alcohol": "Alcohol",
    "exercise": "Exercised",
    "screens_late": "Screens in bed",
}


def connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sleep (
            date TEXT PRIMARY KEY,
            bedtime TEXT,
            wake_time TEXT,
            total_sleep_hours REAL,
            deep_hours REAL,
            rem_hours REAL,
            sleep_score INTEGER
        )
    """)
    habit_cols = ", ".join(f"{h} INTEGER DEFAULT 0" for h in HABITS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS habits (
            date TEXT PRIMARY KEY,
            {habit_cols},
            notes TEXT
        )
    """)
    # Small key/value store for things like "when did we last sync?"
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def upsert(table, rows, key):
    """Insert rows (a list of dicts), replacing any row with the same key.

    Creates the table if needed, and adds any new columns automatically - so when
    sync.py starts saving a new field, old databases keep working.
    """
    if not rows:
        return
    cols = list(dict.fromkeys(k for r in rows for k in r))  # every key, in first-seen order
    with connect() as conn:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({key} PRIMARY KEY)")
        existing = table_columns(conn, table)
        for c in cols:
            if c not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {c}")
        placeholders = ", ".join(f":{c}" for c in cols)
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            [{c: r.get(c) for c in cols} for r in rows])


def load(table, order="date"):
    """Load a whole table as a DataFrame (empty if the table doesn't exist yet)."""
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            return pd.DataFrame()
        df = pd.read_sql(f"SELECT * FROM {table} ORDER BY {order}", conn)
    if "date" in df:
        df["date"] = pd.to_datetime(df["date"])
    return df


def get_meta(key, default=None):
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(key, value):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))


def save_sleep(rows):
    upsert("sleep", rows, "date")


def save_habits(day, habits, notes=""):
    """habits is a dict like {"alcohol": True, "exercise": False, ...}."""
    cols = list(HABITS)
    values = [day] + [int(bool(habits.get(h))) for h in cols] + [notes]
    placeholders = ", ".join("?" for _ in values)
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO habits (date, {', '.join(cols)}, notes) VALUES ({placeholders})",
            values,
        )


def load_sleep():
    df = load("sleep")
    if df.empty:
        return df
    return add_columns(df)


def load_weight():
    """Weigh-ins in kg, oldest first (deleted ones left out)."""
    df = load("weight")
    if df.empty:
        return df
    return df[df["source"] != "deleted"].dropna(subset=["kg"]).reset_index(drop=True)


def save_weight(day, kg, source="app"):
    """Save one weigh-in. `day` is 'YYYY-MM-DD'; saving the same day again replaces it."""
    upsert("weight", [{"date": day, "kg": round(float(kg), 2), "source": source}], "date")


def delete_weight(day):
    """Remove a weigh-in. It's kept as 'deleted' so the next sync doesn't bring a Garmin copy back."""
    upsert("weight", [{"date": day, "kg": None, "source": "deleted"}], "date")


def save_garmin_weights(rows):
    """Add weigh-ins from Garmin without overwriting ones entered (or deleted) in this app."""
    existing = load("weight")
    mine = set()
    if not existing.empty:
        mine = set(existing.loc[existing["source"] != "garmin", "date"].dt.strftime("%Y-%m-%d"))
    upsert("weight", [r for r in rows if r["date"] not in mine], "date")


def save_meal(meal):
    """Save one meal (a dict with date, time, meal, name, calories, protein_g, ...)."""
    meal = dict(meal)
    meal.setdefault("id", f"{meal['date']}T{meal['time']}:{len(load('meals'))}")
    upsert("meals", [meal], "id")


def delete_meal(meal_id):
    with connect() as conn:
        conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))


def load_meals():
    """Every meal logged, oldest first."""
    return load("meals", order="date, time")


def save_classes(meetings):
    """Replace the saved class schedule with a new one (a list of dicts from schedule.parse)."""
    with connect() as conn:
        conn.execute("DROP TABLE IF EXISTS classes")
    for i, m in enumerate(meetings):
        m["id"] = i
    upsert("classes", meetings, "id")


def load_classes():
    """The saved class schedule as a list of dicts (empty if none)."""
    df = load("classes", order="id")
    if df.empty:
        return []
    df["first_day"] = df["first_day"].astype(str)
    df["last_day"] = df["last_day"].astype(str)
    df["days"] = df["days"].astype(str)
    return df.to_dict("records")


def load_habits():
    with connect() as conn:
        return pd.read_sql("SELECT * FROM habits ORDER BY date", conn)


def bedtime_to_hours(clock):
    """'23:30' -> 23.5, '01:15' -> 25.25 (so after-midnight bedtimes sort as 'later')."""
    h, m = map(int, clock.split(":"))
    hours = h + m / 60
    return hours + 24 if hours < 18 else hours


def add_columns(df):
    """Extra columns that make analysis easier."""
    df["bedtime_hours"] = df["bedtime"].apply(bedtime_to_hours)
    df["weekday"] = df["date"].dt.day_name()
    df["light_hours"] = (df["total_sleep_hours"] - df["deep_hours"] - df["rem_hours"]).round(1)
    df["deep_pct"] = (df["deep_hours"] / df["total_sleep_hours"] * 100).round(1)
    df["rem_pct"] = (df["rem_hours"] / df["total_sleep_hours"] * 100).round(1)
    return df


def format_bedtime(hours):
    """25.25 -> '01:15'."""
    hours = hours % 24
    h, m = int(hours), int(round(hours % 1 * 60))
    if m == 60:
        h, m = (h + 1) % 24, 0
    return f"{h:02d}:{m:02d}"

"""Read a class schedule pasted from a student portal's
class list (PeopleSoft-style "List View") and work out
when your first class is each day.

Each class meeting in the paste looks like:
    MWF 8:30AM - 9:20AM     <- days and times
    ENG 101                 <- room (ignored)
    ...
    01/06/2026 - 04/07/2026 <- the dates it runs between
"""
import re
from datetime import date, datetime, timedelta

COURSE = re.compile(r"^([A-Z]{2,6}\s?\d{2,3}[A-Z]?)\s+-\s+")                 # "MATH 101 - Calculus"
COMPONENT = re.compile(r"^(LEC|TUT|LAB|SEM|TST|PRA|DIS|STU|CLN|ESS|OLN|PRJ|RDG|WRK)$")
TIMES = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}:\d{2}\s?[AP]M)\s*-\s*(\d{1,2}:\d{2}\s?[AP]M)$")
DATES = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})$")
DAY = re.compile(r"Th|Sa|Su|M|T|W|F")
WEEKDAY = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5, "Su": 6}

WAKE_BEFORE_MIN = 50  # default: wake up this long before your first class (changeable in the app)


def to_hours(text):
    """'8:30AM' -> 8.5"""
    t = datetime.strptime(text.replace(" ", ""), "%I:%M%p")
    return t.hour + t.minute / 60


def parse(text):
    """Turn the pasted schedule into a list of class meetings (one dict each)."""
    meetings, course, component, pending = [], None, None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if m := COURSE.match(line):
            course = m.group(1).replace("  ", " ")
        elif COMPONENT.match(line):
            component = line
        elif m := TIMES.match(line):
            days = DAY.findall(m.group(1))
            if days and "".join(days) == m.group(1):  # really a days code like "MWF" or "TTh"
                pending = {"course": course, "component": component, "days": "".join(str(WEEKDAY[d]) for d in days),
                           "start": to_hours(m.group(2)), "end": to_hours(m.group(3))}
        elif (m := DATES.match(line)) and pending:
            first, last = (datetime.strptime(d, "%m/%d/%Y").date().isoformat() for d in m.groups())
            meetings.append({**pending, "first_day": first, "last_day": last})
            pending = None
    return meetings


def classes_on(meetings, day):
    """Class meetings happening on `day`, earliest first."""
    iso, weekday = day.isoformat(), str(day.weekday())
    today = [m for m in meetings if m["first_day"] <= iso <= m["last_day"] and weekday in m["days"]]
    return sorted(today, key=lambda m: m["start"])


def first_class(meetings, day):
    """The earliest class on `day`, or None if there isn't one."""
    found = classes_on(meetings, day)
    return found[0] if found else None


def class_wake(meetings, day, buffer_min=WAKE_BEFORE_MIN):
    """Wake-up time (hours) for `day`: `buffer_min` minutes before the first class. None on days off."""
    first = first_class(meetings, day)
    return None if first is None else first["start"] - buffer_min / 60


def term_end(meetings):
    return max((m["last_day"] for m in meetings), default=None)


def week_ahead(meetings, start, days=7):
    """(day, first class or None) for each of the next `days` days."""
    return [(start + timedelta(days=i), first_class(meetings, start + timedelta(days=i))) for i in range(days)]


if __name__ == "__main__":  # quick check: python schedule.py < my_schedule.txt
    import sys
    found = parse(sys.stdin.read())
    print(f"{len(found)} class meetings")
    for d, c in week_ahead(found, date.today()):
        print(d, c and f"{c['course']} {c['component']} at {c['start']:.2f}")

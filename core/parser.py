# schedule_app/core/parser.py

import re
import pandas as pd

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

def time_to_hour(t):
    """Convert time string to decimal hour (e.g. '14:30' -> 14.5)"""
    if isinstance(t, str):
        parts = t.split(":")
        if len(parts) == 2:
            try:
                return int(parts[0]) + int(parts[1]) / 60
            except ValueError:
                pass
    # fallback for bad formats
    try:
        return float(t)
    except:
        return 0.0

def format_time_ampm(time_str):
    """Format 'HH:MM' to 'h:MM AM/PM'"""
    try:
        hour, minute = map(int, time_str.split(":"))
        period = "AM" if hour < 12 else "PM"
        hour = hour % 12
        if hour == 0:
            hour = 12
        return f"{hour}:{minute:02d} {period}"
    except:
        return time_str

def parse_availability(raw_string):
    """Parse availability like 'Monday 12:00-15:00, Tue 14:00-18:00' into structured dict"""
    if pd.isna(raw_string) or not raw_string:
        return {}
    day_map = {
        "sunday": "Sunday", "sun": "Sunday",
        "monday": "Monday", "mon": "Monday",
        "tuesday": "Tuesday", "tue": "Tuesday",
        "wednesday": "Wednesday", "wed": "Wednesday",
        "thursday": "Thursday", "thu": "Thursday",
        "friday": "Friday", "fri": "Friday",
        "saturday": "Saturday", "sat": "Saturday"
    }
    availability = {}
    blocks = re.split(r',\s*', str(raw_string))
    for block in blocks:
        m = re.match(
            r'(\w+)\s+(\d{1,2}:\d{2})-(\d{1,2}:\d{2})',
            block.strip(), re.IGNORECASE
        )
        if not m:
            continue
        day_raw, start, end = m.groups()
        day = day_map.get(day_raw.lower())
        if not day:
            continue
        sh = time_to_hour(start)
        eh = time_to_hour(end)
        # if end ≤ start assume next-day (e.g. 00:00 → 24:00)
        if eh <= sh:
            eh += 24.0
        availability.setdefault(day, []).append({
            "start":       start,
            "end":         end,
            "start_hour":  sh,
            "end_hour":    eh
        })
    return availability

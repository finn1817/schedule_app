# schedule_app/core/scheduler.py

import random
import logging
from datetime import datetime
from .parser import time_to_hour, format_time_ampm, parse_availability
from core.config import DAYS

def hour_to_time_str(hour: float) -> str:
    """Convert decimal hour to HH:MM (24h), allowing values up to 24:00."""
    h = int(hour)
    m = int(round((hour - h) * 60))
    return f"{h:02d}:{m:02d}"

def overlaps(s1: float, e1: float, s2: float, e2: float) -> bool:
    return max(s1, s2) < min(e1, e2)

def is_worker_available(worker: dict, day: str,
                        shift_start: float, shift_end: float) -> bool:
    """True if `worker` is free on `day` from shift_start→shift_end."""
    for a in worker.get('availability', {}).get(day, []):
        if a['start_hour'] <= shift_start and shift_end <= a['end_hour']:
            return True
    return False

def find_alternative_workers(workers: list,
                             day: str,
                             start: float,
                             end: float,
                             assigned_hours: dict,
                             max_hours: float,
                             already_assigned: list):
    """Return a sorted list of workers who could cover day start→end."""
    alts = []
    for w in workers:
        em = w['email']
        if em in already_assigned:
            continue
        if is_worker_available(w, day, start, end) and \
           assigned_hours.get(em, 0) + (end - start) <= max_hours:
            alts.append(w)
    alts.sort(key=lambda w: assigned_hours.get(w['email'], 0))
    return alts

def create_shifts_from_availability(hours_of_operation: dict,
                                    workers: list,
                                    workplace: str,
                                    max_hours_per_worker: float,
                                    max_workers_per_shift: int):
    """
    Returns:
      schedule: dict[day, list of shift dicts],
      assigned_hours: dict[email, float],
      low_hours: list[str],
      unassigned: list[str],
      alt_sols: dict[key→list[str]],
      unfilled_shifts: list[shift dict],
      ws_issues: list[str]
    """
    random.seed(datetime.now().timestamp())

    schedule = {}
    unfilled_shifts = []
    shift_lengths = [2, 3, 4, 5]
    random.shuffle(shift_lengths)

    # track how many hours each email has
    assigned_hours = {w['email']: 0 for w in workers}
    ws_status      = {w['email']: w.get('work_study', False) for w in workers}
    ws_workers     = [w for w in workers if ws_status[w['email']]]
    random.shuffle(ws_workers)

    #
    # 1) Allocate exactly 5 hours to each work-study, possibly split across multiple sub-shifts
    #
    for w in ws_workers:
        em = w['email']
        remaining = 5.0

        # gather all the intersections of (hours_of_operation × worker availability)
        windows = []
        for day, ops in hours_of_operation.items():
            for op in ops:
                op_start = time_to_hour(op['start'])
                op_end   = time_to_hour(op['end'])
                if op_end <= op_start:
                    op_end += 24

                for a in w.get('availability', {}).get(day, []):
                    av_start = a['start_hour']
                    av_end   = a['end_hour']
                    s = max(op_start, av_start)
                    e = min(op_end, av_end)
                    if e > s:
                        windows.append((day, s, e))

        # sort by day order and start time
        windows.sort(key=lambda x: (DAYS.index(x[0]), x[1]))

        # carve off exactly `remaining` hours from those windows
        for day, s, e in windows:
            if remaining <= 0:
                break
            window_len = e - s
            if window_len <= 0:
                continue

            take = min(window_len, remaining)
            seg_start = s
            seg_end   = s + take

            # record a work-study shift
            schedule.setdefault(day, []).append({
                "start":        hour_to_time_str(seg_start),
                "end":          hour_to_time_str(seg_end),
                "assigned":     [f"{w['first_name']} {w['last_name']}"],
                "available":    [f"{w['first_name']} {w['last_name']}"],
                "raw_assigned": [em],
                "all_available": [w],
                "is_work_study": True
            })

            assigned_hours[em] += take
            remaining       -= take

        if remaining > 0:
            # mark issue—will show up in your ws_issues list
            logging.warning(
                f"Work-study {w['first_name']} {w['last_name']} "
                f"only got {5-remaining:.1f}h out of 5h"
            )

    #
    # 2) Fill remaining hours-of-operation windows as before
    #
    days = list(hours_of_operation.keys())
    random.shuffle(days)
    for day in days:
        ops = hours_of_operation.get(day, [])
        if not ops:
            continue
        schedule.setdefault(day, [])

        for op in ops:
            op_start = time_to_hour(op['start'])
            op_end   = time_to_hour(op['end'])
            if op_end <= op_start:
                op_end += 24

            # subtract out already-scheduled blocks to get free slots
            free_slots = [(op_start, op_end)]
            for blk in schedule[day]:
                s1 = time_to_hour(blk['start'])
                e1 = time_to_hour(blk['end'])
                new_free = []
                for (s0, e0) in free_slots:
                    if e0 <= s1 or s0 >= e1:
                        new_free.append((s0, e0))
                    else:
                        if s0 < s1:
                            new_free.append((s0, s1))
                        if e0 > e1:
                            new_free.append((e1, e0))
                free_slots = new_free

            # within each free slot, carve shifts of random length
            for (s0, e0) in free_slots:
                if (e0 - s0) < 2:
                    continue
                lengths = [l for l in shift_lengths if l <= (e0 - s0)] or [2]
                cur = s0
                while cur < e0:
                    random.shuffle(lengths)
                    length    = next((l for l in lengths if cur + l <= e0), lengths[0])
                    end_shift = min(cur + length, e0)

                    # pick available workers
                    avail = []
                    for x in workers:
                        x_em = x['email']
                        if ws_status.get(x_em, False) and assigned_hours[x_em] >= 5:
                            continue
                        # ensure WS only gets their 5h in phase 1
                        if ws_status.get(x_em, False) and assigned_hours[x_em] == 0 \
                           and (end_shift - cur) != 5:
                            continue
                        if is_worker_available(x, day, cur, end_shift) and \
                           assigned_hours[x_em] + (end_shift - cur) <= max_hours_per_worker:
                            avail.append(x)

                    avail.sort(key=lambda x: (assigned_hours[x['email']], random.random()))
                    chosen = avail[:max_workers_per_shift]

                    # assign those chosen
                    for x in chosen:
                        assigned_hours[x['email']] += (end_shift - cur)

                    # record individual shifts—one entry per worker
                    for x in chosen:
                        schedule[day].append({
                            "start":        hour_to_time_str(cur),
                            "end":          hour_to_time_str(end_shift),
                            "assigned":     [f"{x['first_name']} {x['last_name']}"],
                            "available":    [f"{y['first_name']} {y['last_name']}" for y in avail],
                            "raw_assigned": [x['email']],
                            "all_available": avail
                        })

                    # if we didn’t fill up to max_workers, mark unfilled slots
                    for _ in range(max_workers_per_shift - len(chosen)):
                        unfilled_shifts.append({
                            "day":        day,
                            "start":      hour_to_time_str(cur),
                            "end":        hour_to_time_str(end_shift),
                            "start_hour": cur,
                            "end_hour":   end_shift
                        })
                        schedule[day].append({
                            "start":        hour_to_time_str(cur),
                            "end":          hour_to_time_str(end_shift),
                            "assigned":     ["Unfilled"],
                            "available":    [f"{y['first_name']} {y['last_name']}" for y in avail],
                            "raw_assigned": [],
                            "all_available": avail
                        })

                    cur = end_shift

    #
    # 3) Build summaries
    #
    low_hours = [
        f"{w['first_name']} {w['last_name']}"
        for w in workers
        if not ws_status[w['email']] and assigned_hours[w['email']] < 4
    ]
    unassigned = [
        f"{w['first_name']} {w['last_name']}"
        for w in workers
        if assigned_hours[w['email']] == 0
    ]
    ws_issues = [
        f"{w['first_name']} {w['last_name']} ({assigned_hours[w['email']]}h)"
        for w in workers
        if ws_status[w['email']] and assigned_hours[w['email']] != 5
    ]

    # alternative solutions for any unfilled
    alt_sols = {}
    for us in unfilled_shifts:
        key = f"{us['day']} {us['start']}-{us['end']}"
        sols = find_alternative_workers(
            workers, us['day'], us['start_hour'], us['end_hour'],
            assigned_hours, max_hours_per_worker * 1.5, []
        )
        if sols:
            alt_sols[key] = [f"{w['first_name']} {w['last_name']}" for w in sols]

    return schedule, assigned_hours, low_hours, unassigned, alt_sols, unfilled_shifts, ws_issues

# schedule_app/core/scheduler.py

import random
import logging
from datetime import datetime
from .parser import time_to_hour, format_time_ampm, parse_availability
from .data import get_workers, get_hours_of_operation
from core.config import DAYS

# Setup logging
logger = logging.getLogger(__name__)

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

def find_optimal_shift_split(windows, remaining_hours, prefer_split=True):
    """
    Find an optimal split of shifts for a work study student
    
    Args:
        windows: List of (day, start, end) availability windows
        remaining_hours: Target hours to allocate (typically 5.0)
        prefer_split: Whether to prefer 3+2 or 2+3 splits versus a single 5-hour shift
        
    Returns:
        List of (day, start, end, duration) shift assignments
    """
    if not windows or remaining_hours <= 0:
        return []
    
    # If not enough total availability
    total_available = sum(end - start for _, start, end in windows)
    if total_available < remaining_hours:
        # Just return all available windows
        return [(day, start, end, end - start) for day, start, end in windows]
    
    # Check for perfect 3+2 or 2+3 splits
    if prefer_split and remaining_hours == 5.0:
        # Look for ~3 hour windows
        for i, (day1, s1, e1) in enumerate(windows):
            if 2.8 <= (e1 - s1) <= 3.2:  # ~3 hours
                # Look for complementary ~2 hour windows
                for j, (day2, s2, e2) in enumerate(windows):
                    if i != j and 1.8 <= (e2 - s2) <= 2.2:  # ~2 hours
                        return [
                            (day1, s1, s1 + 3.0, 3.0),
                            (day2, s2, s2 + 2.0, 2.0)
                        ]
    
    # No perfect split found, try to maximize shift distribution
    # Sort by duration (prefer shorter shifts for more flexibility)
    sorted_windows = sorted(windows, key=lambda w: w[2] - w[1])
    
    result = []
    remaining = remaining_hours
    
    # Try to make shifts not too long (split if a window is too long)
    for day, start, end in sorted_windows:
        if remaining <= 0:
            break
        
        window_duration = end - start
        
        # If window is long enough, try to break it up
        if prefer_split and window_duration >= 4.5 and remaining == 5.0:
            # Create 3+2 split in the same day
            result.append((day, start, start + 3.0, 3.0))
            result.append((day, start + 3.0, start + 5.0, 2.0))
            remaining = 0
            break
        
        # Otherwise just take what we need from this window
        take = min(window_duration, remaining)
        result.append((day, start, start + take, take))
        remaining -= take
    
    return result

def calculate_availability_hours(worker):
    """Calculate total hours a worker is available per week"""
    total_hours = 0
    for day_slots in worker.get('availability', {}).values():
        for slot in day_slots:
            total_hours += slot['end_hour'] - slot['start_hour']
    return total_hours

def check_work_study_availability(ws_workers, hours_of_operation):
    """
    Check if work study students have sufficient availability
    matching hours of operation
    
    Returns:
        List of (worker, issue) tuples for workers with insufficient availability
    """
    issues = []
    
    for worker in ws_workers:
        # Calculate total available hours that match hours of operation
        matching_hours = 0
        for day, ops in hours_of_operation.items():
            for op in ops:
                op_start = time_to_hour(op['start'])
                op_end = time_to_hour(op['end'])
                if op_end <= op_start:
                    op_end += 24
                    
                # Check worker's availability against this hours of operation
                for a in worker.get('availability', {}).get(day, []):
                    av_start = a['start_hour']
                    av_end = a['end_hour']
                    # Calculate overlap
                    overlap_start = max(op_start, av_start)
                    overlap_end = min(op_end, av_end)
                    if overlap_end > overlap_start:
                        matching_hours += (overlap_end - overlap_start)
        
        # If less than 5 hours available, report an issue
        if matching_hours < 5:
            issues.append((
                worker,
                f"Only {matching_hours:.1f} hours available during operating hours (needs 5)"
            ))
    
    return issues

def recently_scheduled(worker_email, day, shift_start, schedule, buffer_hours=0.5):
    """Check if a worker has been scheduled just before this shift"""
    if day not in schedule:
        return False
        
    for shift in schedule.get(day, []):
        if worker_email in shift.get('raw_assigned', []):
            shift_end = time_to_hour(shift['end'])
            # If this worker's last shift ended within buffer_hours of this one
            if abs(shift_end - shift_start) < buffer_hours:
                return True
    return False

def create_shifts_from_availability(hours_of_operation=None, workers=None, workplace_id=None, 
                                    max_hours_per_worker=20.0, max_workers_per_shift=2, min_hours_per_worker=3):
    """
    Create shifts from worker availability and hours of operation.
    
    This function can be called in two ways:
    1. With hours_of_operation and workers directly provided
    2. With just workplace_id provided (data fetched automatically)
    
    Args:
        hours_of_operation: Dictionary of hours of operation by day
        workers: List of worker data
        workplace_id: Workplace ID (to fetch data if not provided directly)
        max_hours_per_worker: Maximum hours per worker (default: 20.0)
        max_workers_per_shift: Maximum workers per shift (default: 2)
        min_hours_per_worker: Minimum hours for non-work-study workers (default: 3)
    
    Returns:
      schedule: dict[day, list of shift dicts],
      assigned_hours: dict[email, float],
      low_hours: list[str],
      unassigned: list[str],
      alt_sols: dict[key→list[str]],
      unfilled_shifts: list[shift dict],
      ws_issues: list[str],
      min_hours_issues: list[str]
    """
    # Determine how the function was called and get data accordingly
    if workplace_id and (hours_of_operation is None or workers is None):
        # Fetch data from database
        hours_of_operation = get_hours_of_operation(workplace_id)
        workers = get_workers(workplace_id)
    
    # Validate data
    if not hours_of_operation:
        logger.warning(f"No hours of operation provided")
        return {}, {}, [], [], {}, [], [], []
        
    if not workers:
        logger.warning(f"No workers provided")
        return {}, {}, [], [], {}, [], [], []
    
    random.seed(datetime.now().timestamp())

    schedule = {}
    unfilled_shifts = []
    shift_lengths = [2, 3, 4, 5]
    random.shuffle(shift_lengths)

    # track how many hours each email has
    assigned_hours = {w['email']: 0 for w in workers}
    ws_status = {w['email']: w.get('work_study', False) for w in workers}
    
    # Calculate availability ratio for each worker for fair distribution
    availability_hours = {w['email']: calculate_availability_hours(w) for w in workers}
    
    # Sort work study workers by availability (least available first to prioritize them)
    ws_workers = [w for w in workers if ws_status[w['email']]]
    ws_workers.sort(key=lambda w: availability_hours[w['email']])
    
    # Check for work study availability issues
    ws_availability_issues = check_work_study_availability(ws_workers, hours_of_operation)
    if ws_availability_issues:
        for worker, issue in ws_availability_issues:
            logger.warning(f"Work study {worker['first_name']} {worker['last_name']}: {issue}")
    
    # Initial work study issues
    initial_ws_issues = [
        f"{w['first_name']} {w['last_name']}: {issue}"
        for w, issue in ws_availability_issues
    ]

    #
    # 1) Allocate exactly 5 hours to each work-study, preferring 3+2 or 2+3 hour splits
    #
    for w in ws_workers:
        em = w['email']
        remaining = 5.0

        # gather all the intersections of (hours_of_operation × worker availability)
        windows = []
        for day, ops in hours_of_operation.items():
            for op in ops:
                op_start = time_to_hour(op['start'])
                op_end = time_to_hour(op['end'])
                if op_end <= op_start:
                    op_end += 24

                for a in w.get('availability', {}).get(day, []):
                    av_start = a['start_hour']
                    av_end = a['end_hour']
                    s = max(op_start, av_start)
                    e = min(op_end, av_end)
                    if e > s:
                        windows.append((day, s, e))

        # Find optimal shift splits (prefer 3+2 split for work-study)
        optimal_shifts = find_optimal_shift_split(windows, remaining, prefer_split=True)
        
        # Apply the optimal shifts
        for day, start, end, duration in optimal_shifts:
            # Enforce max_workers_per_shift
            slot_start = hour_to_time_str(start)
            slot_end = hour_to_time_str(end)
            existing_shifts = [
                s for s in schedule.get(day, [])
                if s['start'] == slot_start and s['end'] == slot_end
            ]
            if len(existing_shifts) < max_workers_per_shift:
                schedule.setdefault(day, []).append({
                    "start": slot_start,
                    "end": slot_end,
                    "assigned": [f"{w['first_name']} {w['last_name']}"],
                    "available": [f"{w['first_name']} {w['last_name']}"],
                    "raw_assigned": [em],
                    "all_available": [w],
                    "is_work_study": True
                })
                assigned_hours[em] += duration
                remaining -= duration
            else:
                logger.warning(f"Skipping work study shift for {w['first_name']} {w['last_name']} on {day} {slot_start}-{slot_end} due to max_workers_per_shift limit.")
                # Optionally, add to ws_issues or similar

        if remaining > 0:
            # mark issue--will show up in your ws_issues list
            logger.warning(
                f"Work-study {w['first_name']} {w['last_name']} "
                f"only got {5-remaining:.1f}h out of 5h"
            )

    #
    # 2) Fill remaining hours-of-operation windows with regular workers
    #    Sort workers by ratio of (assigned_hours / availability_hours)
    #    to ensure even distribution relative to availability
    #
    days = list(hours_of_operation.keys())
    
    # Keep days in order to make schedule more predictable
    # This helps with consistency across schedule generations
    days.sort(key=DAYS.index)
    
    for day in days:
        ops = hours_of_operation.get(day, [])
        if not ops:
            continue
        schedule.setdefault(day, [])

        for op in ops:
            op_start = time_to_hour(op['start'])
            op_end = time_to_hour(op['end'])
            if op_end <= op_start:
                op_end += 24

            # subtract out already-scheduled blocks to get free slots
            free_slots = [(op_start, op_end)]
            for blk in schedule.get(day, []):
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

            # Sort free slots by duration (shortest first)
            # This helps create more balanced shift lengths
            free_slots.sort(key=lambda slot: slot[1] - slot[0])

            # within each free slot, carve shifts of appropriate length
            for (s0, e0) in free_slots:
                if (e0 - s0) < 2:
                    continue
                
                # Prefer common shift lengths but have some variety
                lengths = [l for l in shift_lengths if l <= (e0 - s0)] or [2]
                
                cur = s0
                while cur < e0:
                    random.shuffle(lengths)
                    length = next((l for l in lengths if cur + l <= e0), lengths[0])
                    end_shift = min(cur + length, e0)
                    shift_duration = end_shift - cur

                    # pick available workers
                    avail = []
                    for x in workers:
                        x_em = x['email']
                        
                        # Skip work study students who have their hours or haven't been scheduled yet
                        if ws_status.get(x_em, False):
                            if assigned_hours[x_em] >= 5:
                                continue
                            # ensure WS only gets their 5h in phase 1
                            if assigned_hours[x_em] == 0:
                                continue
                            
                        # Skip workers who just had a shift (avoid back-to-back shifts)
                        if recently_scheduled(x_em, day, cur, schedule):
                            continue
                            
                        # Regular worker availability check
                        if is_worker_available(x, day, cur, end_shift) and \
                           assigned_hours[x_em] + shift_duration <= max_hours_per_worker:
                            avail.append(x)

                    # Calculate fairness ratio: assigned_hours / availability_hours
                    # This ensures workers with less availability get fair consideration
                    def fairness_score(worker):
                        w_email = worker['email']
                        avail_hours = max(availability_hours.get(w_email, 1), 1)  # Avoid div by zero
                        assigned = assigned_hours.get(w_email, 0)
                        ratio = assigned / avail_hours
                        # Add small random factor to break ties
                        return (ratio, random.random())
                    
                    # Sort by fairness ratio (lowest first)
                    avail.sort(key=fairness_score)
                    chosen = avail[:max_workers_per_shift]

                    # assign those chosen
                    for x in chosen:
                        assigned_hours[x['email']] += shift_duration

                    # record individual shifts--one entry per worker
                    for x in chosen:
                        schedule.setdefault(day, []).append({
                            "start": hour_to_time_str(cur),
                            "end": hour_to_time_str(end_shift),
                            "assigned": [f"{x['first_name']} {x['last_name']}"],
                            "available": [f"{y['first_name']} {y['last_name']}" for y in avail],
                            "raw_assigned": [x['email']],
                            "all_available": avail
                        })

                    # if we didn't fill up to max_workers, mark unfilled slots
                    for _ in range(max_workers_per_shift - len(chosen)):
                        unfilled_shifts.append({
                            "day": day,
                            "start": hour_to_time_str(cur),
                            "end": hour_to_time_str(end_shift),
                            "start_hour": cur,
                            "end_hour": end_shift
                        })
                        schedule.setdefault(day, []).append({
                            "start": hour_to_time_str(cur),
                            "end": hour_to_time_str(end_shift),
                            "assigned": ["Unfilled"],
                            "available": [f"{y['first_name']} {y['last_name']}" for y in avail],
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
    
    # Include both initial issues and final check
    ws_issues = initial_ws_issues + [
        f"{w['first_name']} {w['last_name']} ({assigned_hours[w['email']]}h)"
        for w in workers
        if ws_status[w['email']] and assigned_hours[w['email']] != 5 
        and f"{w['first_name']} {w['last_name']}" not in [issue.split(':')[0] for issue in initial_ws_issues]
    ]

    # New: collect workers below min_hours_per_worker (non-work-study only)
    min_hours_issues = [
        f"{w['first_name']} {w['last_name']}"
        for w in workers
        if not ws_status[w['email']] and assigned_hours[w['email']] < min_hours_per_worker
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

    return schedule, assigned_hours, low_hours, unassigned, alt_sols, unfilled_shifts, ws_issues, min_hours_issues
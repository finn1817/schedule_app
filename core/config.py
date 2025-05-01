# schedule_app/core/config.py

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = {
    'workplaces': os.path.join(BASE_DIR, 'workplaces'),
    'schedules': os.path.join(BASE_DIR, 'schedules'),
    'saved_schedules': os.path.join(BASE_DIR, 'saved_schedules'),
    'templates': os.path.join(BASE_DIR, 'templates'),
    'static': os.path.join(BASE_DIR, 'static'),
    'logs': os.path.join(BASE_DIR, 'logs'),
}

# ensure directories exist
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# days-of-week constant used throughout UI and scheduler
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
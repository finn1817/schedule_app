#!/usr/bin/env python3
# schedule_app/Install.py

import os
import sys
import subprocess
import json
from pathlib import Path

def print_header(text):
    print("\n" + "=" * 60)
    print(f" {text} ".center(60, "="))
    print("=" * 60)

def print_step(text):
    print(f"\n>> {text}")

def create_directory(path: Path):
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {path}")
    else:
        print(f"Directory already exists: {path}")

def find_desktop_path() -> Path:
    home = Path.home()
    onedrive = home / "OneDrive" / "Desktop"
    standard = home / "Desktop"
    if onedrive.exists():
        return onedrive
    if standard.exists():
        return standard
    standard.mkdir(parents=True, exist_ok=True)
    return standard

def main():
    root = Path(__file__).resolve().parent
    print_header("WORKPLACE SCHEDULER INSTALLER")

    # 1. Python version
    print_step("Checking Python version...")
    if sys.version_info < (3, 7):
        print("Error: Python 3.7+ required.")
        sys.exit(1)
    print(f"Using Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # 2. Install pip packages
    print_step("Installing Python dependencies...")
    for pkg in ("pandas", "openpyxl", "matplotlib", "PyQt5", "email-validator", "Pillow", "firebase-admin"):
        print(f" - {pkg}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

    # 3. Create directories
    print_step("Creating application directories...")
    dirs = [
        root / "workplaces",
        root / "saved_schedules",
        root / "data",
        root / "data" / "templates",
        root / "static",
        root / "logs",
    ]
    for d in dirs:
        create_directory(d)

    # 4. Initialize data/data.json
    print_step("Creating initial data file...")
    data_file = root / "data" / "data.json"
    if not data_file.exists():
        initial_data = {
            "esports_lounge":  {"hours_of_operation": {}},
            "esports_arena":   {"hours_of_operation": {}},
            "it_service_center": {"hours_of_operation": {}},
        }
        with data_file.open("w") as f:
            json.dump(initial_data, f, indent=4)
        print(f"Created: {data_file}")
    else:
        print(f"Data file exists: {data_file}")

    # 5. Check for Firebase credentials
    print_step("Checking Firebase credentials...")
    firebase_creds = root / "workplace-scheduler-ace38-firebase-adminsdk-fbsvc-4d7d358b05.json"
    if not firebase_creds.exists():
        print(f"Warning: Firebase credentials file not found at {firebase_creds}")
        print("Firebase functionality will be limited until credentials are added.")
        
        # Create placeholder for explanation
        firebase_readme = root / "FIREBASE_SETUP.txt"
        with firebase_readme.open("w") as f:
            f.write("""
FIREBASE SETUP INSTRUCTIONS
==========================

To enable Firebase functionality in the Workplace Scheduler app:

1. Create a Firebase project at https://console.firebase.google.com/
2. Go to Project Settings > Service Accounts
3. Click "Generate new private key" button
4. Download the JSON file
5. Rename it to: workplace-scheduler-ace38-firebase-adminsdk-fbsvc-4d7d358b05.json
6. Place it in the application root directory (same location as this file)
7. Restart the application

Once these steps are completed, Firebase functionality will be enabled.
""")
        print(f"Created Firebase setup instructions at {firebase_readme}")
    else:
        print(f"Firebase credentials file found at {firebase_creds}")

    # 6. Desktop shortcut
    print_step("Creating desktop shortcut...")
    desktop = find_desktop_path()
    shortcut = desktop / "Workplace Scheduler.bat"
    try:
        with shortcut.open("w") as f:
            f.write(
                f'@echo off\n'
                f'cd /d "{root}"\n'
                f'"{sys.executable}" "{root / "main.py"}"\n'
                "pause\n"
            )
        print(f"Shortcut created at {shortcut}")
    except Exception as e:
        print(f"Warning: could not create shortcut: {e}")
        print(f"Run the app manually with:\n  python \"{root / 'main.py'}\"")

    print_header("INSTALLATION COMPLETE")
    input("Press Enter to finish…")

if __name__ == "__main__":
    main()
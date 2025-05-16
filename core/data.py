# schedule_app/core/data.py

import os
import json
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional

from .config import DIRS, firebase_available, DAYS
from .parser import time_to_hour
from .firebase_manager import FirebaseManager

logger = logging.getLogger(__name__)

# Global variables
DATA_FILE = os.path.join(DIRS['data'], 'data.json')
data_manager = None

def load_data() -> Dict[str, Any]:
    """Load data from JSON file"""
    if not os.path.exists(DATA_FILE):
        return {}
    
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return {}

def save_data(data: Dict[str, Any]) -> bool:
    """Save data to JSON file"""
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving data: {e}")
        return False

def get_data_manager():
    """Get or create data manager instance"""
    global data_manager
    if data_manager is None:
        data_manager = DataManager()
    return data_manager

class DataManager:
    """Class for managing app data with Firebase integration"""
    
    def __init__(self):
        """Initialize data manager"""
        self.firebase_enabled = firebase_available()
        self.firebase = FirebaseManager.get_instance() if self.firebase_enabled else None
        self.current_workplace_id = None
    
    def load_workplace(self, workplace_id: str) -> bool:
        """
        Load a workplace and set it as current
        
        Args:
            workplace_id: Workplace ID
            
        Returns:
            True if successful, False otherwise
        """
        # Set current workplace ID
        self.current_workplace_id = workplace_id
        
        # Set in Firebase manager if enabled
        if self.firebase_enabled and self.firebase:
            return self.firebase.set_workplace(workplace_id)
        
        return True
    
    def get_workers(self) -> List[Dict[str, Any]]:
        """
        Get all workers for the current workplace
        
        Returns:
            List of worker data
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return []
        
        # Get from Firebase if enabled
        if self.firebase_enabled and self.firebase:
            return self.firebase.get_workers(self.current_workplace_id)
        
        # Fall back to local file
        return self._get_workers_from_excel()
    
    def _get_workers_from_excel(self) -> List[Dict[str, Any]]:
        """Get workers from Excel file"""
        if not self.current_workplace_id:
            return []
        
        path = os.path.join(DIRS['workplaces'], f"{self.current_workplace_id}.xlsx")
        if not os.path.exists(path):
            return []
        
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip()
            df = df.dropna(subset=['Email'], how='all')
            df = df[df['Email'].str.strip() != '']
            df = df[~df['Email'].str.contains('nan', case=False, na=False)]
            
            workers = []
            
            # Get availability column
            avail_col = next((c for c in df.columns if 'available' in c.lower()), None)
            
            for _, row in df.iterrows():
                # Parse availability
                avail_text = str(row.get(avail_col, "")) if avail_col else ""
                if pd.isna(avail_text) or avail_text == "nan":
                    avail_text = ""
                
                from core.parser import parse_availability
                parsed_avail = parse_availability(avail_text)
                
                workers.append({
                    "first_name": row.get("First Name", "").strip(),
                    "last_name": row.get("Last Name", "").strip(),
                    "email": row.get("Email", "").strip(),
                    "work_study": str(row.get("Work Study", "")).strip().lower() in ['yes', 'y', 'true'],
                    "availability": parsed_avail,
                    "availability_text": avail_text
                })
            
            return workers
            
        except Exception as e:
            logger.error(f"Error loading workers from Excel: {e}")
            return []
    
    def add_worker(self, worker_data: Dict[str, Any]) -> bool:
        """
        Add a worker to the current workplace
        
        Args:
            worker_data: Worker data
            
        Returns:
            True if successful, False otherwise
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return False
        
        # Add to Firebase if enabled
        if self.firebase_enabled and self.firebase:
            worker_id = self.firebase.add_worker(self.current_workplace_id, worker_data)
            return worker_id is not None
        
        # Fall back to local file
        return self._add_worker_to_excel(worker_data)
    
    def _add_worker_to_excel(self, worker_data: Dict[str, Any]) -> bool:
        """Add worker to Excel file"""
        if not self.current_workplace_id:
            return False
        
        path = os.path.join(DIRS['workplaces'], f"{self.current_workplace_id}.xlsx")
        
        try:
            # Check if file exists
            if os.path.exists(path):
                df = pd.read_excel(path)
                df.columns = df.columns.str.strip()
            else:
                # Create new dataframe
                df = pd.DataFrame(columns=[
                    "First Name", "Last Name", "Email", "Work Study", "Days & Times Available"
                ])
            
            # Check for duplicate email
            if "Email" in df.columns and worker_data["email"] in df["Email"].values:
                logger.warning(f"Worker with email {worker_data['email']} already exists")
                return False
            
            # Add worker
            new_row = {
                "First Name": worker_data["first_name"],
                "Last Name": worker_data["last_name"],
                "Email": worker_data["email"],
                "Work Study": "Yes" if worker_data["work_study"] else "No",
                "Days & Times Available": worker_data.get("availability_text", "")
            }
            
            # Append row
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
            # Save Excel file
            df.to_excel(path, index=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding worker to Excel: {e}")
            return False
    
    def update_worker(self, worker_id: str, worker_data: Dict[str, Any]) -> bool:
        """
        Update a worker in the current workplace
        
        Args:
            worker_id: Worker ID
            worker_data: Worker data
            
        Returns:
            True if successful, False otherwise
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return False
        
        # Update in Firebase if enabled
        if self.firebase_enabled and self.firebase:
            return self.firebase.update_worker(self.current_workplace_id, worker_id, worker_data)
        
        # Fall back to local file - no worker_id for Excel, use email
        return self._update_worker_in_excel(worker_data)
    
    def _update_worker_in_excel(self, worker_data: Dict[str, Any]) -> bool:
        """Update worker in Excel file"""
        if not self.current_workplace_id or "email" not in worker_data:
            return False
        
        path = os.path.join(DIRS['workplaces'], f"{self.current_workplace_id}.xlsx")
        if not os.path.exists(path):
            return False
        
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip()
            
            # Find worker by email
            mask = df["Email"] == worker_data["email"]
            if not mask.any():
                logger.warning(f"Worker with email {worker_data['email']} not found")
                return False
            
            # Update worker
            df.loc[mask, "First Name"] = worker_data["first_name"]
            df.loc[mask, "Last Name"] = worker_data["last_name"]
            df.loc[mask, "Work Study"] = "Yes" if worker_data["work_study"] else "No"
            
            # Update availability
            avail_col = next((c for c in df.columns if 'available' in c.lower()), None)
            if avail_col:
                df.loc[mask, avail_col] = worker_data.get("availability_text", "")
            
            # Save Excel file
            df.to_excel(path, index=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating worker in Excel: {e}")
            return False
    
    def delete_worker(self, worker_id_or_email: str) -> bool:
        """
        Delete a worker from the current workplace
        
        Args:
            worker_id_or_email: Worker ID or email
            
        Returns:
            True if successful, False otherwise
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return False
        
        # Try to determine if it's an ID or email
        is_email = '@' in worker_id_or_email
        
        # Delete from Firebase if enabled
        if self.firebase_enabled and self.firebase:
            if is_email:
                return self.firebase.delete_worker_by_email(self.current_workplace_id, worker_id_or_email)
            else:
                return self.firebase.delete_worker(self.current_workplace_id, worker_id_or_email)
        
        # Fall back to local file - email only for Excel
        if is_email:
            return self._delete_worker_from_excel(worker_id_or_email)
        
        logger.error("Cannot delete worker by ID from Excel, email required")
        return False
    
    def _delete_worker_from_excel(self, email: str) -> bool:
        """Delete worker from Excel file"""
        if not self.current_workplace_id:
            return False
        
        path = os.path.join(DIRS['workplaces'], f"{self.current_workplace_id}.xlsx")
        if not os.path.exists(path):
            return False
        
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip()
            
            # Find worker by email
            mask = df["Email"] == email
            if not mask.any():
                logger.warning(f"Worker with email {email} not found")
                return False
            
            # Remove worker
            df = df[~mask]
            
            # Save Excel file
            df.to_excel(path, index=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting worker from Excel: {e}")
            return False
    
    def remove_all_workers(self) -> bool:
        """
        Remove all workers from the current workplace
        
        Returns:
            True if successful, False otherwise
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return False
        
        # Remove from Firebase if enabled
        firebase_success = False
        if self.firebase_enabled and self.firebase:
            count = self.firebase.remove_all_workers(self.current_workplace_id)
            firebase_success = count > 0
        
        # Always remove from local file
        excel_success = self._remove_all_workers_from_excel()
        
        return firebase_success or excel_success
    
    def _remove_all_workers_from_excel(self) -> bool:
        """Remove all workers from Excel file"""
        if not self.current_workplace_id:
            return False
        
        path = os.path.join(DIRS['workplaces'], f"{self.current_workplace_id}.xlsx")
        if not os.path.exists(path):
            return True  # No file to remove workers from
        
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip()
            
            # Create empty dataframe with same columns
            empty_df = pd.DataFrame(columns=df.columns)
            
            # Save Excel file
            empty_df.to_excel(path, index=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing all workers from Excel: {e}")
            return False
    
    def get_hours_of_operation(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Get hours of operation for the current workplace
        
        Returns:
            Hours of operation data
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return {}
        
        # Get from Firebase if enabled
        if self.firebase_enabled and self.firebase:
            hours = self.firebase.get_hours_of_operation(self.current_workplace_id)
            if hours:
                return hours
        
        # Fall back to local data
        data = load_data()
        return data.get(self.current_workplace_id, {}).get('hours_of_operation', {})
    
    def update_hours_of_operation(self, hours_data: Dict[str, List[Dict[str, str]]]) -> bool:
        """
        Update hours of operation for the current workplace
        
        Args:
            hours_data: Hours of operation data
            
        Returns:
            True if successful, False otherwise
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return False
        
        # Update in Firebase if enabled
        firebase_success = False
        if self.firebase_enabled and self.firebase:
            firebase_success = self.firebase.update_hours_of_operation(self.current_workplace_id, hours_data)
        
        # Always update local data
        data = load_data()
        data.setdefault(self.current_workplace_id, {})['hours_of_operation'] = hours_data
        local_success = save_data(data)
        
        return firebase_success or local_success
    
    def save_schedule(self, schedule_data: Dict[str, Any]) -> Optional[str]:
        """
        Save a schedule for the current workplace
        
        Args:
            schedule_data: Schedule data
            
        Returns:
            Schedule ID if successful, None otherwise
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return None
        
        # Save to Firebase if enabled
        if self.firebase_enabled and self.firebase:
            return self.firebase.save_schedule(self.current_workplace_id, schedule_data)
        
        # Fall back to local file
        return self._save_schedule_to_file(schedule_data)
    
    def _save_schedule_to_file(self, schedule_data: Dict[str, Any]) -> Optional[str]:
        """Save schedule to local file"""
        if not self.current_workplace_id:
            return None
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(DIRS['saved_schedules'], exist_ok=True)
            
            # Save JSON file
            json_path = os.path.join(DIRS['saved_schedules'], f"{self.current_workplace_id}_current.json")
            
            # Get the actual schedule data
            days_data = schedule_data.get('days', schedule_data)
            
            with open(json_path, 'w') as f:
                json.dump(days_data, f, indent=4)
            
            # Save Excel file
            self._save_schedule_to_excel(days_data)
            
            return "current"
            
        except Exception as e:
            logger.error(f"Error saving schedule to file: {e}")
            return None
    
    def _save_schedule_to_excel(self, schedule_data: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Save schedule to Excel file"""
        if not self.current_workplace_id:
            return False
        
        try:
            excel_path = os.path.join(DIRS['saved_schedules'], f"{self.current_workplace_id}_current.xlsx")
            
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                # Create a sheet for each day
                for day in DAYS:
                    shifts = schedule_data.get(day, [])
                    if not shifts:
                        continue
                    
                    rows = []
                    for shift in shifts:
                        from core.parser import format_time_ampm
                        rows.append({
                            "Start": format_time_ampm(shift['start']),
                            "End": format_time_ampm(shift['end']),
                            "Assigned": ", ".join(shift['assigned'])
                        })
                    
                    if rows:
                        pd.DataFrame(rows).to_excel(writer, sheet_name=day, index=False)
                
                # Create a full schedule sheet with ordered days and sorted times
                all_rows = []
                
                # Define the correct day order (Sunday first)
                correct_day_order = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
                
                # Process days in the correct order
                for day in correct_day_order:
                    shifts = schedule_data.get(day, [])
                    if not shifts:
                        continue
                    
                    day_rows = []
                    
                    # Process shifts for this day
                    for shift in shifts:
                        from core.parser import format_time_ampm, time_to_hour
                        start_hour = time_to_hour(shift['start'])
                        
                        # For each assigned worker, create a separate row
                        if len(shift['assigned']) > 1 or (len(shift['assigned']) == 1 and shift['assigned'][0] != "Unfilled"):
                            for worker in shift['assigned']:
                                day_rows.append({
                                    "Day": day,
                                    "Start": format_time_ampm(shift['start']),
                                    "End": format_time_ampm(shift['end']),
                                    "Assigned": worker,
                                    "_start_hour": start_hour  # For sorting, will be removed later
                                })
                        else:
                            # Keep "Unfilled" slots as they are
                            day_rows.append({
                                "Day": day,
                                "Start": format_time_ampm(shift['start']),
                                "End": format_time_ampm(shift['end']),
                                "Assigned": ", ".join(shift['assigned']),
                                "_start_hour": start_hour  # For sorting, will be removed later
                            })
                    
                    # Sort shifts for this day by start time
                    day_rows.sort(key=lambda x: x["_start_hour"])
                    
                    # Remove the temporary sorting field
                    for row in day_rows:
                        del row["_start_hour"]
                        
                    # Add this day's rows to the full list
                    all_rows.extend(day_rows)
                
                if all_rows:
                    pd.DataFrame(all_rows).to_excel(writer, sheet_name="Full Schedule", index=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving schedule to Excel: {e}")
            return False
    
    def get_schedules(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get schedules for the current workplace
        
        Args:
            limit: Maximum number of schedules to return
            
        Returns:
            List of schedule data
        """
        if not self.current_workplace_id:
            logger.error("No current workplace set")
            return []
        
        # Get from Firebase if enabled
        if self.firebase_enabled and self.firebase:
            schedules = self.firebase.get_schedules(self.current_workplace_id, limit)
            if schedules:
                return schedules
        
        # Fall back to local file
        return self._get_schedules_from_file()
    
    def _get_schedules_from_file(self) -> List[Dict[str, Any]]:
        """Get schedules from local file"""
        if not self.current_workplace_id:
            return []
        
        try:
            json_path = os.path.join(DIRS['saved_schedules'], f"{self.current_workplace_id}_current.json")
            
            if not os.path.exists(json_path):
                return []
            
            with open(json_path, 'r') as f:
                schedule_data = json.load(f)
            
            # Format as a list with a single schedule
            return [{
                'id': 'current',
                'name': f"{self.current_workplace_id} Current Schedule",
                'days': schedule_data,
                'created_at': datetime.fromtimestamp(os.path.getmtime(json_path)).isoformat(),
                'workplace_id': self.current_workplace_id
            }]
            
        except Exception as e:
            logger.error(f"Error loading schedules from file: {e}")
            return []

# Helper functions for use in other modules

def get_workers(workplace_id: str) -> List[Dict[str, Any]]:
    """
    Get workers for a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        
    Returns:
        List of worker data
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    return dm.get_workers()

def save_worker(workplace_id: str, worker_data: Dict[str, Any]) -> bool:
    """
    Save a worker to a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        worker_data: Worker data
        
    Returns:
        True if successful, False otherwise
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    
    # Check if worker has an ID (update) or not (add)
    if 'id' in worker_data:
        worker_id = worker_data.pop('id')  # Remove ID from data
        return dm.update_worker(worker_id, worker_data)
    else:
        return dm.add_worker(worker_data)

def delete_worker(workplace_id: str, worker_id_or_email: str) -> bool:
    """
    Delete a worker from a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        worker_id_or_email: Worker ID or email
        
    Returns:
        True if successful, False otherwise
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    return dm.delete_worker(worker_id_or_email)

def export_all_workers_to_firebase(workplace_id: str) -> bool:
    """
    Export all workers from Excel to Firebase
    
    Args:
        workplace_id: Workplace ID
        
    Returns:
        True if successful, False otherwise
    """
    if not firebase_available():
        logger.error("Firebase not available")
        return False
    
    try:
        # Get data manager
        dm = get_data_manager()
        dm.load_workplace(workplace_id)
        
        # Get Firebase manager
        firebase = FirebaseManager.get_instance()
        
        # Get workers from Excel
        workers = dm._get_workers_from_excel()
        
        if not workers:
            logger.warning(f"No workers found in Excel for {workplace_id}")
            return False
        
        # Add each worker to Firebase
        success_count = 0
        for worker in workers:
            worker_id = firebase.add_worker(workplace_id, worker)
            if worker_id:
                success_count += 1
        
        logger.info(f"Exported {success_count} of {len(workers)} workers to Firebase for {workplace_id}")
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Error exporting workers to Firebase: {e}")
        return False

def save_workers_from_ui(workplace_id: str, workers: List[Dict[str, Any]]) -> bool:
    """
    Save workers from UI to Firebase
    
    Args:
        workplace_id: Workplace ID
        workers: List of worker data
        
    Returns:
        True if successful, False otherwise
    """
    if not firebase_available():
        logger.error("Firebase not available")
        return False
    
    try:
        # Get Firebase manager
        firebase = FirebaseManager.get_instance()
        
        # Set workplace
        firebase.set_workplace(workplace_id)
        
        # Remove all existing workers
        firebase.remove_all_workers(workplace_id)
        
        # Add each worker to Firebase
        success_count = 0
        for worker in workers:
            worker_id = firebase.add_worker(workplace_id, worker)
            if worker_id:
                success_count += 1
        
        logger.info(f"Saved {success_count} of {len(workers)} workers to Firebase for {workplace_id}")
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Error saving workers from UI to Firebase: {e}")
        return False

def get_hours_of_operation(workplace_id: str) -> Dict[str, List[Dict[str, str]]]:
    """
    Get hours of operation for a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        
    Returns:
        Hours of operation data
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    return dm.get_hours_of_operation()

def save_schedule(workplace_id: str, schedule_data: Dict[str, Any]) -> Optional[str]:
    """
    Save a schedule for a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        schedule_data: Schedule data
        
    Returns:
        Schedule ID if successful, None otherwise
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    return dm.save_schedule(schedule_data)

def get_schedules(workplace_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get schedules for a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        limit: Maximum number of schedules to return
        
    Returns:
        List of schedule data
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    return dm.get_schedules(limit)

def update_hours_of_operation(workplace_id: str, hours_data: Dict[str, List[Dict[str, str]]]) -> bool:
    """
    Update hours of operation for a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        hours_data: Hours of operation data
        
    Returns:
        True if successful, False otherwise
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    return dm.update_hours_of_operation(hours_data)

def remove_all_workers(workplace_id: str) -> bool:
    """
    Remove all workers from a workplace (Firebase-aware)
    
    Args:
        workplace_id: Workplace ID
        
    Returns:
        True if successful, False otherwise
    """
    dm = get_data_manager()
    dm.load_workplace(workplace_id)
    return dm.remove_all_workers()
# schedule_app/scripts/test_firebase.py

import logging
import time
import sys
import os
import firebase_admin
from firebase_admin import credentials, firestore
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import firebase_available, initialize_firebase
from core.firebase_manager import FirebaseManager
from core.firebase_utils import FirebaseUtils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/firebase_test.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def test_firebase_connection():
    """Test Firebase connection"""
    logger.info("Testing Firebase connection...")
    
    # Initialize Firebase
    if firebase_available():
        logger.info("Firebase is already available")
    else:
        logger.info("Firebase not available, initializing...")
        if initialize_firebase():
            logger.info("Firebase initialized successfully")
        else:
            logger.error("Failed to initialize Firebase")
            return False
    
    # Get Firebase manager
    firebase = FirebaseManager.get_instance()
    
    if firebase.db:
        logger.info("Firebase manager initialized successfully")
        return True
    else:
        logger.error("Firebase manager not initialized properly")
        return False

def test_workplace_operations():
    """Test workplace operations"""
    logger.info("Testing workplace operations...")
    
    # Get Firebase manager
    firebase = FirebaseManager.get_instance()
    
    # Test workplace setting
    workplace_id = "esports_lounge"
    
    if firebase.set_workplace(workplace_id):
        logger.info(f"Successfully set workplace: {workplace_id}")
    else:
        logger.error(f"Failed to set workplace: {workplace_id}")
        return False
    
    return True

def test_worker_operations():
    """Test worker operations"""
    logger.info("Testing worker operations...")
    
    # Get Firebase manager
    firebase = FirebaseManager.get_instance()
    
    # Generate a unique email to avoid duplicates
    test_email = f"test.worker.{int(time.time())}@example.com"
    
    # Create test worker
    test_worker = {
        "first_name": "Test",
        "last_name": "Worker",
        "email": test_email,
        "work_study": True,
        "availability_text": "Monday 09:00-17:00, Friday 12:00-18:00"
    }
    
    # Get workers before adding
    workers_before = firebase.get_workers()
    logger.info(f"Found {len(workers_before)} workers before adding")
    
    # Add worker
    worker_id = firebase.add_worker(None, test_worker)
    
    if worker_id:
        logger.info(f"Successfully added worker with ID: {worker_id}")
    else:
        logger.error("Failed to add worker")
        return False
    
    # Get workers after adding
    time.sleep(1)  # Small delay to ensure Firestore consistency
    workers_after = firebase.get_workers()
    logger.info(f"Found {len(workers_after)} workers after adding")
    
    # Verify worker was added
    if len(workers_after) != len(workers_before) + 1:
        logger.warning("Worker count mismatch after adding")
    
    # Find the added worker
    added_worker = next((w for w in workers_after if w.get("email") == test_email), None)
    
    if added_worker:
        logger.info(f"Found added worker: {added_worker.get('first_name')} {added_worker.get('last_name')}")
    else:
        logger.error(f"Could not find added worker with email: {test_email}")
        return False
    
    # Clean up - delete the test worker
    worker_id_to_delete = added_worker.get("id")
    
    if worker_id_to_delete:
        if firebase.delete_worker(None, worker_id_to_delete):
            logger.info(f"Successfully deleted worker with ID: {worker_id_to_delete}")
        else:
            logger.error(f"Failed to delete worker with ID: {worker_id_to_delete}")
            return False
    else:
        # Try deleting by email
        if firebase.delete_worker_by_email(None, test_email):
            logger.info(f"Successfully deleted worker with email: {test_email}")
        else:
            logger.error(f"Failed to delete worker with email: {test_email}")
            return False
    
    # Get workers after deletion
    time.sleep(1)  # Small delay to ensure Firestore consistency
    workers_after_delete = firebase.get_workers()
    logger.info(f"Found {len(workers_after_delete)} workers after deletion")
    
    # Verify worker was deleted
    if len(workers_after_delete) != len(workers_before):
        logger.warning("Worker count mismatch after deletion")
    
    return True

def test_hours_operations():
    """Test hours of operation"""
    logger.info("Testing hours of operation...")
    
    # Get Firebase manager
    firebase = FirebaseManager.get_instance()
    
    # Get current hours of operation
    current_hours = firebase.get_hours_of_operation()
    logger.info(f"Current hours of operation: {json.dumps(current_hours)}")
    
    # Create test hours
    test_hours = {
        "Monday": [{"start": "09:00", "end": "17:00"}],
        "Tuesday": [{"start": "09:00", "end": "17:00"}],
        "Wednesday": [{"start": "09:00", "end": "17:00"}],
        "Thursday": [{"start": "09:00", "end": "17:00"}],
        "Friday": [{"start": "09:00", "end": "17:00"}],
        "Saturday": [{"start": "10:00", "end": "15:00"}],
        "Sunday": []
    }
    
    # Update hours of operation
    if firebase.update_hours_of_operation(None, test_hours):
        logger.info("Successfully updated hours of operation")
    else:
        logger.error("Failed to update hours of operation")
        return False
    
    # Get updated hours of operation
    time.sleep(1)  # Small delay to ensure Firestore consistency
    updated_hours = firebase.get_hours_of_operation()
    logger.info(f"Updated hours of operation: {json.dumps(updated_hours)}")
    
    # Restore original hours if there were any
    if current_hours:
        if firebase.update_hours_of_operation(None, current_hours):
            logger.info("Successfully restored original hours of operation")
        else:
            logger.error("Failed to restore original hours of operation")
            return False
    
    return True

def test_schedule_operations():
    """Test schedule operations"""
    logger.info("Testing schedule operations...")
    
    # Get Firebase manager
    firebase = FirebaseManager.get_instance()
    
    # Create test schedule
    test_schedule = {
        "days": {
            "Monday": [
                {
                    "start": "09:00",
                    "end": "12:00",
                    "assigned": ["Test Worker"],
                    "raw_assigned": ["test.worker@example.com"]
                }
            ],
            "Tuesday": [
                {
                    "start": "13:00",
                    "end": "17:00",
                    "assigned": ["Test Worker"],
                    "raw_assigned": ["test.worker@example.com"]
                }
            ]
        },
        "name": "Test Schedule"
    }
    
    # Save schedule
    schedule_id = firebase.save_schedule(None, test_schedule)
    
    if schedule_id:
        logger.info(f"Successfully saved schedule with ID: {schedule_id}")
    else:
        logger.error("Failed to save schedule")
        return False
    
    # Get schedules
    time.sleep(1)  # Small delay to ensure Firestore consistency
    schedules = firebase.get_schedules()
    logger.info(f"Found {len(schedules)} schedules")
    
    # Find the saved schedule
    saved_schedule = next((s for s in schedules if s.get("name") == "Test Schedule"), None)
    
    if saved_schedule:
        logger.info(f"Found saved schedule: {saved_schedule.get('name')}")
    else:
        logger.error("Could not find saved schedule")
        return False
    
    return True

def run_tests():
    """Run all Firebase tests"""
    logger.info("Starting Firebase tests...")
    
    tests = [
        ("Firebase Connection", test_firebase_connection),
        ("Workplace Operations", test_workplace_operations),
        ("Worker Operations", test_worker_operations),
        ("Hours Operations", test_hours_operations),
        ("Schedule Operations", test_schedule_operations)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n=== Running Test: {test_name} ===")
        try:
            success = test_func()
            results.append((test_name, success))
            logger.info(f"=== Test: {test_name} - {'PASSED' if success else 'FAILED'} ===\n")
        except Exception as e:
            logger.exception(f"Error running test {test_name}: {e}")
            results.append((test_name, False))
            logger.info(f"=== Test: {test_name} - FAILED (exception) ===\n")
    
    # Print summary
    logger.info("\n=== Test Results Summary ===")
    passed = 0
    for test_name, success in results:
        status = "PASSED" if success else "FAILED"
        logger.info(f"{test_name}: {status}")
        if success:
            passed += 1
    
    logger.info(f"\nPassed {passed} of {len(results)} tests")
    
    return passed == len(results)

if __name__ == "__main__":
    run_tests()
# schedule_app/scripts/migrate_firebase_structure.py

import logging
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import time
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.firebase_utils import FirebaseUtils
from core.parser import parse_availability

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def initialize_firebase():
    """Initialize Firebase connection"""
    try:
        # Check if already initialized
        if firebase_admin._apps:
            # Get existing app
            app = firebase_admin.get_app()
            db = firestore.client(app=app)
            logger.info("Using existing Firebase app")
            return db
        
        # Look for credentials file
        cred_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'workplace-scheduler-ace38-firebase-adminsdk-fbsvc-4d7d358b05.json'
        )
        
        if not os.path.exists(cred_file):
            logger.error(f"Firebase credentials file not found: {cred_file}")
            return None
        
        # Initialize Firebase
        cred = credentials.Certificate(cred_file)
        app = firebase_admin.initialize_app(cred)
        
        # Get Firestore client
        db = firestore.client(app=app)
        logger.info("Firebase initialized successfully")
        return db
        
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        return None

def migrate_to_nested_structure(db):
    """
    Migrate data from flat structure to nested structure
    """
    try:
        # Define workplaces
        workplaces = ["esports_lounge", "esports_arena", "it_service_center"]
        
        for workplace_id in workplaces:
            logger.info(f"Migrating workplace: {workplace_id}")
            
            # Normalize workplace ID
            workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
            
            # Create or update workplace document
            workplace_ref = db.collection('workplaces').document(workplace_id)
            workplace_doc = workplace_ref.get()
            
            if not workplace_doc.exists:
                workplace_ref.set({
                    'name': workplace_id.replace('_', ' ').title(),
                    'created_at': datetime.now().isoformat()
                })
                logger.info(f"Created workplace document: {workplace_id}")
            
            # Migrate hours of operation
            migrate_hours_of_operation(db, workplace_id, workplace_ref)
            
            # Migrate workers
            migrate_workers(db, workplace_id, workplace_ref)
            
            # Migrate schedules
            migrate_schedules(db, workplace_id, workplace_ref)
            
            logger.info(f"Completed migration for workplace: {workplace_id}")
            
        logger.info("Migration to nested structure completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error migrating to nested structure: {e}")
        return False

def migrate_hours_of_operation(db, workplace_id, workplace_ref):
    """
    Migrate hours of operation from flat to nested structure
    """
    try:
        # Check if hours exists in flat structure
        hours_doc = db.collection(workplace_id).document('hours_of_operation').get()
        
        if hours_doc.exists:
            hours_data = hours_doc.to_dict()
            
            # Save to nested structure
            workplace_ref.set({'hours_of_operation': hours_data}, merge=True)
            
            logger.info(f"Migrated hours of operation for {workplace_id}")
        else:
            logger.info(f"No hours of operation found for {workplace_id}")
            
        return True
        
    except Exception as e:
        logger.error(f"Error migrating hours of operation for {workplace_id}: {e}")
        return False

def migrate_workers(db, workplace_id, workplace_ref):
    """
    Migrate workers from flat to nested structure
    """
    try:
        # Get all workers in flat structure
        workers_query = db.collection(workplace_id).where("Email", "!=", "").stream()
        workers = list(workers_query)
        
        if not workers:
            logger.info(f"No workers found in flat structure for {workplace_id}")
            return True
        
        logger.info(f"Found {len(workers)} workers to migrate for {workplace_id}")
        
        # Create workers subcollection
        workers_ref = workplace_ref.collection('workers')
        
        # Process workers in batches
        batch_size = 450  # Keep under 500 to be safe
        
        for i in range(0, len(workers), batch_size):
            batch = db.batch()
            batch_workers = workers[i:i+batch_size]
            
            for worker_doc in batch_workers:
                worker_data = worker_doc.to_dict()
                
                # Skip if not a worker document
                if "Email" not in worker_data or not worker_data["Email"]:
                    continue
                
                # Map to app format
                app_worker = FirebaseUtils.map_worker_from_firebase(worker_data)
                
                # Ensure availability is parsed
                if "availability" not in app_worker and "availability_text" in app_worker:
                    app_worker["availability"] = parse_availability(app_worker["availability_text"])
                
                # Add to nested structure
                new_worker_ref = workers_ref.document()
                
                # Map back to Firebase format
                firebase_worker = FirebaseUtils.map_worker_to_firebase(app_worker)
                
                # Add to batch
                batch.set(new_worker_ref, firebase_worker)
                
                # Note: We're not deleting from flat structure to be safe
            
            # Commit the batch
            batch.commit()
            
            logger.info(f"Migrated batch of {len(batch_workers)} workers for {workplace_id}")
            
            # Small delay to avoid overloading Firestore
            time.sleep(0.5)
        
        logger.info(f"Successfully migrated {len(workers)} workers for {workplace_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error migrating workers for {workplace_id}: {e}")
        return False

def migrate_schedules(db, workplace_id, workplace_ref):
    """
    Migrate schedules from flat to nested structure
    """
    try:
        # Check if current schedule exists in flat structure
        schedule_doc = db.collection(workplace_id).document('current_schedule').get()
        
        if schedule_doc.exists:
            schedule_data = schedule_doc.to_dict()
            
            # Save to nested structure
            schedules_ref = workplace_ref.collection('schedules')
            schedules_ref.add(schedule_data)
            
            logger.info(f"Migrated current schedule for {workplace_id}")
        else:
            logger.info(f"No current schedule found for {workplace_id}")
            
        return True
        
    except Exception as e:
        logger.error(f"Error migrating schedule for {workplace_id}: {e}")
        return False

def run_migration():
    """
    Run the migration process
    """
    logger.info("Starting Firebase structure migration...")
    
    # Initialize Firebase
    db = initialize_firebase()
    if not db:
        logger.error("Failed to initialize Firebase. Migration aborted.")
        return False
    
    # Migrate to nested structure
    success = migrate_to_nested_structure(db)
    
    if success:
        logger.info("Firebase structure migration completed successfully!")
    else:
        logger.warning("Firebase structure migration completed with errors.")
    
    return success

if __name__ == "__main__":
    run_migration()
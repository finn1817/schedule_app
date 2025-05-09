# schedule_app/scripts/firebase_migration.py

import os
import json
import logging
from datetime import datetime
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from core.parser import parse_availability

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FirebaseMigration")

# Base directory - adjust if needed
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, 'data.json')
CRED_FILE = os.path.join(BASE_DIR, 'workplace-scheduler-ace38-firebase-adminsdk-fbsvc-4d7d358b05.json')
WORKPLACES = ["esports_lounge", "esports_arena", "it_service_center"]
WORKPLACES_DIR = os.path.join(BASE_DIR, 'workplaces')

def load_local_data():
    """Load data from local JSON file"""
    if not os.path.exists(DATA_FILE):
        logger.warning(f"Data file not found: {DATA_FILE}")
        return {}
    
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading local data: {str(e)}")
        return {}

def initialize_firebase():
    """Initialize Firebase connection"""
    if not os.path.exists(CRED_FILE):
        logger.error(f"Firebase credentials file not found: {CRED_FILE}")
        return None
    
    try:
        # Check if already initialized
        if firebase_admin._apps:
            # Get existing app
            app = firebase_admin.get_app()
            db = firestore.client(app=app)
            logger.info("Using existing Firebase app")
            return db
            
        # Initialize Firebase
        cred = credentials.Certificate(CRED_FILE)
        app = firebase_admin.initialize_app(cred)
        
        # Get Firestore client
        db = firestore.client(app=app)
        logger.info("Firebase initialized successfully")
        return db
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {str(e)}")
        return None

def migrate_global_settings(db, data):
    """Migrate global settings to Firestore"""
    try:
        # Get app-wide settings
        app_settings = {
            'last_updated': datetime.now().isoformat(),
            'version': '1.1.0'
        }
        
        # Add any global settings from data.json
        if 'settings' in data:
            app_settings.update(data['settings'])
        
        # Save to Firestore
        db.collection('settings').document('app_data').set(app_settings)
        logger.info("Migrated global settings")
        return True
    except Exception as e:
        logger.error(f"Error migrating global settings: {str(e)}")
        return False

def migrate_workplace_basic_info(db):
    """Create basic workplace documents"""
    try:
        for workplace_id in WORKPLACES:
            # Format the name nicely
            name = workplace_id.replace('_', ' ').title()
            
            # Create workplace document with merge=True to not overwrite existing data
            workplace_ref = db.collection('workplaces').document(workplace_id)
            workplace_ref.set({
                'name': name,
                'created_at': datetime.now().isoformat()
            }, merge=True)
        
        logger.info(f"Created {len(WORKPLACES)} workplace documents")
        return True
    except Exception as e:
        logger.error(f"Error creating workplace documents: {str(e)}")
        return False

def migrate_hours_of_operation(db, data):
    """Migrate hours of operation to Firestore"""
    try:
        for workplace_id in WORKPLACES:
            # Get hours of operation from data.json
            hours = {}
            
            # First try to get from the workplace directly
            if workplace_id in data and 'hours_of_operation' in data[workplace_id]:
                hours = data[workplace_id]['hours_of_operation']
                logger.info(f"Found hours directly in data for {workplace_id}")
            # Then check in workplaces subdictionary
            elif 'workplaces' in data and workplace_id in data['workplaces'] and 'hours_of_operation' in data['workplaces'][workplace_id]:
                hours = data['workplaces'][workplace_id]['hours_of_operation']
                logger.info(f"Found hours in workplaces section for {workplace_id}")
            
            if not hours:
                logger.warning(f"No hours of operation found for {workplace_id}")
                continue
            
            # Save to Firestore
            db.collection('workplaces').document(workplace_id).set({
                'hours_of_operation': hours
            }, merge=True)
            
            logger.info(f"Migrated hours of operation for {workplace_id}")
        
        return True
    except Exception as e:
        logger.error(f"Error migrating hours of operation: {str(e)}")
        return False

def migrate_workers_from_excel(db):
    """Migrate workers from Excel files to Firestore"""
    try:
        total_workers = 0
        
        for workplace_id in WORKPLACES:
            # Check if Excel file exists
            excel_path = os.path.join(WORKPLACES_DIR, f"{workplace_id}.xlsx")
            if not os.path.exists(excel_path):
                logger.warning(f"No Excel file found for {workplace_id}")
                continue
            
            # Read Excel file
            try:
                df = pd.read_excel(excel_path)
                df.columns = df.columns.str.strip()
                df = df.dropna(subset=['Email'], how='all')
                df = df[df['Email'].str.strip() != '']
                df = df[~df['Email'].str.contains('nan', case=False, na=False)]
            except Exception as e:
                logger.error(f"Error reading Excel file for {workplace_id}: {str(e)}")
                continue
            
            # Process workers
            worker_count = 0
            
            # Get availability column name
            avail_col = next((c for c in df.columns if 'available' in c.lower()), None)
            
            # Process each worker
            for _, row in df.iterrows():
                # Check if email exists (required field)
                email = row.get('Email', '').strip()
                if not email or pd.isna(email):
                    logger.warning(f"Skipping worker with no email in {workplace_id}")
                    continue
                
                # Parse availability
                avail_text = str(row.get(avail_col, '')) if avail_col else ''
                if pd.isna(avail_text) or avail_text.lower() == 'nan':
                    avail_text = ''
                
                parsed_avail = parse_availability(avail_text)
                
                # Create worker data
                worker_data = {
                    'first_name': row.get('First Name', '').strip(),
                    'last_name': row.get('Last Name', '').strip(),
                    'email': email,
                    'work_study': str(row.get('Work Study', '')).strip().lower() in ['yes', 'y', 'true'],
                    'availability': parsed_avail,
                    'availability_text': avail_text,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                
                # Check if worker already exists in Firebase
                query = db.collection('workplaces').document(workplace_id) \
                          .collection('workers') \
                          .where('email', '==', email) \
                          .limit(1)
                
                existing_workers = list(query.stream())
                
                if existing_workers:
                    # Update existing worker
                    existing_worker = existing_workers[0]
                    db.collection('workplaces').document(workplace_id) \
                      .collection('workers').document(existing_worker.id) \
                      .update(worker_data)
                    logger.info(f"Updated existing worker {email} in {workplace_id}")
                else:
                    # Create new worker
                    db.collection('workplaces').document(workplace_id) \
                      .collection('workers').add(worker_data)
                    logger.info(f"Added new worker {email} to {workplace_id}")
                
                worker_count += 1
            
            total_workers += worker_count
            logger.info(f"Migrated {worker_count} workers for {workplace_id} from Excel")
        
        logger.info(f"Total workers migrated from Excel: {total_workers}")
        return True
    except Exception as e:
        logger.error(f"Error migrating workers from Excel: {str(e)}")
        return False

def migrate_workers_from_json(db, data):
    """Migrate workers from data.json to Firestore"""
    try:
        total_workers = 0
        
        for workplace_id in WORKPLACES:
            # Get workers from data.json
            workers = []
            
            # First try to get from the workplace directly
            if workplace_id in data and 'workers' in data[workplace_id]:
                workers = data[workplace_id]['workers']
                logger.info(f"Found workers directly in data for {workplace_id}")
            # Then check in workplaces subdictionary
            elif 'workplaces' in data and workplace_id in data['workplaces'] and 'workers' in data['workplaces'][workplace_id]:
                workers = data['workplaces'][workplace_id]['workers']
                logger.info(f"Found workers in workplaces section for {workplace_id}")
            
            if not workers:
                logger.warning(f"No workers found in JSON for {workplace_id}")
                continue
            
            # Process workers
            worker_count = 0
            
            for worker in workers:
                # Skip if no email (required field)
                email = worker.get('email', '')
                if not email:
                    logger.warning(f"Skipping worker with no email in {workplace_id}")
                    continue
                
                # Format availability if needed
                if 'availability' not in worker or not isinstance(worker['availability'], dict):
                    avail_text = worker.get('availability_text', '')
                    if not avail_text and isinstance(worker.get('availability'), str):
                        avail_text = worker['availability']
                    
                    worker['availability'] = parse_availability(avail_text)
                    worker['availability_text'] = avail_text
                
                # Ensure timestamps
                if 'created_at' not in worker:
                    worker['created_at'] = datetime.now().isoformat()
                if 'updated_at' not in worker:
                    worker['updated_at'] = datetime.now().isoformat()
                
                # Normalize field names
                if 'firstName' in worker and 'first_name' not in worker:
                    worker['first_name'] = worker['firstName']
                if 'lastName' in worker and 'last_name' not in worker:
                    worker['last_name'] = worker['lastName']
                if 'workStudy' in worker and 'work_study' not in worker:
                    worker['work_study'] = worker['workStudy']
                
                # Check if worker already exists in Firebase
                query = db.collection('workplaces').document(workplace_id) \
                          .collection('workers') \
                          .where('email', '==', email) \
                          .limit(1)
                
                existing_workers = list(query.stream())
                
                if existing_workers:
                    # Update existing worker
                    existing_worker = existing_workers[0]
                    db.collection('workplaces').document(workplace_id) \
                      .collection('workers').document(existing_worker.id) \
                      .update(worker)
                    logger.info(f"Updated existing worker {email} in {workplace_id}")
                else:
                    # Create new worker
                    db.collection('workplaces').document(workplace_id) \
                      .collection('workers').add(worker)
                    logger.info(f"Added new worker {email} to {workplace_id}")
                
                worker_count += 1
            
            total_workers += worker_count
            logger.info(f"Migrated {worker_count} workers for {workplace_id} from JSON")
        
        logger.info(f"Total workers migrated from JSON: {total_workers}")
        return True
    except Exception as e:
        logger.error(f"Error migrating workers from JSON: {str(e)}")
        return False

def migrate_saved_schedules(db, data):
    """Migrate saved schedules to Firestore"""
    try:
        total_schedules = 0
        
        for workplace_id in WORKPLACES:
            # Get saved schedules from data.json
            schedules = []
            
            # First try to get from the workplace directly
            if workplace_id in data and 'saved_schedules' in data[workplace_id]:
                schedules = data[workplace_id]['saved_schedules']
                logger.info(f"Found schedules directly in data for {workplace_id}")
            # Then check in workplaces subdictionary
            elif 'workplaces' in data and workplace_id in data['workplaces'] and 'saved_schedules' in data['workplaces'][workplace_id]:
                schedules = data['workplaces'][workplace_id]['saved_schedules']
                logger.info(f"Found schedules in workplaces section for {workplace_id}")
            
            if not schedules:
                logger.warning(f"No saved schedules found for {workplace_id}")
                
                # Check for current.json in saved_schedules directory
                schedule_path = os.path.join(BASE_DIR, 'saved_schedules', f"{workplace_id}_current.json")
                if os.path.exists(schedule_path):
                    try:
                        with open(schedule_path, 'r') as f:
                            schedule_data = json.load(f)
                            
                            # Format for Firebase
                            firebase_schedule = {
                                'days': schedule_data,
                                'created_at': datetime.now().isoformat(),
                                'workplace_id': workplace_id,
                                'name': f"{workplace_id} Schedule {datetime.now().strftime('%Y-%m-%d')}"
                            }
                            
                            # Add to Firestore
                            db.collection('workplaces').document(workplace_id) \
                              .collection('schedules').add(firebase_schedule)
                            
                            logger.info(f"Migrated current schedule from file for {workplace_id}")
                            total_schedules += 1
                    except Exception as e:
                        logger.error(f"Error loading schedule from file for {workplace_id}: {str(e)}")
                
                continue
            
            # Process schedules
            schedule_count = 0
            
            for schedule in schedules:
                # Add timestamp if not present
                if 'created_at' not in schedule:
                    schedule['created_at'] = datetime.now().isoformat()
                
                # Add workplace_id if not present
                if 'workplace_id' not in schedule:
                    schedule['workplace_id'] = workplace_id
                
                # Add name if not present
                if 'name' not in schedule:
                    schedule['name'] = f"{workplace_id} Schedule {schedule_count + 1}"
                
                # Create a new schedule document
                db.collection('workplaces').document(workplace_id) \
                  .collection('schedules').add(schedule)
                
                schedule_count += 1
            
            total_schedules += schedule_count
            logger.info(f"Migrated {schedule_count} schedules for {workplace_id}")
        
        logger.info(f"Total schedules migrated: {total_schedules}")
        return True
    except Exception as e:
        logger.error(f"Error migrating schedules: {str(e)}")
        return False

def run_migration():
    """Run the complete migration process"""
    logger.info("Starting Firebase migration...")
    
    # Load local data
    data = load_local_data()
    if not data:
        logger.warning("No local data found in data.json. Will try other sources.")
    
    # Initialize Firebase
    db = initialize_firebase()
    if not db:
        logger.error("Failed to initialize Firebase. Migration aborted.")
        return False
    
    # Run migration steps
    steps = [
        ("Global Settings", lambda: migrate_global_settings(db, data)),
        ("Workplace Basic Info", lambda: migrate_workplace_basic_info(db)),
        ("Hours of Operation", lambda: migrate_hours_of_operation(db, data)),
        ("Workers from JSON", lambda: migrate_workers_from_json(db, data)),
        ("Workers from Excel", lambda: migrate_workers_from_excel(db)),
        ("Saved Schedules", lambda: migrate_saved_schedules(db, data))
    ]
    
    success = True
    for step_name, step_func in steps:
        logger.info(f"Running migration step: {step_name}")
        if step_func():
            logger.info(f"Migration step completed: {step_name}")
        else:
            logger.error(f"Migration step failed: {step_name}")
            success = False
    
    if success:
        logger.info("Firebase migration completed successfully!")
    else:
        logger.warning("Firebase migration completed with some errors.")
    
    return success

if __name__ == "__main__":
    run_migration()
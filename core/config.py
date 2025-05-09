# schedule_app/core/config.py

import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore

# Configure logging
logger = logging.getLogger(__name__)

# Directory structure
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = {
    'workplaces': os.path.join(BASE_DIR, 'workplaces'),
    'saved_schedules': os.path.join(BASE_DIR, 'saved_schedules'),
    'data': os.path.join(BASE_DIR, 'data'),
    'logs': os.path.join(BASE_DIR, 'logs'),
    'static': os.path.join(BASE_DIR, 'static'),
}

# Days of the week
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Firebase variables
db = None
firebase_admin_app = None

def firebase_available():
    """Check if Firebase is available and initialized"""
    global db, firebase_admin_app
    
    # Return existing db if already initialized
    if db is not None:
        return True
    
    # Check for Firebase Admin app
    if firebase_admin._apps:
        firebase_admin_app = firebase_admin.get_app()
        db = firestore.client(app=firebase_admin_app)
        return True
    
    return False

def initialize_firebase():
    """Initialize Firebase connection"""
    global db, firebase_admin_app
    
    try:
        # Return existing db if already initialized
        if db is not None:
            return True
        
        # Check for existing app
        if firebase_admin._apps:
            firebase_admin_app = firebase_admin.get_app()
            db = firestore.client(app=firebase_admin_app)
            logger.info("Using existing Firebase app")
            return True
        
        # Look for credentials file in the project root directory
        cred_file = os.path.join(BASE_DIR, 'workplace-scheduler-ace38-firebase-adminsdk-fbsvc-4d7d358b05.json')
        
        if not os.path.exists(cred_file):
            logger.warning(f"Firebase credentials file not found: {cred_file}")
            return False
        
        # Initialize Firebase
        cred = credentials.Certificate(cred_file)
        firebase_admin_app = firebase_admin.initialize_app(cred)
        
        # Get Firestore database
        db = firestore.client(app=firebase_admin_app)
        
        logger.info("Firebase initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing Firebase: {e}")
        db = None
        firebase_admin_app = None
        return False
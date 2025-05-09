# schedule_app/core/firebase_utils.py

import logging
import time
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Dict, List, Optional, Any, Union
from core.parser import parse_availability

logger = logging.getLogger(__name__)

class FirebaseUtils:
    """Utility functions for Firebase operations"""
    
    @staticmethod
    def map_worker_to_firebase(worker_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert from app worker format to Firebase format
        
        Args:
            worker_data: Worker data in app format
            
        Returns:
            Worker data formatted for Firebase
        """
        if not worker_data:
            return {}
            
        # Make a copy to avoid modifying the original
        firebase_worker = {}
        
        # Handle field mapping
        firebase_worker["First Name"] = worker_data.get("first_name", "")
        firebase_worker["Last Name"] = worker_data.get("last_name", "")
        firebase_worker["Email"] = worker_data.get("email", "")
        
        # Convert boolean to "Yes"/"No" string
        firebase_worker["Work Study"] = "Yes" if worker_data.get("work_study", False) else "No"
        
        # Handle availability
        avail_text = worker_data.get("availability_text", "")
        firebase_worker["Days & Times Available"] = avail_text
        
        # Add timestamps
        if "created_at" not in worker_data:
            firebase_worker["created_at"] = datetime.now().isoformat()
        else:
            firebase_worker["created_at"] = worker_data["created_at"]
            
        firebase_worker["updated_at"] = datetime.now().isoformat()
        
        return firebase_worker
    
    @staticmethod
    def map_worker_from_firebase(firebase_worker: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert from Firebase format to app worker format
        
        Args:
            firebase_worker: Worker data from Firebase
            
        Returns:
            Worker data in app format
        """
        if not firebase_worker:
            return {}
            
        # Make a copy to avoid modifying the original
        worker_data = {}
        
        # Handle field mapping
        worker_data["first_name"] = firebase_worker.get("First Name", "")
        worker_data["last_name"] = firebase_worker.get("Last Name", "")
        worker_data["email"] = firebase_worker.get("Email", "")
        
        # Convert "Yes"/"No" string to boolean
        work_study_str = firebase_worker.get("Work Study", "").lower()
        worker_data["work_study"] = work_study_str in ["yes", "y", "true"]
        
        # Handle availability
        avail_text = firebase_worker.get("Days & Times Available", "")
        worker_data["availability_text"] = avail_text
        
        # Parse availability if text exists
        if avail_text:
            worker_data["availability"] = parse_availability(avail_text)
        else:
            worker_data["availability"] = {}
        
        # Handle document ID if it exists
        if "id" in firebase_worker:
            worker_data["id"] = firebase_worker["id"]
        
        # Handle timestamps
        worker_data["created_at"] = firebase_worker.get("created_at", datetime.now().isoformat())
        worker_data["updated_at"] = firebase_worker.get("updated_at", datetime.now().isoformat())
        
        return worker_data
    
    @staticmethod
    def normalize_workplace_id(workplace_id: str) -> str:
        """
        Normalize a workplace ID to ensure consistency
        
        Args:
            workplace_id: Raw workplace ID
            
        Returns:
            Normalized workplace ID
        """
        if not workplace_id:
            return ""
        
        # Convert to lowercase and replace spaces with underscores
        return workplace_id.lower().replace(' ', '_')
    
    @staticmethod
    def create_or_update_workplace(db, workplace_id: str) -> bool:
        """
        Create a workplace document if it doesn't exist
        
        Args:
            db: Firestore database instance
            workplace_id: Workplace ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Normalize workplace ID
            workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
            
            # Try to get the document
            workplace_ref = db.collection('workplaces').document(workplace_id)
            workplace_doc = workplace_ref.get()
            
            # Create if it doesn't exist
            if not workplace_doc.exists:
                workplace_ref.set({
                    'name': workplace_id.replace('_', ' ').title(),
                    'created_at': datetime.now().isoformat()
                })
                logger.info(f"Created workplace document: {workplace_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating/updating workplace {workplace_id}: {e}")
            return False

    @staticmethod
    def ensure_workers_collection_exists(db, workplace_id: str) -> bool:
        """
        Ensure the workers collection exists for a workplace
        
        Args:
            db: Firestore database instance
            workplace_id: Workplace ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Normalize workplace ID
            workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
            
            # First make sure the workplace document exists
            FirebaseUtils.create_or_update_workplace(db, workplace_id)
            
            # Create a metadata document in the workers collection to ensure it exists
            # (While not strictly necessary, this makes the collection visible in the console)
            workplace_ref = db.collection('workplaces').document(workplace_id)
            workers_ref = workplace_ref.collection('workers')
            
            # Check if metadata document exists
            metadata_ref = workers_ref.document('_metadata')
            metadata_doc = metadata_ref.get()
            
            if not metadata_doc.exists:
                # Create metadata document
                metadata_ref.set({
                    'created_at': datetime.now().isoformat(),
                    'count': 0
                })
                logger.info(f"Created workers collection for workplace: {workplace_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error ensuring workers collection exists for {workplace_id}: {e}")
            return False

    @staticmethod
    def get_worker_collection_ref(db, workplace_id: str) -> Any:
        """
        Get the reference to the workers collection for a workplace.
        This handles both the nested structure and the flat structure.
        
        Args:
            db: Firestore database instance
            workplace_id: Workplace ID
            
        Returns:
            Firestore collection reference
        """
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        # First try the nested structure (recommended)
        nested_ref = db.collection('workplaces').document(workplace_id).collection('workers')
        
        # Check if the nested collection exists and has any documents
        try:
            if list(nested_ref.limit(1).stream()):
                logger.debug(f"Using nested structure for {workplace_id} workers")
                return nested_ref
        except Exception:
            pass
        
        # Fall back to flat structure
        logger.debug(f"Using flat structure for {workplace_id} workers")
        return db.collection(workplace_id)
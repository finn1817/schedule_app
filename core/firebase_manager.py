# schedule_app/core/firebase_manager.py

import logging
import time
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Dict, List, Optional, Any, Union
from .firebase_utils import FirebaseUtils

logger = logging.getLogger(__name__)

class FirebaseManager:
    """Manager class for Firebase operations"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize Firebase manager"""
        self.db = None
        self.current_workplace_id = None
        
        # Get Firestore database
        try:
            if firebase_admin._apps:
                # Get existing app
                app = firebase_admin.get_app()
                self.db = firestore.client(app=app)
                logger.info("Using existing Firebase app")
            else:
                # App not initialized
                logger.warning("Firebase app not initialized")
                self.db = None
                
        except Exception as e:
            logger.error(f"Error initializing Firebase manager: {e}")
            self.db = None
    
    def set_workplace(self, workplace_id: str) -> bool:
        """
        Set current workplace
        
        Args:
            workplace_id: Workplace ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return False
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        # Create workspace and ensure workers collection if it doesn't exist
        success = (FirebaseUtils.create_or_update_workplace(self.db, workplace_id) and 
                  FirebaseUtils.ensure_workers_collection_exists(self.db, workplace_id))
        
        if success:
            self.current_workplace_id = workplace_id
            logger.info(f"Current workplace set to: {workplace_id}")
            return True
        return False
    
    def get_workers(self, workplace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all workers for a workplace
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            
        Returns:
            List of worker data
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return []
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return []
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Get workers collection reference (handles nested or flat)
            workers_ref = FirebaseUtils.get_worker_collection_ref(self.db, workplace_id)
            
            # Get all workers
            workers = []
            for doc in workers_ref.stream():
                worker_data = doc.to_dict()
                worker_data["id"] = doc.id
                
                # Map to app format
                mapped_worker = FirebaseUtils.map_worker_from_firebase(worker_data)
                workers.append(mapped_worker)
            
            logger.info(f"Retrieved {len(workers)} workers for {workplace_id}")
            return workers
            
        except Exception as e:
            logger.error(f"Error getting workers for {workplace_id}: {e}")
            return []
    
    def add_worker(self, workplace_id: Optional[str], worker_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a worker to a workplace
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            worker_data: Worker data
            
        Returns:
            Worker ID if successful, None otherwise
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return None
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return None
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Convert worker data to Firebase format
            firebase_worker = FirebaseUtils.map_worker_to_firebase(worker_data)
            
            # Get workers collection reference (handles nested or flat)
            workers_ref = FirebaseUtils.get_worker_collection_ref(self.db, workplace_id)
            
            # Add the worker
            worker_ref = workers_ref.add(firebase_worker)
            worker_id = worker_ref[1].id
            
            logger.info(f"Added worker with ID {worker_id} to {workplace_id}")
            return worker_id
            
        except Exception as e:
            logger.error(f"Error adding worker to {workplace_id}: {e}")
            return None
    
    def update_worker(self, workplace_id: Optional[str], worker_id: str, worker_data: Dict[str, Any]) -> bool:
        """
        Update a worker
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            worker_id: Worker ID
            worker_data: Worker data
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return False
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return False
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Convert worker data to Firebase format
            firebase_worker = FirebaseUtils.map_worker_to_firebase(worker_data)
            
            # Add updated timestamp
            firebase_worker["updated_at"] = datetime.now().isoformat()
            
            # Get workers collection reference (handles nested or flat)
            workers_ref = FirebaseUtils.get_worker_collection_ref(self.db, workplace_id)
            
            # Update the worker
            workers_ref.document(worker_id).update(firebase_worker)
            
            logger.info(f"Updated worker with ID {worker_id} in {workplace_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating worker {worker_id} in {workplace_id}: {e}")
            return False
    
    def delete_worker(self, workplace_id: Optional[str], worker_id: str) -> bool:
        """
        Delete a worker
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            worker_id: Worker ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return False
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return False
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Get workers collection reference (handles nested or flat)
            workers_ref = FirebaseUtils.get_worker_collection_ref(self.db, workplace_id)
            
            # Delete the worker
            workers_ref.document(worker_id).delete()
            
            logger.info(f"Deleted worker with ID {worker_id} from {workplace_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting worker {worker_id} from {workplace_id}: {e}")
            return False
    
    def delete_worker_by_email(self, workplace_id: Optional[str], email: str) -> bool:
        """
        Delete a worker by email
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            email: Worker email
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return False
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return False
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Get workers collection reference (handles nested or flat)
            workers_ref = FirebaseUtils.get_worker_collection_ref(self.db, workplace_id)
            
            # Query for the worker by email
            query = workers_ref.where("Email", "==", email)
            
            # Get the matching documents
            docs = list(query.stream())
            
            if not docs:
                logger.warning(f"No worker found with email {email} in {workplace_id}")
                return False
            
            # Delete the first matching document
            docs[0].reference.delete()
            
            logger.info(f"Deleted worker with email {email} from {workplace_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting worker with email {email} from {workplace_id}: {e}")
            return False
    
    def remove_all_workers(self, workplace_id: Optional[str] = None) -> int:
        """
        Remove all workers from a workplace
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            
        Returns:
            Number of workers removed
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return 0
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return 0
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Get workers collection reference (handles nested or flat)
            workers_ref = FirebaseUtils.get_worker_collection_ref(self.db, workplace_id)
            
            # Get all worker documents
            docs = list(workers_ref.stream())
            count = len(docs)
            
            if count == 0:
                logger.info(f"No workers found in {workplace_id}")
                return 0
            
            # Delete in batches (max 500 per batch)
            batch_size = 450  # Keep under 500 to be safe
            batches_needed = (count + batch_size - 1) // batch_size
            
            logger.info(f"Removing {count} workers from {workplace_id} in {batches_needed} batches")
            
            for i in range(0, count, batch_size):
                batch = self.db.batch()
                batch_docs = docs[i:i+batch_size]
                
                for doc in batch_docs:
                    batch.delete(doc.reference)
                
                # Commit the batch
                batch.commit()
                
                logger.info(f"Deleted batch of {len(batch_docs)} workers")
                
                # Small delay to avoid overloading Firestore
                time.sleep(0.5)
            
            logger.info(f"Successfully removed {count} workers from {workplace_id}")
            return count
            
        except Exception as e:
            logger.error(f"Error removing all workers from {workplace_id}: {e}")
            return 0
    
    def get_hours_of_operation(self, workplace_id: Optional[str] = None) -> Dict[str, List[Dict[str, str]]]:
        """
        Get hours of operation for a workplace
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            
        Returns:
            Hours of operation data
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return {}
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return {}
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # First try to get hours from the nested structure
            workplace_ref = self.db.collection('workplaces').document(workplace_id)
            workplace_doc = workplace_ref.get()
            
            if workplace_doc.exists:
                workplace_data = workplace_doc.to_dict()
                hours = workplace_data.get('hours_of_operation', {})
                if hours:
                    logger.info(f"Retrieved hours of operation for {workplace_id} from nested structure")
                    return hours
            
            # If not found in nested structure, try the original flat structure
            hours_doc = self.db.collection(workplace_id).document('hours_of_operation').get()
            
            if hours_doc.exists:
                hours = hours_doc.to_dict()
                logger.info(f"Retrieved hours of operation for {workplace_id} from flat structure")
                return hours
            
            logger.warning(f"No hours of operation found for {workplace_id}")
            return {}
            
        except Exception as e:
            logger.error(f"Error getting hours of operation for {workplace_id}: {e}")
            return {}
    
    def update_hours_of_operation(self, workplace_id: Optional[str], hours_data: Dict[str, List[Dict[str, str]]]) -> bool:
        """
        Update hours of operation for a workplace
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            hours_data: Hours of operation data
            
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return False
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return False
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Update in both places to ensure compatibility
            
            # 1. Update in the nested structure (recommended)
            workplace_ref = self.db.collection('workplaces').document(workplace_id)
            workplace_ref.set({'hours_of_operation': hours_data}, merge=True)
            
            # 2. Update in the flat structure (for backwards compatibility)
            self.db.collection(workplace_id).document('hours_of_operation').set(hours_data)
            
            logger.info(f"Updated hours of operation for {workplace_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating hours of operation for {workplace_id}: {e}")
            return False
    
    def save_schedule(self, workplace_id: Optional[str], schedule_data: Dict[str, Any]) -> Optional[str]:
        """
        Save a schedule for a workplace
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            schedule_data: Schedule data
            
        Returns:
            Schedule ID if successful, None otherwise
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return None
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return None
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            # Make sure workplace_id is set in the schedule data
            if 'workplace_id' not in schedule_data:
                schedule_data['workplace_id'] = workplace_id
            
            # Add timestamps if not present
            if 'created_at' not in schedule_data:
                schedule_data['created_at'] = datetime.now().isoformat()
            schedule_data['updated_at'] = datetime.now().isoformat()
            
            # Add name if not present
            if 'name' not in schedule_data:
                schedule_data['name'] = f"{workplace_id.replace('_', ' ').title()} Schedule {datetime.now().strftime('%Y-%m-%d')}"
            
            # Save to nested structure (recommended)
            schedules_ref = self.db.collection('workplaces').document(workplace_id).collection('schedules')
            schedule_ref = schedules_ref.add(schedule_data)
            schedule_id = schedule_ref[1].id
            
            # Also save as current schedule in the flat structure (for backwards compatibility)
            self.db.collection(workplace_id).document('current_schedule').set(schedule_data)
            
            logger.info(f"Saved schedule with ID {schedule_id} for {workplace_id}")
            return schedule_id
            
        except Exception as e:
            logger.error(f"Error saving schedule for {workplace_id}: {e}")
            return None
    
    def get_schedules(self, workplace_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get schedules for a workplace
        
        Args:
            workplace_id: Workplace ID (optional, uses current if not specified)
            limit: Maximum number of schedules to return
            
        Returns:
            List of schedule data
        """
        if not self.db:
            logger.error("Firebase not initialized")
            return []
        
        # Use provided workplace_id or current
        if not workplace_id:
            if not self.current_workplace_id:
                logger.error("No workplace ID provided")
                return []
            workplace_id = self.current_workplace_id
        
        # Normalize workplace ID
        workplace_id = FirebaseUtils.normalize_workplace_id(workplace_id)
        
        try:
            schedules = []
            
            # First try nested structure (recommended)
            schedules_ref = self.db.collection('workplaces').document(workplace_id).collection('schedules')
            query = schedules_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
            
            for doc in query.stream():
                schedule = doc.to_dict()
                schedule['id'] = doc.id
                schedules.append(schedule)
            
            # If no schedules found in nested structure, try flat structure
            if not schedules:
                current_doc = self.db.collection(workplace_id).document('current_schedule').get()
                if current_doc.exists:
                    schedule = current_doc.to_dict()
                    schedule['id'] = 'current'
                    schedules.append(schedule)
            
            logger.info(f"Retrieved {len(schedules)} schedules for {workplace_id}")
            return schedules
            
        except Exception as e:
            logger.error(f"Error getting schedules for {workplace_id}: {e}")
            return []
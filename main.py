# schedule_app/main.py
#!/usr/bin/env python3

import sys
import os
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow
from core.data import get_data_manager
from core.config import firebase_available, initialize_firebase

# Configure logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def main():
    try:
        # Create application
        app = QApplication(sys.argv)
        
        # Initialize Firebase first
        firebase_status = initialize_firebase()
        if firebase_status:
            logger.info("Firebase initialized successfully at startup")
        else:
            logger.warning("Firebase initialization failed at startup")
        
        # Initialize data manager after Firebase
        data_manager = get_data_manager()
        
        # Create and show main window
        window = MainWindow()
        window.show()
        
        # If Firebase failed to initialize, show a warning
        if not firebase_available() and window is not None:
            QMessageBox.warning(
                window, 
                "Firebase Connection", 
                "Failed to connect to Firebase. Some features will be disabled.\n\n"
                "You can reconnect using the 'Connect to Firebase' button."
            )
        
        return app.exec_()
    except Exception as e:
        logger.error(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    main()
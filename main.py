# schedule_app/main.py
#!/usr/bin/env python3

import sys
import os
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox, QMainWindow, QPushButton, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
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

if os.name == 'nt':
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

class FullscreenMainWindow(MainWindow):
    """Extended MainWindow that opens in fullscreen with exit button"""
    def __init__(self):
        super().__init__()
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
        
        # Create a container for the exit button at the top-right
        exit_container = QWidget(self)
        exit_container.setFixedHeight(40)
        exit_container.setStyleSheet("background-color: transparent;")
        
        # Position in top-right corner
        exit_container.setGeometry(self.width() - 50, 10, 40, 40)
        
        # Create layout for the exit button
        exit_layout = QHBoxLayout(exit_container)
        exit_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create exit button
        exit_btn = QPushButton("✕")
        exit_btn.setFixedSize(30, 30)
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border-radius: 15px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #bd2130;
            }
        """)
        exit_btn.clicked.connect(self.close)
        
        exit_layout.addWidget(exit_btn)
        exit_container.show()
        
        # Make sure the exit button stays in the top-right corner when window is resized
        self.resizeEvent = self._handle_resize
    
    def _handle_resize(self, event):
        """Keep the exit button in the top-right corner when window is resized"""
        # Find the exit container
        for child in self.children():
            if isinstance(child, QWidget) and hasattr(child, 'layout'):
                layout = child.layout()
                if layout and layout.count() > 0:
                    item = layout.itemAt(0)
                    if item and isinstance(item.widget(), QPushButton) and item.widget().text() == "✕":
                        # Found the exit container, update its position
                        child.setGeometry(self.width() - 50, 10, 40, 40)
        
        # Call the original resize event
        QMainWindow.resizeEvent(self, event)

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
        
        # Create and show main window in fullscreen mode
        window = FullscreenMainWindow()
        window.showMaximized()  # Start maximized instead of normal size
        
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
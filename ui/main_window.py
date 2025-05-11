# schedule_app/ui/main_window.py

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                            QLabel, QPushButton, QMessageBox, QInputDialog, QLineEdit, QDialog, 
                            QFormLayout, QProgressDialog, QFileDialog)
from PyQt5.QtGui import QFont, QDesktopServices
from PyQt5.QtCore import Qt, pyqtSlot, QUrl
from .workplace_tab import WorkplaceTab
from .style_helper import StyleHelper
from core.config import initialize_firebase, db, firebase_available
from core.data import get_data_manager, export_all_workers_to_firebase, load_data, save_workers_from_ui
import logging
import json
import os
import sys

APP_NAME = "Workplace Scheduler"
APP_VERSION = "1.1.0"  # Updated version for Firebase integration

logger = logging.getLogger(__name__)

class FirebaseSetupDialog(QDialog):
    """Dialog for Firebase project setup"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Firebase Setup")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel(
            "To connect to Firebase, you need to provide a service account key. "
            "You can create one in the Firebase console under Project Settings > Service Accounts."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # File selection
        form = QFormLayout()
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
        
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(browse_btn)
        
        form.addRow("Service Account Key:", file_layout)
        layout.addLayout(form)
        
        # Visit Firebase console link
        link_label = QLabel("<a href='https://console.firebase.google.com/'>Visit Firebase Console</a>")
        link_label.setOpenExternalLinks(True)
        layout.addWidget(link_label)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.ok_button)
        buttons_layout.addWidget(self.cancel_button)
        layout.addLayout(buttons_layout)
    
    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Firebase Service Account Key", "", "JSON Files (*.json)"
        )
        if file_path:
            self.file_path.setText(file_path)
            self.ok_button.setEnabled(True)
        
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(StyleHelper.get_main_style())
        
        # Initialize data manager
        self.data_manager = get_data_manager()
        
        # Check Firebase connection
        self.firebase_status = firebase_available()
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Create header with app name and buttons
        header = QHBoxLayout()
        
        # Title
        title = QLabel(APP_NAME)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        header.addWidget(title)
        
        # Add spacer
        header.addStretch()
        
        # Create Firebase UI elements
        self.firebase_indicator = QLabel()
        self.firebase_connect_btn = QPushButton("Connect to Firebase")
        self.firebase_connect_btn.clicked.connect(self.connect_to_firebase)
        self.sync_btn = QPushButton("Sync Data")
        self.sync_btn.clicked.connect(self.sync_data)
        
        # Add Force Sync button
        self.force_sync_btn = QPushButton("Force Sync UI to Firebase")
        self.force_sync_btn.clicked.connect(self.force_sync_from_ui)
        self.force_sync_btn.setStyleSheet("background-color: #dc3545; color: white;")
        
        # Add Migration button
        self.migrate_btn = QPushButton("Run Full Migration")
        self.migrate_btn.clicked.connect(self.run_migration)
        self.migrate_btn.setStyleSheet("background-color: #007bff; color: white;")
        
        # Add Firebase status indicator
        header.addWidget(self.firebase_indicator)
        
        # Add Firebase connection button
        header.addWidget(self.firebase_connect_btn)
        
        # Add sync buttons
        header.addWidget(self.sync_btn)
        header.addWidget(self.force_sync_btn)
        header.addWidget(self.migrate_btn)
        
        # Version
        version = QLabel(f"v{APP_VERSION}")
        header.addWidget(version)
        
        layout.addLayout(header)
        
        # Create tabs for workplaces
        self.tabs = QTabWidget()
        self.tabs.addTab(WorkplaceTab("esports_lounge"),     "eSports Lounge")
        self.tabs.addTab(WorkplaceTab("esports_arena"),      "eSports Arena")
        self.tabs.addTab(WorkplaceTab("it_service_center"),  "IT Service Center")
        layout.addWidget(self.tabs)
        
        # Connect tab change signal
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Update Firebase UI elements after they're created
        self.update_firebase_status()
    
    def update_firebase_status(self):
        """Update the Firebase connection status indicator"""
        if self.firebase_status:
            self.firebase_indicator.setText("🟢 Firebase Connected")
            self.firebase_indicator.setStyleSheet("color: green;")
            self.firebase_connect_btn.setText("Reconnect Firebase")
            self.sync_btn.setEnabled(True)
            self.force_sync_btn.setEnabled(True)
            self.migrate_btn.setEnabled(True)
        else:
            self.firebase_indicator.setText("🔴 Firebase Disconnected")
            self.firebase_indicator.setStyleSheet("color: red;")
            self.firebase_connect_btn.setText("Connect to Firebase")
            self.sync_btn.setEnabled(False)
            self.force_sync_btn.setEnabled(False)
            self.migrate_btn.setEnabled(False)
    
    def on_tab_changed(self, index):
        """Handle tab change event"""
        if index >= 0 and self.firebase_status:
            current_tab = self.tabs.widget(index)
            if current_tab and isinstance(current_tab, WorkplaceTab):
                # Refresh the tab with Firebase data
                current_tab.load_workers_table()
                current_tab.load_hours_table()
    
    @pyqtSlot()
    def connect_to_firebase(self):
        """Attempt to connect or reconnect to Firebase"""
        # Check if credentials file exists
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cred_file = os.path.join(base_dir, 'workplace-scheduler-ace38-firebase-adminsdk-fbsvc-4d7d358b05.json')
        
        if not os.path.exists(cred_file):
            # Prompt for Firebase credentials if not found
            dlg = FirebaseSetupDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                selected_file = dlg.file_path.text()
                if selected_file and os.path.exists(selected_file):
                    # Copy the selected file to the default location
                    try:
                        import shutil
                        shutil.copy2(selected_file, cred_file)
                        QMessageBox.information(self, "Firebase Setup", 
                            "Credentials file copied successfully. Attempting to connect to Firebase.")
                    except Exception as e:
                        QMessageBox.critical(self, "Error", 
                            f"Failed to copy credentials file: {str(e)}")
                        return
                else:
                    QMessageBox.warning(self, "Warning", "No valid credentials file selected.")
                    return
        
        # Show progress dialog
        progress = QProgressDialog("Connecting to Firebase...", None, 0, 100, self)
        progress.setWindowTitle("Firebase Connection")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(10)
        progress.show()
        
        # Initialize Firebase
        success = initialize_firebase()
        self.firebase_status = success
        
        progress.setValue(100)
        
        if success:
            QMessageBox.information(self, "Firebase Connection", 
                                   "Successfully connected to Firebase!")
            
            # Load default workplace into data manager
            current_tab = self.tabs.currentWidget()
            if current_tab and isinstance(current_tab, WorkplaceTab):
                self.data_manager.load_workplace(current_tab.workplace)
                
                # Refresh the current tab
                current_tab.load_workers_table()
                current_tab.load_hours_table()
        else:
            QMessageBox.critical(self, "Firebase Connection Error", 
                                "Failed to connect to Firebase. Check your credentials and internet connection.")
        
        self.update_firebase_status()
    
    def run_migration(self):
        """Run the full migration script"""
        if not self.firebase_status:
            QMessageBox.warning(self, "Firebase Not Connected", 
                             "Firebase must be connected to run migration.")
            return
        
        # Ask for confirmation
        reply = QMessageBox.question(
            self, "Run Full Migration",
            "This will migrate all data from local storage to Firebase.\n\n"
            "This process may take several minutes depending on the amount of data.\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Show progress dialog
        progress = QProgressDialog("Running migration...", None, 0, 100, self)
        progress.setWindowTitle("Firebase Migration")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(10)
        progress.show()
        
        try:
            # Import and run migration script
            from scripts.firebase_migration import run_migration
            
            # Run in a separate thread to avoid freezing UI
            import threading
            
            def run_migration_thread():
                result = run_migration()
                # Update UI from main thread
                from PyQt5.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "migration_completed", 
                    Qt.QueuedConnection, 
                    Q_ARG(bool, result)
                )
            
            # Start migration thread
            threading.Thread(target=run_migration_thread).start()
            
            # Update progress (not actual progress, just visual feedback)
            import time
            for i in range(11, 100, 10):
                time.sleep(1)  # Simulate work being done
                progress.setValue(i)
                
            # Final progress will be set when migration completes
            
        except Exception as e:
            progress.setValue(100)
            QMessageBox.critical(self, "Migration Error", 
                              f"Error running migration: {str(e)}")
            logger.error(f"Migration error: {e}")
    
    @pyqtSlot(bool)
    def migration_completed(self, success):
        """Called when migration is complete"""
        if success:
            QMessageBox.information(self, "Migration Complete", 
                                 "Data migration to Firebase completed successfully.")
            
            # Refresh all tabs
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                if isinstance(tab, WorkplaceTab):
                    tab.load_workers_table()
                    tab.load_hours_table()
        else:
            QMessageBox.warning(self, "Migration Warning", 
                             "Migration completed with some errors. Check the log file for details.")
    
    @pyqtSlot()
    def sync_data(self):
        """Sync data with Firebase"""
        if not self.firebase_status:
            QMessageBox.warning(self, "Sync Failed", "Firebase is not connected.")
            return
        
        # Get current tab
        current_tab = self.tabs.currentWidget()
        if current_tab and isinstance(current_tab, WorkplaceTab):
            current_workplace = current_tab.workplace
            display_name = current_workplace.replace('_', ' ').title()
            
            # Show progress dialog
            progress = QProgressDialog(f"Syncing {display_name}...", None, 0, 100, self)
            progress.setWindowTitle("Firebase Sync")
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(10)
            progress.show()
            
            try:
                # Load workplace data
                progress.setValue(30)
                self.data_manager.load_workplace(current_workplace)
                
                # Export workers
                progress.setValue(60)
                result = export_all_workers_to_firebase(current_workplace)
                
                # Refresh UI
                progress.setValue(90)
                if result:
                    current_tab.load_workers_table()
                    current_tab.load_hours_table()
                    
                progress.setValue(100)
                
                if result:
                    QMessageBox.information(self, "Sync Complete", 
                                        f"Successfully synced data for {display_name}.")
                else:
                    QMessageBox.warning(self, "Sync Incomplete", 
                                     f"Some data may not have synced properly for {display_name}.")
                
            except Exception as e:
                progress.setValue(100)
                logger.error(f"Sync error: {e}")
                QMessageBox.critical(self, "Sync Error", 
                                  f"Error syncing data: {str(e)}")

    @pyqtSlot()
    def force_sync_from_ui(self):
        """Force sync workers from UI table to Firebase"""
        if not self.firebase_status:
            QMessageBox.warning(self, "Sync Failed", "Firebase is not connected.")
            return
        
        # Get current tab
        current_tab = self.tabs.currentWidget()
        if current_tab and isinstance(current_tab, WorkplaceTab):
            # Get workers from the table
            workers = current_tab.get_workers_from_table()
            
            if workers:
                current_workplace = current_tab.workplace
                display_name = current_workplace.replace('_', ' ').title()
                
                # Confirm with the user
                reply = QMessageBox.question(
                    self, "Force Sync UI to Firebase",
                    f"This will overwrite all workers in Firebase with the {len(workers)} workers currently shown in the UI.\n\n"
                    f"Are you sure you want to continue?",
                    QMessageBox.Yes | QMessageBox.No, 
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    # Show progress dialog
                    progress = QProgressDialog("Exporting to Firebase...", None, 0, 100, self)
                    progress.setWindowTitle("Firebase Export")
                    progress.setWindowModality(Qt.WindowModal)
                    progress.setValue(10)
                    progress.show()
                    
                    try:
                        # Use the save_workers_from_ui function
                        progress.setValue(50)
                        result = save_workers_from_ui(current_workplace, workers)
                        
                        progress.setValue(100)
                        
                        if result:
                            QMessageBox.information(self, "Sync Complete", 
                                                f"Successfully exported {len(workers)} workers from UI to Firebase for {display_name}.")
                            
                            # Refresh the tab to show updated data
                            self.data_manager.load_workplace(current_workplace)
                            current_tab.load_workers_table()
                        else:
                            QMessageBox.warning(self, "Sync Failed", 
                                            f"Failed to export workers to Firebase for {display_name}.")
                    except Exception as e:
                        progress.setValue(100)
                        logger.error(f"Force sync error: {e}")
                        QMessageBox.critical(self, "Sync Error", 
                                          f"Error syncing data: {str(e)}")
            else:
                QMessageBox.warning(self, "Sync Warning", 
                                "No workers found in the current table.")

    def show_log_dialog(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel
        import os
        log_path = os.path.join("logs", "firebase_test.log")
        dlg = QDialog(self)
        dlg.setWindowTitle("Application Log")
        dlg.setMinimumSize(800, 500)
        L = QVBoxLayout(dlg)
        title = QLabel("Application Log Output")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #343a40; margin-bottom: 10px;")
        L.addWidget(title)
        log_view = QTextEdit()
        log_view.setReadOnly(True)
        log_view.setStyleSheet("background-color: #212529; color: #e9ecef; font-family: monospace; font-size: 12px; border-radius: 6px; padding: 8px;")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                log_view.setPlainText(f.read())
        else:
            log_view.setPlainText("Log file not found: " + log_path)
        L.addWidget(log_view)
        btns = QHBoxLayout()
        btns.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btns.addWidget(close_btn)
        L.addLayout(btns)
        dlg.exec_()
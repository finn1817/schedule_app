# schedule_app/ui/last_minute_availability_dialog.py

import os, logging, pandas as pd
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QFormLayout, QHBoxLayout,
    QComboBox, QTimeEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QProgressDialog,
    QCheckBox, QWidget  # Added QWidget to the imports
)
from PyQt5.QtCore import QTime, Qt
from .style_helper import StyleHelper
from core.config import DIRS, firebase_available
from core.parser import parse_availability, format_time_ampm
from core.data import get_data_manager

logger = logging.getLogger(__name__)

DAYS = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

class LastMinuteAvailabilityDialog(QDialog):
    def __init__(self, workplace, parent=None):
        super().__init__(parent)
        self.workplace = workplace
        self.workers = []
        self.firebase_available = firebase_available()
        self.data_manager = get_data_manager() if self.firebase_available else None
        self.initUI()
        self.loadWorkers()

    def initUI(self):
        self.setWindowTitle(f"Last Minute Availability - {self.workplace.replace('_',' ').title()}")
        self.setMinimumSize(800, 600)
        layout = QVBoxLayout(self)

        # Header with Firebase status
        header_layout = QHBoxLayout()
        title = QLabel("Check Last Minute Availability")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)
        
        # Firebase indicator
        if self.firebase_available:
            fb_status = QLabel("✅ Using Firebase Data")
            fb_status.setStyleSheet("color: #28a745; font-weight: bold;")
            header_layout.addWidget(fb_status)
        else:
            fb_status = QLabel("⚠️ Using Local Data Only")
            fb_status.setStyleSheet("color: #ffc107; font-weight: bold;")
            header_layout.addWidget(fb_status)
        
        layout.addLayout(header_layout)

        # Form for day and time selection
        form = QFormLayout()
        self.day = QComboBox()
        self.day.addItems(DAYS)
        form.addRow("Day:", self.day)
        
        hl = QHBoxLayout()
        self.st = QTimeEdit()
        self.st.setDisplayFormat("HH:mm")
        self.st.setTime(QTime(9,0))
        self.et = QTimeEdit()
        self.et.setDisplayFormat("HH:mm")
        self.et.setTime(QTime(17,0))
        hl.addWidget(QLabel("Start:"))
        hl.addWidget(self.st)
        hl.addWidget(QLabel("End:"))
        hl.addWidget(self.et)
        form.addRow("Time:", hl)
        layout.addLayout(form)

        # Add data source option
        data_source_layout = QHBoxLayout()
        
        if self.firebase_available:
            self.use_firebase = QCheckBox("Use Firebase data (recommended)")
            self.use_firebase.setChecked(True)
            data_source_layout.addWidget(self.use_firebase)
        
        self.use_local = QCheckBox("Use local Excel data")
        self.use_local.setChecked(not self.firebase_available)
        data_source_layout.addWidget(self.use_local)
        
        # Connect checkboxes to keep only one checked
        if self.firebase_available:
            self.use_firebase.stateChanged.connect(self.sync_checkboxes)
        self.use_local.stateChanged.connect(self.sync_checkboxes)
        
        layout.addLayout(data_source_layout)

        # Check availability button
        button_layout = QHBoxLayout()
        chk = StyleHelper.create_action_button("Check Availability")
        chk.clicked.connect(self.checkAvailability)
        button_layout.addWidget(chk)
        
        reload_btn = StyleHelper.create_button("Reload Workers")
        reload_btn.clicked.connect(self.loadWorkers)
        button_layout.addWidget(reload_btn)
        
        layout.addLayout(button_layout)

        # Results table
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(4)
        self.tbl.setHorizontalHeaderLabels(["Name", "Email", "Work Study", "Contact"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tbl)

        # Status label
        self.status_label = QLabel("Ready to check availability.")
        layout.addWidget(self.status_label)

        # Close button
        close_btn = StyleHelper.create_button("Close", primary=False)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def sync_checkboxes(self, state):
        """Keep only one checkbox checked"""
        if self.firebase_available:
            if self.sender() == self.use_firebase and state == Qt.Checked:
                self.use_local.setChecked(False)
            elif self.sender() == self.use_local and state == Qt.Checked:
                self.use_firebase.setChecked(False)
        
        # Ensure at least one is checked
        if self.firebase_available and not self.use_firebase.isChecked() and not self.use_local.isChecked():
            if self.sender() == self.use_firebase:
                self.use_local.setChecked(True)
            else:
                self.use_firebase.setChecked(True)

    def loadWorkers(self):
        """Load workers from either Firebase or Excel file"""
        self.workers = []
        
        # Show progress dialog
        progress = QProgressDialog("Loading workers...", None, 0, 100, self)
        progress.setWindowTitle("Loading")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(10)
        progress.show()
        
        # Determine the data source to use
        use_firebase = self.firebase_available and (
            not hasattr(self, 'use_firebase') or self.use_firebase.isChecked()
        )
        
        if use_firebase:
            # Load from Firebase
            progress.setValue(30)
            progress.setLabelText("Loading workers from Firebase...")
            
            try:
                # Make sure data manager is using the correct workplace
                self.data_manager.load_workplace(self.workplace)
                
                # Get workers
                firebase_workers = self.data_manager.get_workers()
                
                progress.setValue(60)
                
                if firebase_workers:
                    for worker in firebase_workers:
                        self.workers.append({
                            "first_name": worker.get("first_name", "").strip(),
                            "last_name": worker.get("last_name", "").strip(),
                            "email": worker.get("email", "").strip(),
                            "work_study": worker.get("work_study", False),
                            "availability": worker.get("availability", {})
                        })
                    
                    progress.setValue(90)
                    self.status_label.setText(f"Loaded {len(self.workers)} workers from Firebase.")
                    logger.info(f"Loaded {len(self.workers)} workers from Firebase for {self.workplace}")
                else:
                    # Try local Excel as fallback
                    progress.setValue(70)
                    progress.setLabelText("No workers found in Firebase. Trying local Excel file...")
                    self._load_from_excel(progress)
            except Exception as e:
                logger.error(f"Error loading workers from Firebase: {e}")
                progress.setValue(70)
                progress.setLabelText("Error with Firebase. Trying local Excel file...")
                self._load_from_excel(progress)
        else:
            # Load from Excel
            progress.setValue(30)
            progress.setLabelText("Loading workers from Excel file...")
            self._load_from_excel(progress)
        
        progress.setValue(100)
        
        # Update status label
        if self.workers:
            self.status_label.setText(f"Loaded {len(self.workers)} workers. Ready to check availability.")
        else:
            self.status_label.setText("No workers loaded. Please check data source.")

    def _load_from_excel(self, progress=None):
        """Load workers from Excel file"""
        path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
        if not os.path.exists(path):
            if progress:
                progress.setValue(100)
            QMessageBox.warning(self, "Warning", "No Excel file found.")
            self.status_label.setText("Error: No Excel file found.")
            return
        
        try:
            if progress:
                progress.setLabelText("Reading Excel file...")
                
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip()
            df = df.dropna(subset=['Email'], how='all')
            df = df[df['Email'].str.strip()!='']
            
            if progress:
                progress.setValue(80)
                progress.setLabelText("Processing worker data...")
            
            col = next((c for c in df.columns if 'available' in c.lower()), None)
            for _, r in df.iterrows():
                txt = str(r.get(col,"")) if col else ""
                if pd.isna(txt) or txt.lower()=="nan":
                    txt = ""
                avail = parse_availability(txt)
                self.workers.append({
                    "first_name": r.get("First Name","").strip(),
                    "last_name":  r.get("Last Name","").strip(),
                    "email":      r.get("Email","").strip(),
                    "work_study": str(r.get("Work Study","")).strip().lower() in ['yes','y','true'],
                    "availability": avail
                })
            
            self.status_label.setText(f"Loaded {len(self.workers)} workers from Excel file.")
            logger.info(f"Loaded {len(self.workers)} workers from Excel for {self.workplace}")
            
            if progress:
                progress.setValue(100)
                
        except Exception as e:
            if progress:
                progress.setValue(100)
            logger.error(f"Load workers from Excel: {e}")
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText(f"Error loading workers: {str(e)}")

    def checkAvailability(self):
        try:
            if not self.workers:
                QMessageBox.warning(self, "No Workers", "Please load workers first.")
                return
            
            day = self.day.currentText()
            st = self.st.time().toString("HH:mm")
            et = self.et.time().toString("HH:mm")
            
            # Parse start and end hours
            start_hour = int(st[:2])
            end_hour = int(et[:2])
            
            if start_hour >= end_hour:
                QMessageBox.warning(self, "Invalid Time Range", "End time must be after start time.")
                return
            
            # Find available workers
            avail = []
            for w in self.workers:
                day_blocks = w['availability'].get(day, [])
                if not day_blocks:
                    continue
                    
                for b in day_blocks:
                    if b.get('start_hour', 0) <= start_hour and end_hour <= b.get('end_hour', 24):
                        avail.append(w)
                        break
            
            # Update results table
            self.tbl.setRowCount(len(avail))
            for i, w in enumerate(avail):
                # Name column
                name = f"{w['first_name']} {w['last_name']}"
                self.tbl.setItem(i, 0, QTableWidgetItem(name))
                
                # Email column
                email_item = QTableWidgetItem(w['email'])
                self.tbl.setItem(i, 1, email_item)
                
                # Work Study column
                work_study_text = "Yes" if w['work_study'] else "No"
                work_study_item = QTableWidgetItem(work_study_text)
                if w['work_study']:
                    work_study_item.setBackground(Qt.yellow)
                self.tbl.setItem(i, 2, work_study_item)
                
                # Add contact button
                contact_cell = QWidget()
                contact_layout = QHBoxLayout(contact_cell)
                contact_layout.setContentsMargins(2, 2, 2, 2)
                
                email_btn = QPushButton("Email")
                email_btn.setStyleSheet("background-color: #007bff; color: white;")
                email_btn.clicked.connect(lambda _, email=w['email']: self.compose_email(email))
                
                contact_layout.addWidget(email_btn)
                self.tbl.setCellWidget(i, 3, contact_cell)
            
            # Update status
            if avail:
                self.status_label.setText(f"Found {len(avail)} available workers on {day} from {format_time_ampm(st)} to {format_time_ampm(et)}.")
            else:
                QMessageBox.warning(self, "No Available Workers",
                    f"No workers available on {day} from {format_time_ampm(st)} to {format_time_ampm(et)}.")
                self.status_label.setText(f"No workers available on {day} from {format_time_ampm(st)} to {format_time_ampm(et)}.")
            
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            QMessageBox.critical(self, "Error", f"Error checking availability: {str(e)}")
            self.status_label.setText(f"Error: {str(e)}")
    
    def compose_email(self, email):
        """Open default email client to contact worker"""
        try:
            # Get day and time info for email subject
            day = self.day.currentText()
            start_time = format_time_ampm(self.st.time().toString("HH:mm"))
            end_time = format_time_ampm(self.et.time().toString("HH:mm"))
            
            # Create email subject and body
            subject = f"Urgent Shift Coverage Needed: {day} {start_time} - {end_time}"
            body = f"Hello,\n\nWe need coverage for a shift on {day} from {start_time} to {end_time}.\n\nPlease let me know if you are available.\n\nThank you,\n{self.workplace.replace('_', ' ').title()} Management"
            
            # Create mailto URL
            import urllib.parse
            mailto_url = f"mailto:{email}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
            
            # Open default email client
            from PyQt5.QtGui import QDesktopServices
            from PyQt5.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(mailto_url))
            
        except Exception as e:
            logger.error(f"Error composing email: {e}")
            QMessageBox.critical(self, "Error", f"Could not open email client: {str(e)}")
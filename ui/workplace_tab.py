# schedule_app/ui/workplace_tab.py

import os
import logging
import shutil
import json
import pandas as pd
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QTabWidget, QDialog, QFormLayout, QSpinBox, QComboBox,
    QLineEdit, QTextEdit, QHeaderView, QListWidget, QListWidgetItem,
    QProgressDialog, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from PyQt5.QtGui import QTextDocument

from core.config import DIRS, DAYS, db, firebase_available
from core.data import (
    load_data, save_data, get_data_manager, get_workers as fb_get_workers, 
    save_worker as fb_save_worker, delete_worker as fb_delete_worker,
    export_all_workers_to_firebase, save_workers_from_ui
)
from core.parser import parse_availability, format_time_ampm, time_to_hour
from core.scheduler import create_shifts_from_availability
from core.exporter import send_schedule_email
from core.firebase_manager import FirebaseManager
from .style_helper import StyleHelper
from .hours_of_operation_dialog import HoursOfOperationDialog
from .alternative_solutions_dialog import AlternativeSolutionsDialog
from .last_minute_availability_dialog import LastMinuteAvailabilityDialog
from .shift_override_dialog import ShiftOverrideDialog


class WorkplaceTab(QWidget):
    """Tab for managing a specific workplace."""
    def __init__(self, workplace, parent=None):
        super().__init__(parent)
        self.workplace = workplace
        self.app_data = load_data()
        self.data_manager = get_data_manager()
        self.firebase_enabled = firebase_available()
        self.firebase_manager = FirebaseManager.get_instance() if self.firebase_enabled else None
        self.initUI()
        
        # Try to load workplace data from Firebase if available
        if self.firebase_enabled:
            self.data_manager.load_workplace(workplace)

    def initUI(self):
        layout = QVBoxLayout(self)

        # Title
        title = StyleHelper.create_section_title(
            self.workplace.replace('_',' ').title()
        )
        layout.addWidget(title)

        # Firebase status indicator
        if self.firebase_enabled:
            status = QLabel("✅ Firebase Connected")
            status.setStyleSheet("color: #28a745; font-weight: bold;")
        else:
            status = QLabel("❌ Firebase Not Connected")
            status.setStyleSheet("color: #dc3545; font-weight: bold;")
        layout.addWidget(status)

        # Quick action buttons
        btn_layout = QHBoxLayout()
        upload_btn   = StyleHelper.create_button("Upload Excel File")
        upload_btn.clicked.connect(self.upload_excel)
        hours_btn    = StyleHelper.create_button("Hours of Operation")
        hours_btn.clicked.connect(self.manage_hours)
        generate_btn = StyleHelper.create_action_button("Generate Schedule")
        generate_btn.clicked.connect(self.generate_schedule)
        view_btn     = StyleHelper.create_button("View Current Schedule", primary=False)
        view_btn.clicked.connect(self.view_current_schedule)
        last_btn     = StyleHelper.create_button("Last Minute", primary=False)
        last_btn.setStyleSheet("background-color: #fd7e14; color: white;")
        last_btn.clicked.connect(self.show_last_minute_dialog)

        # Add Firebase sync button if Firebase is enabled
        if self.firebase_enabled:
            sync_btn = StyleHelper.create_button("Sync with Firebase", primary=False)
            sync_btn.setStyleSheet("background-color: #17a2b8; color: white;")
            sync_btn.clicked.connect(self.sync_with_firebase)
            btn_layout.addWidget(sync_btn)

        for b in (upload_btn, hours_btn, generate_btn, view_btn, last_btn):
            btn_layout.addWidget(b)
        layout.addLayout(btn_layout)

        # Tabs: Workers + Hours only
        self.tabs = QTabWidget()
        self._make_workers_tab()
        self._make_hours_tab()
        layout.addWidget(self.tabs)

    def _make_workers_tab(self):
        tab = QWidget()
        L = QVBoxLayout(tab)

        self.workers_table = QTableWidget()
        self.workers_table.setColumnCount(6)
        self.workers_table.setHorizontalHeaderLabels([
            "First Name","Last Name","Email","Work Study","Availability","Actions"
        ])
        self.load_workers_table()
        L.addWidget(self.workers_table)

        btn_layout = QHBoxLayout()
        add_btn    = StyleHelper.create_button("Add Worker")
        add_btn.clicked.connect(self.add_worker_dialog)
        remove_btn = StyleHelper.create_button("Remove All Workers", primary=False)
        remove_btn.setStyleSheet("background-color: #dc3545; color: white;")
        remove_btn.clicked.connect(self.remove_all_workers)
        
        # If Firebase enabled, add Export to Firebase button
        if self.firebase_enabled:
            export_btn = StyleHelper.create_button("Export to Firebase", primary=False)
            export_btn.setStyleSheet("background-color: #28a745; color: white;")
            export_btn.clicked.connect(self.export_workers_to_firebase)
            btn_layout.addWidget(export_btn)
            
            import_btn = StyleHelper.create_button("Import from Firebase", primary=False)
            import_btn.setStyleSheet("background-color: #17a2b8; color: white;")
            import_btn.clicked.connect(self.import_workers_from_firebase)
            btn_layout.addWidget(import_btn)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        L.addLayout(btn_layout)

        self.tabs.addTab(tab, "Workers")

    def _make_hours_tab(self):
        tab = QWidget()
        L = QVBoxLayout(tab)

        self.hours_table = QTableWidget()
        self.hours_table.setColumnCount(3)
        self.hours_table.setHorizontalHeaderLabels(["Day","Start","End"])
        self.load_hours_table()
        L.addWidget(self.hours_table)

        btn_layout = QHBoxLayout()
        btn = StyleHelper.create_button("Edit Hours of Operation")
        btn.clicked.connect(self.manage_hours)
        btn_layout.addWidget(btn)
        
        # If Firebase enabled, add sync hours button
        if self.firebase_enabled:
            sync_hours_btn = StyleHelper.create_button("Sync Hours with Firebase", primary=False)
            sync_hours_btn.setStyleSheet("background-color: #17a2b8; color: white;")
            sync_hours_btn.clicked.connect(self.sync_hours_with_firebase)
            btn_layout.addWidget(sync_hours_btn)
        
        L.addLayout(btn_layout)

        self.tabs.addTab(tab, "Hours of Operation")

    def load_workers_table(self):
        self.workers_table.setRowCount(0)
        
        # Try to load from Firebase first if enabled
        firebase_workers = []
        if self.firebase_enabled:
            try:
                firebase_workers = fb_get_workers(self.workplace)
                if firebase_workers:
                    self._populate_workers_table_from_firebase(firebase_workers)
                    return
            except Exception as e:
                logging.error(f"Error loading workers from Firebase: {e}")
                # Fall back to local file
                pass
        
        # If Firebase loading failed or is disabled, load from Excel file
        path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
        if not os.path.exists(path):
            return

        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip()
            df = df.dropna(subset=['Email'], how='all')
            df = df[df['Email'].str.strip() != '']
            df = df[~df['Email'].str.contains('nan', case=False, na=False)]

            self.workers_table.setRowCount(len(df))
            for i, (_, row) in enumerate(df.iterrows()):
                fn = row.get("First Name","") or ""
                ln = row.get("Last Name","") or ""
                em = row.get("Email","") or ""
                ws = row.get("Work Study","No") or "No"
                avail_col = next((c for c in df.columns if 'available' in c.lower()), None)
                at = str(row.get(avail_col,"")) if avail_col else ""

                self.workers_table.setItem(i,0,QTableWidgetItem(fn))
                self.workers_table.setItem(i,1,QTableWidgetItem(ln))
                self.workers_table.setItem(i,2,QTableWidgetItem(em))
                self.workers_table.setItem(i,3,QTableWidgetItem(ws))
                self.workers_table.setItem(i,4,QTableWidgetItem(at))

                actions = QWidget()
                hl = QHBoxLayout(actions)
                hl.setContentsMargins(0,0,0,0)
                e = QPushButton("Edit")
                e.setStyleSheet("background:#ffc107;")
                e.clicked.connect(lambda _,r=i,em=em: self.edit_worker_dialog(r,em))
                d = QPushButton("Delete")
                d.setStyleSheet("background:#dc3545;")
                d.clicked.connect(lambda _,em=em: self.delete_worker(em))
                hl.addWidget(e)
                hl.addWidget(d)
                self.workers_table.setCellWidget(i,5,actions)

            self.workers_table.resizeColumnsToContents()
            self.tabs.setCurrentIndex(0)

        except Exception as e:
            logging.error(f"Error loading workers from Excel: {e}")
            QMessageBox.critical(self, "Error", f"Error loading workers: {e}")

    def _populate_workers_table_from_firebase(self, workers):
        """Populate workers table with data from Firebase"""
        try:
            self.workers_table.setRowCount(len(workers))
            for i, worker in enumerate(workers):
                fn = worker.get("first_name", "")
                ln = worker.get("last_name", "")
                em = worker.get("email", "")
                ws = "Yes" if worker.get("work_study", False) else "No"
                
                # Format availability from object to string
                avail = worker.get("availability", {})
                avail_str = worker.get("availability_text", "")
                
                # If no formatted text exists, build it from the structured availability
                if not avail_str:
                    avail_str = ""
                    for day, times in avail.items():
                        for time_range in times:
                            if avail_str:
                                avail_str += ", "
                            avail_str += f"{day} {time_range['start']}-{time_range['end']}"
                
                self.workers_table.setItem(i,0,QTableWidgetItem(fn))
                self.workers_table.setItem(i,1,QTableWidgetItem(ln))
                self.workers_table.setItem(i,2,QTableWidgetItem(em))
                self.workers_table.setItem(i,3,QTableWidgetItem(ws))
                self.workers_table.setItem(i,4,QTableWidgetItem(avail_str))

                actions = QWidget()
                hl = QHBoxLayout(actions)
                hl.setContentsMargins(0,0,0,0)
                e = QPushButton("Edit")
                e.setStyleSheet("background:#ffc107;")
                e.clicked.connect(lambda _,r=i,em=em,wid=worker.get('id',''): 
                                 self.edit_worker_dialog(r, em, worker_id=wid))
                d = QPushButton("Delete")
                d.setStyleSheet("background:#dc3545;")
                d.clicked.connect(lambda _,em=em,wid=worker.get('id',''): 
                                 self.delete_worker(em, worker_id=wid))
                hl.addWidget(e)
                hl.addWidget(d)
                self.workers_table.setCellWidget(i,5,actions)

            self.workers_table.resizeColumnsToContents()
            self.tabs.setCurrentIndex(0)
            
        except Exception as e:
            logging.error(f"Error populating workers table from Firebase: {e}")
            QMessageBox.critical(self, "Error", f"Error loading workers from Firebase: {e}")

    def load_hours_table(self):
        self.hours_table.setRowCount(0)
        
        # Try to load from Firebase first if enabled
        if self.firebase_enabled:
            try:
                hours = self.data_manager.get_hours_of_operation()
                if hours:
                    total = sum(len(v) for v in hours.values())
                    self.hours_table.setRowCount(total or len(DAYS))  # At least one row per day
                    
                    r = 0
                    for day in DAYS:
                        blocks = hours.get(day, [])
                        if not blocks:
                            self.hours_table.setItem(r,0,QTableWidgetItem(day))
                            self.hours_table.setItem(r,1,QTableWidgetItem("Closed"))
                            self.hours_table.setItem(r,2,QTableWidgetItem("Closed"))
                            r += 1
                        else:
                            for b in blocks:
                                self.hours_table.setItem(r,0,QTableWidgetItem(day))
                                self.hours_table.setItem(r,1,QTableWidgetItem(format_time_ampm(b['start'])))
                                self.hours_table.setItem(r,2,QTableWidgetItem(format_time_ampm(b['end'])))
                                r += 1
                    
                    self.hours_table.resizeColumnsToContents()
                    return
            except Exception as e:
                logging.error(f"Error loading hours from Firebase: {e}")
                # Fall back to app_data
        
        # If Firebase loading failed or is disabled, load from app_data
        hours = self.app_data.get(self.workplace, {}).get('hours_of_operation', {})
        total = sum(len(v) for v in hours.values())
        self.hours_table.setRowCount(total or len(DAYS))  # At least one row per day
        r = 0
        for day in DAYS:
            blocks = hours.get(day, [])
            if not blocks:
                self.hours_table.setItem(r,0,QTableWidgetItem(day))
                self.hours_table.setItem(r,1,QTableWidgetItem("Closed"))
                self.hours_table.setItem(r,2,QTableWidgetItem("Closed"))
                r += 1
            else:
                for b in blocks:
                    self.hours_table.setItem(r,0,QTableWidgetItem(day))
                    self.hours_table.setItem(r,1,QTableWidgetItem(format_time_ampm(b['start'])))
                    self.hours_table.setItem(r,2,QTableWidgetItem(format_time_ampm(b['end'])))
                    r += 1
        self.hours_table.resizeColumnsToContents()

    def upload_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Upload Excel File", "", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return
        try:
            dst = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            shutil.copy2(file_path, dst)
            self.clean_excel_file(dst)
            self.load_workers_table()
            QMessageBox.information(self, "Success", "Excel file uploaded successfully.")
            
            # Ask if user wants to export to Firebase
            if self.firebase_enabled:
                reply = QMessageBox.question(
                    self, "Export to Firebase?",
                    "Would you like to export these workers to Firebase?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.export_workers_to_firebase()
                    
        except Exception as e:
            logging.error(f"Error uploading Excel file: {e}")
            QMessageBox.critical(self, "Error", f"Error uploading Excel file: {e}")

    def clean_excel_file(self, file_path):
        try:
            df = pd.read_excel(file_path)
            df.columns = df.columns.str.strip()
            df = df.dropna(subset=['Email'], how='all')
            df = df[df['Email'].str.strip() != '']
            df = df[~df['Email'].str.contains('nan', case=False, na=False)]
            df.to_excel(file_path, index=False)
        except Exception as e:
            logging.error(f"Error cleaning Excel file: {e}")
            raise

    def add_worker_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Worker")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        fn = QLineEdit(); form.addRow("First Name:", fn)
        ln = QLineEdit(); form.addRow("Last Name:", ln)
        em = QLineEdit(); form.addRow("Email:", em)
        ws = QComboBox(); ws.addItems(["No","Yes"]); form.addRow("Work Study:", ws)
        avail = QTextEdit()
        avail.setPlaceholderText("Day HH:MM-HH:MM, ...")
        avail.setMinimumHeight(100)
        form.addRow("Availability:", avail)
        
        # Add Firebase option if enabled
        if self.firebase_enabled:
            use_firebase = QCheckBox("Save to Firebase")
            use_firebase.setChecked(True)
            form.addRow("", use_firebase)
        else:
            use_firebase = None
            
        layout.addLayout(form)

        btns = QHBoxLayout()
        save = StyleHelper.create_button("Save")
        cancel = StyleHelper.create_button("Cancel", primary=False)
        btns.addWidget(save); btns.addWidget(cancel)
        layout.addLayout(btns)

        save.clicked.connect(lambda: self.save_worker(
            dialog, fn.text(), ln.text(), em.text(),
            ws.currentText(), avail.toPlainText(),
            use_firebase.isChecked() if use_firebase else False
        ))
        cancel.clicked.connect(dialog.reject)

        dialog.exec_()

    def save_worker(self, dialog, first_name, last_name, email, work_study, availability, use_firebase=True):
        if not first_name or not last_name or not email:
            QMessageBox.warning(dialog, "Warning",
                                "First name, last name, and email are required.")
            return
        
        try:
            # Check if email already exists - in Firebase if enabled, otherwise in Excel
            duplicate_found = False
            
            if self.firebase_enabled and use_firebase:
                # Check for duplicates in Firebase
                existing_workers = fb_get_workers(self.workplace)
                duplicate_found = any(w.get('email') == email for w in existing_workers)
                
                if duplicate_found:
                    QMessageBox.warning(dialog, "Warning", 
                                     "A worker with this email already exists in Firebase.")
                    return
            
            # Save to Firebase if enabled and selected
            saved_to_firebase = False
            if self.firebase_enabled and use_firebase:
                # Parse availability
                parsed_avail = parse_availability(availability)
                
                # Create worker data
                worker_data = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "work_study": work_study.lower() in ['yes', 'y', 'true'],
                    "availability": parsed_avail,
                    "availability_text": availability
                }
                
                # Save to Firebase
                if fb_save_worker(self.workplace, worker_data):
                    saved_to_firebase = True
                    logging.info(f"Worker {email} saved to Firebase")
                else:
                    logging.error(f"Failed to save worker {email} to Firebase")
            
            # Always save to Excel unless Firebase save was successful
            if not saved_to_firebase:
                path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
                if os.path.exists(path):
                    df = pd.read_excel(path)
                    df.columns = df.columns.str.strip()
                    df = df.dropna(subset=['Email'], how='all')
                    df = df[df['Email'].str.strip() != '']
                    df = df[~df['Email'].str.contains('nan', case=False, na=False)]
                    
                    # Check for duplicates again in Excel
                    if email in df['Email'].values:
                        QMessageBox.warning(dialog, "Warning", "Worker already exists in Excel file.")
                        return
                        
                    new = {
                        "First Name": first_name,
                        "Last Name": last_name,
                        "Email": email,
                        "Work Study": work_study
                    }
                    col = next((c for c in df.columns if 'available' in c.lower()), None)
                    if col:
                        new[col] = availability
                    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                else:
                    cols = ["First Name","Last Name","Email","Work Study","Days & Times Available"]
                    df = pd.DataFrame(columns=cols)
                    new = {
                        "First Name": first_name,
                        "Last Name": last_name,
                        "Email": email,
                        "Work Study": work_study,
                        "Days & Times Available": availability
                    }
                    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                df.to_excel(path, index=False)
            
            # Reload workers table
            self.load_workers_table()
            dialog.accept()
            
            if saved_to_firebase:
                QMessageBox.information(self, "Success", "Worker added successfully to Firebase.")
            else:
                QMessageBox.information(self, "Success", "Worker added successfully to Excel file.")
                
        except Exception as e:
            logging.error(f"Error saving worker: {e}")
            QMessageBox.critical(dialog, "Error", f"Error saving worker: {e}")

    def edit_worker_dialog(self, row, email, worker_id=None):
        # Try to get worker data from Firebase first if ID is provided
        if self.firebase_enabled and worker_id:
            try:
                # Get worker data from Firebase
                workers = fb_get_workers(self.workplace)
                worker_data = next((w for w in workers if w.get('id') == worker_id), None)
                
                if worker_data:
                    dialog = QDialog(self)
                    dialog.setWindowTitle("Edit Worker")
                    dialog.setMinimumWidth(500)
                    layout = QVBoxLayout(dialog)
                    
                    form = QFormLayout()
                    fn = QLineEdit(worker_data.get("first_name", "")); form.addRow("First Name:", fn)
                    ln = QLineEdit(worker_data.get("last_name", "")); form.addRow("Last Name:", ln)
                    em = QLineEdit(worker_data.get("email", "")); em.setReadOnly(True); form.addRow("Email:", em)
                    ws = QComboBox(); ws.addItems(["No", "Yes"])
                    ws.setCurrentText("Yes" if worker_data.get("work_study", False) else "No")
                    form.addRow("Work Study:", ws)
                    
                    # Format availability from object to string for editing
                    avail_text = worker_data.get("availability_text", "")
                    if not avail_text:
                        avail = worker_data.get("availability", {})
                        avail_text = ""
                        for day, times in avail.items():
                            for time_range in times:
                                if avail_text:
                                    avail_text += ", "
                                avail_text += f"{day} {time_range['start']}-{time_range['end']}"
                    
                    avail = QTextEdit(avail_text)
                    avail.setMinimumHeight(100)
                    form.addRow("Availability:", avail)
                    
                    # Add Firebase option
                    use_firebase = QCheckBox("Update in Firebase")
                    use_firebase.setChecked(True)
                    form.addRow("", use_firebase)
                    
                    layout.addLayout(form)
                    
                    btns = QHBoxLayout()
                    save = StyleHelper.create_button("Save")
                    cancel = StyleHelper.create_button("Cancel", primary=False)
                    btns.addWidget(save); btns.addWidget(cancel)
                    layout.addLayout(btns)
                    
                    save.clicked.connect(lambda: self.update_worker_firebase(
                        dialog, worker_id, fn.text(), ln.text(),
                        ws.currentText(), avail.toPlainText(),
                        use_firebase.isChecked()
                    ))
                    cancel.clicked.connect(dialog.reject)
                    
                    dialog.exec_()
                    return
            except Exception as e:
                logging.error(f"Error getting worker from Firebase: {e}")
                # Fall back to Excel method
        
        # If Firebase failed or disabled, use Excel method
        path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
        if not os.path.exists(path):
            QMessageBox.warning(self, "Warning", "Excel file not found.")
            return
        try:
            df = pd.read_excel(path); df.columns = df.columns.str.strip()
            wr = df[df['Email']==email]
            if wr.empty:
                QMessageBox.warning(self, "Warning", "Worker not found.")
                return
            wr = wr.iloc[0]
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Worker")
            dialog.setMinimumWidth(500)
            layout = QVBoxLayout(dialog)

            form = QFormLayout()
            fn = QLineEdit(wr.get("First Name","")); form.addRow("First Name:", fn)
            ln = QLineEdit(wr.get("Last Name",""));  form.addRow("Last Name:", ln)
            em = QLineEdit(wr.get("Email","")); em.setReadOnly(True); form.addRow("Email:", em)
            ws = QComboBox(); ws.addItems(["No","Yes"])
            ws.setCurrentText(str(wr.get("Work Study","No")))
            form.addRow("Work Study:", ws)
            col = next((c for c in df.columns if 'available' in c.lower()), None)
            avail = QTextEdit(str(wr[col]) if col else "")
            avail.setMinimumHeight(100)
            form.addRow("Availability:", avail)
            
            # Add Firebase option if enabled
            if self.firebase_enabled:
                use_firebase = QCheckBox("Also save to Firebase")
                use_firebase.setChecked(True)
                form.addRow("", use_firebase)
            else:
                use_firebase = None
                
            layout.addLayout(form)

            btns = QHBoxLayout()
            save = StyleHelper.create_button("Save")
            cancel = StyleHelper.create_button("Cancel", primary=False)
            btns.addWidget(save); btns.addWidget(cancel)
            layout.addLayout(btns)

            save.clicked.connect(lambda: self.update_worker(
                dialog, email, fn.text(), ln.text(),
                ws.currentText(), avail.toPlainText(),
                use_firebase.isChecked() if use_firebase else False
            ))
            cancel.clicked.connect(dialog.reject)

            dialog.exec_()

        except Exception as e:
            logging.error(f"Error editing worker: {e}")
            QMessageBox.critical(self, "Error", f"Error editing worker: {e}")

    def update_worker_firebase(self, dialog, worker_id, first_name, last_name, work_study, availability, use_firebase=True):
        """Update worker in Firebase"""
        if not first_name or not last_name:
            QMessageBox.warning(dialog, "Warning", "First and last name are required.")
            return
        
        try:
            # Get the email from Firebase
            email = None
            if use_firebase:
                workers = fb_get_workers(self.workplace)
                worker = next((w for w in workers if w.get('id') == worker_id), None)
                if worker:
                    email = worker.get('email')
            
            # Update in Firebase if enabled and selected
            firebase_success = False
            if use_firebase and self.firebase_enabled:
                parsed_avail = parse_availability(availability)
                worker_data = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "work_study": work_study.lower() in ['yes', 'y', 'true'],
                    "availability": parsed_avail,
                    "availability_text": availability,
                    "id": worker_id
                }
                
                if fb_save_worker(self.workplace, worker_data):
                    firebase_success = True
                    logging.info(f"Worker {worker_id} updated in Firebase")
                else:
                    logging.error(f"Failed to update worker {worker_id} in Firebase")
            
            # Also update Excel file if email was found
            excel_success = False
            if email:
                path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
                if os.path.exists(path):
                    df = pd.read_excel(path)
                    df.columns = df.columns.str.strip()
                    
                    # Find the worker in Excel by email
                    mask = df['Email'] == email
                    if mask.any():
                        df.loc[mask, "First Name"] = first_name
                        df.loc[mask, "Last Name"] = last_name
                        df.loc[mask, "Work Study"] = work_study
                        
                        # Update availability column
                        col = next((c for c in df.columns if 'available' in c.lower()), None)
                        if col:
                            df.loc[mask, col] = availability
                            
                        df.to_excel(path, index=False)
                        excel_success = True
                        logging.info(f"Worker {email} updated in Excel")
            
            # Reload workers table
            self.load_workers_table()
            dialog.accept()
            
            # Show result message
            if firebase_success and excel_success:
                QMessageBox.information(self, "Success", "Worker updated in both Firebase and Excel.")
            elif firebase_success:
                QMessageBox.information(self, "Success", "Worker updated in Firebase only.")
            elif excel_success:
                QMessageBox.information(self, "Success", "Worker updated in Excel only.")
            else:
                QMessageBox.warning(self, "Warning", "Failed to update worker.")
            
        except Exception as e:
            logging.error(f"Error updating worker in Firebase: {e}")
            QMessageBox.critical(dialog, "Error", f"Error updating worker: {e}")

    def update_worker(self, dialog, email, first_name, last_name, work_study, availability, use_firebase=False):
        if not first_name or not last_name:
            QMessageBox.warning(dialog, "Warning", "First and last name are required.")
            return
        try:
            # Update Excel file
            excel_success = False
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            if os.path.exists(path):
                df = pd.read_excel(path); df.columns = df.columns.str.strip()
                mask = df['Email']==email
                if not mask.any():
                    QMessageBox.warning(dialog, "Warning", "Worker not found in Excel file.")
                else:
                    df.loc[mask,"First Name"] = first_name
                    df.loc[mask,"Last Name"]  = last_name
                    df.loc[mask,"Work Study"]  = work_study
                    col = next((c for c in df.columns if 'available' in c.lower()), None)
                    if col:
                        df.loc[mask,col] = availability
                    df.to_excel(path, index=False)
                    excel_success = True
            
            # Update in Firebase if enabled and selected
            firebase_success = False
            if use_firebase and self.firebase_enabled:
                # Find worker by email in Firebase
                workers = fb_get_workers(self.workplace)
                worker = next((w for w in workers if w.get('email') == email), None)
                
                if worker:
                    worker_id = worker.get('id')
                    parsed_avail = parse_availability(availability)
                    
                    worker_data = {
                        "first_name": first_name,
                        "last_name": last_name,
                        "email": email,
                        "work_study": work_study.lower() in ['yes', 'y', 'true'],
                        "availability": parsed_avail,
                        "availability_text": availability,
                        "id": worker_id
                    }
                    
                    if fb_save_worker(self.workplace, worker_data):
                        firebase_success = True
                        logging.info(f"Worker {email} updated in Firebase")
                    else:
                        logging.error(f"Failed to update worker {email} in Firebase")
                else:
                    # Worker not in Firebase, ask if user wants to add
                    reply = QMessageBox.question(
                        dialog, "Add to Firebase?",
                        "Worker not found in Firebase. Would you like to add this worker to Firebase?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    
                    if reply == QMessageBox.Yes:
                        # Add worker to Firebase
                        parsed_avail = parse_availability(availability)
                        
                        worker_data = {
                            "first_name": first_name,
                            "last_name": last_name,
                            "email": email,
                            "work_study": work_study.lower() in ['yes', 'y', 'true'],
                            "availability": parsed_avail,
                            "availability_text": availability
                        }
                        
                        if fb_save_worker(self.workplace, worker_data):
                            firebase_success = True
                            logging.info(f"Worker {email} added to Firebase")
                        else:
                            logging.error(f"Failed to add worker {email} to Firebase")
            
            # Reload workers table
            self.load_workers_table()
            dialog.accept()
            
            # Show result message
            if firebase_success and excel_success:
                QMessageBox.information(self, "Success", "Worker updated in both Excel and Firebase.")
            elif firebase_success:
                QMessageBox.information(self, "Success", "Worker updated in Firebase only.")
            elif excel_success:
                QMessageBox.information(self, "Success", "Worker updated in Excel file.")
            else:
                QMessageBox.warning(self, "Warning", "Failed to update worker.")
                
        except Exception as e:
            logging.error(f"Error updating worker: {e}")
            QMessageBox.critical(dialog, "Error", f"Error updating worker: {e}")

    def delete_worker(self, email, worker_id=None):
        """Delete a worker by email or ID."""
        reply = QMessageBox.question(
            self, "Delete Worker?",
            "Are you sure you want to delete this worker?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            # Create progress dialog
            progress = QProgressDialog("Deleting worker...", "Cancel", 0, 100, self)
            progress.setWindowTitle("Deleting Worker")
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(10)
            
            # Delete from Firebase if enabled and ID is provided
            firebase_success = False
            if self.firebase_enabled:
                try:
                    progress.setValue(30)
                    progress.setLabelText("Deleting from Firebase...")
                    
                    # If we have worker_id, use it directly
                    if worker_id:
                        firebase_success = fb_delete_worker(self.workplace, worker_id)
                    else:
                        # If not, find by email
                        workers = fb_get_workers(self.workplace)
                        worker = next((w for w in workers if w.get('email') == email), None)
                        if worker:
                            worker_id = worker.get('id')
                            if worker_id:
                                firebase_success = fb_delete_worker(self.workplace, worker_id)
                    
                    if firebase_success:
                        logging.info(f"Worker {email} deleted from Firebase")
                    else:
                        logging.warning(f"Failed to delete worker {email} from Firebase")
                        
                except Exception as e:
                    logging.error(f"Error deleting worker from Firebase: {e}")
            
            # Delete from Excel file
            progress.setValue(60)
            progress.setLabelText("Deleting from Excel file...")
            
            excel_success = False
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            if os.path.exists(path):
                df = pd.read_excel(path)
                df.columns = df.columns.str.strip()
                if email in df['Email'].values:
                    df = df[df['Email'] != email]
                    df.to_excel(path, index=False)
                    excel_success = True
                    logging.info(f"Worker {email} deleted from Excel file")
                else:
                    logging.warning(f"Worker {email} not found in Excel file")
            
            # Reload workers table
            progress.setValue(90)
            progress.setLabelText("Refreshing worker list...")
            
            self.load_workers_table()
            
            # Show result message
            progress.setValue(100)
            
            if firebase_success and excel_success:
                QMessageBox.information(self, "Success", "Worker deleted from both Firebase and Excel.")
            elif firebase_success:
                QMessageBox.information(self, "Success", "Worker deleted from Firebase only.")
            elif excel_success:
                QMessageBox.information(self, "Success", "Worker deleted from Excel file only.")
            else:
                QMessageBox.warning(self, "Warning", "Worker not found in either Firebase or Excel.")
                
        except Exception as e:
            logging.error(f"Error deleting worker: {e}")
            QMessageBox.critical(self, "Error", f"Error deleting worker: {e}")

    def remove_all_workers(self):
        """Delete every worker in this workplace after a BIG confirmation."""
        reply = QMessageBox.question(
            self, "⚠️ Remove ALL Workers?",
            "This will permanently delete *every* worker in this workplace.\n"
            "Are you ABSOLUTELY sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            # Handle Firebase deletion if enabled
            firebase_deleted = False
            if self.firebase_enabled:
                fb_reply = QMessageBox.question(
                    self, "Delete from Firebase?",
                    "Do you also want to delete all workers from Firebase?\n"
                    "WARNING: This will completely remove the workers collection!",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if fb_reply == QMessageBox.Yes:
                    # Create progress dialog
                    progress = QProgressDialog("Deleting from Firebase...", "Cancel", 0, 100, self)
                    progress.setWindowTitle("Firebase Delete")
                    progress.setWindowModality(Qt.WindowModal)
                    progress.setValue(10)
                    
                    try:
                        # Use the data manager to remove all workers
                        progress.setValue(30)
                        progress.setLabelText("Removing workers from Firebase...")
                        
                        self.data_manager.current_workplace_id = self.workplace
                        result = self.data_manager.remove_all_workers()
                        
                        if result:
                            firebase_deleted = True
                            progress.setValue(100)
                            QMessageBox.information(self, "Success", 
                                                "Successfully deleted all workers from Firebase.")
                        else:
                            progress.setValue(100)
                            QMessageBox.warning(self, "Warning", 
                                             "Some workers may remain in Firebase.")
                            
                    except Exception as e:
                        logging.error(f"Error removing workers from Firebase: {e}")
                        progress.setValue(100)
                        QMessageBox.critical(self, "Firebase Error", 
                                        f"Could not remove workers from Firebase:\n{e}")
            
            # Always delete from Excel file
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            if os.path.exists(path):
                df = pd.read_excel(path)
                cols = df.columns.tolist()
                empty = pd.DataFrame(columns=cols)
                empty.to_excel(path, index=False)
            
            # Reload table to reflect changes
            self.load_workers_table()
            
            if not firebase_deleted:
                QMessageBox.information(self, "Local Workers Removed",
                                    "Workers have been removed from local storage only.")
                                    
        except Exception as e:
            logging.error(f"Error removing all workers: {e}")
            QMessageBox.critical(self, "Error",
                             f"Could not remove workers:\n{e}")

    def manage_hours(self):
        # Try to get hours from Firebase first if enabled
        hours = {}
        if self.firebase_enabled:
            try:
                hours = self.data_manager.get_hours_of_operation()
            except Exception as e:
                logging.error(f"Error getting hours from Firebase: {e}")
                # Fall back to app_data
        
        # If Firebase failed or is disabled, use app_data
        if not hours:
            hours = self.app_data.get(self.workplace, {}).get('hours_of_operation', {})
        
        dialog = HoursOfOperationDialog(self.workplace, hours, self)
        if dialog.exec_() == QDialog.Accepted:
            # Save to both Firebase and local app_data
            success = True
            if self.firebase_enabled:
                try:
                    success = self.data_manager.update_hours_of_operation(dialog.hours_data)
                except Exception as e:
                    logging.error(f"Error saving hours to Firebase: {e}")
                    success = False
            
            # Always save to local app_data as backup
            data = load_data()
            data.setdefault(self.workplace, {})['hours_of_operation'] = dialog.hours_data
            if save_data(data):
                self.app_data = data
                self.load_hours_table()
                QMessageBox.information(self, "Success", "Hours saved successfully.")
            else:
                QMessageBox.critical(self, "Error", "Error saving hours.")

    def generate_schedule(self):
        path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
        
        # Check if we have workers - either from Firebase or Excel
        workers_exist = False
        if self.firebase_enabled:
            firebase_workers = fb_get_workers(self.workplace)
            if firebase_workers:
                workers_exist = True
        
        if not workers_exist and not os.path.exists(path):
            QMessageBox.warning(self, "Warning", "No workers found. Add workers first.")
            return
            
        # Check for hours of operation
        hours_op = None
        if self.firebase_enabled:
            hours_op = self.data_manager.get_hours_of_operation()
        
        if not hours_op:
            if self.workplace not in self.app_data or not self.app_data[self.workplace].get('hours_of_operation'):
                QMessageBox.warning(self, "Warning", "Define hours of operation first.")
                return
            hours_op = self.app_data[self.workplace]['hours_of_operation']

        dialog = QDialog(self)
        dialog.setWindowTitle("Generate Schedule")
        dialog.setMinimumWidth(400)
        L = QVBoxLayout(dialog)
        form = QFormLayout()
        max_hours   = QSpinBox(); max_hours.setRange(1,40); max_hours.setValue(20)
        max_workers = QSpinBox(); max_workers.setRange(1,10); max_workers.setValue(1)
        form.addRow("Max Hours Per Worker:",   max_hours)
        form.addRow("Max Workers Per Shift:", max_workers)
        L.addLayout(form)

        btns = QHBoxLayout()
        gen_btn = StyleHelper.create_button("Generate")
        cancel  = StyleHelper.create_button("Cancel", primary=False)
        btns.addWidget(gen_btn); btns.addWidget(cancel)
        L.addLayout(btns)

        gen_btn.clicked.connect(lambda: self.do_generate_schedule(
            dialog, max_hours.value(), max_workers.value(), hours_op
        ))
        cancel.clicked.connect(dialog.reject)
        dialog.exec_()

    def do_generate_schedule(self, dialog, max_hours_per_worker, max_workers_per_shift, hours_op=None):
        try:
            # Initialize progress dialog
            progress = QProgressDialog("Generating schedule...", "Cancel", 0, 100, self)
            progress.setWindowTitle("Please Wait")
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(10)
            
            # Try to get workers from Firebase first if enabled
            workers = []
            if self.firebase_enabled:
                try:
                    firebase_workers = fb_get_workers(self.workplace)
                    if firebase_workers:
                        for worker in firebase_workers:
                            workers.append({
                                "first_name": worker.get("first_name", "").strip(),
                                "last_name": worker.get("last_name", "").strip(),
                                "email": worker.get("email", "").strip(),
                                "work_study": worker.get("work_study", False),
                                "availability": worker.get("availability", {})
                            })
                        progress.setValue(30)
                except Exception as e:
                    logging.error(f"Error getting workers from Firebase: {e}")
                    # Fall back to Excel
            
            # If Firebase failed or had no workers, use Excel
            if not workers:
                path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
                df = pd.read_excel(path); df.columns = df.columns.str.strip()
                df = df.dropna(subset=['Email'], how='all')
                df = df[df['Email'].str.strip() != '']
                df = df[~df['Email'].str.contains('nan', case=False, na=False)]

                col = next((c for c in df.columns if 'available' in c.lower()), None)
                for _, r in df.iterrows():
                    text = str(r.get(col,"")) if col else ""
                    if pd.isna(text) or text=="nan":
                        text = ""
                    workers.append({
                        "first_name": r.get("First Name","").strip(),
                        "last_name":  r.get("Last Name","").strip(),
                        "email":      r.get("Email","").strip(),
                        "work_study": str(r.get("Work Study","")).strip().lower() in ['yes','y','true'],
                        "availability": parse_availability(text)
                    })
                progress.setValue(30)
            
            # Get hours of operation - should have been passed in, but fallback if not
            if not hours_op:
                if self.firebase_enabled:
                    hours_op = self.data_manager.get_hours_of_operation()
                if not hours_op:
                    hours_op = self.app_data[self.workplace]['hours_of_operation']
            
            progress.setValue(50)
            
            # Generate schedule
            schedule, assigned_hours, low_hours, unassigned, alt_sols, unfilled, ws_issues = \
                create_shifts_from_availability(
                    hours_op, workers,
                    self.workplace,
                    max_hours_per_worker,
                    max_workers_per_shift
                )
            
            progress.setValue(80)
            
            # If schedule generation was successful
            dialog.accept()
            progress.setValue(100)
            progress.close()

            # Show alternative solutions dialog if needed
            if unfilled or ws_issues:
                alt = AlternativeSolutionsDialog(alt_sols, unfilled, ws_issues, self)
                alt.exec_()

            # Show schedule dialog
            self.show_schedule_dialog(
                schedule,
                assigned_hours,
                low_hours,
                unassigned,
                workers,
                max_per_shift=max_workers_per_shift,
                max_hours_per_worker=max_hours_per_worker
            )

        except Exception as e:
            logging.error(f"Error generating schedule: {e}")
            QMessageBox.critical(dialog, "Error", f"Error generating schedule: {e}")

    def view_current_schedule(self):
        # Try to get schedule from Firebase first if enabled
        firebase_schedule = None
        if self.firebase_enabled:
            try:
                schedules = self.data_manager.get_schedules()
                # Find the most recent schedule
                if schedules:
                    firebase_schedule = max(
                        schedules, 
                        key=lambda s: s.get('created_at', '2000-01-01')
                    )
                    
                    # If the schedule data is in the 'days' field, extract it
                    if 'days' in firebase_schedule and isinstance(firebase_schedule['days'], dict):
                        firebase_schedule = firebase_schedule['days']
            except Exception as e:
                logging.error(f"Error getting schedule from Firebase: {e}")
                # Fall back to file
        
        # If Firebase failed or is disabled, use local file
        if not firebase_schedule:
            path = os.path.join(DIRS['saved_schedules'], f"{self.workplace}_current.json")
            if not os.path.exists(path):
                QMessageBox.warning(self, "Warning", "No saved schedule found.")
                return
            try:
                with open(path, "r") as f:
                    schedule = json.load(f)
            except Exception as e:
                logging.error(f"Error loading schedule from file: {e}")
                QMessageBox.critical(self, "Error", f"Error loading schedule: {e}")
                return
        else:
            schedule = firebase_schedule
            
        try:
            # Get workers for displaying schedule
            workers = self.get_workers()
            
            # Calculate hours for each worker
            assigned_hours = {}
            for day, shifts in schedule.items():
                for s in shifts:
                    sh = time_to_hour(s['start'])
                    eh = time_to_hour(s['end'])
                    for em in s.get('raw_assigned', []):
                        assigned_hours[em] = assigned_hours.get(em,0)+(eh-sh)

            # Identify workers with low hours or no hours
            unassigned = [
                f"{w['first_name']} {w['last_name']}"
                for w in workers
                if assigned_hours.get(w['email'],0)==0
            ]
            low = [
                f"{w['first_name']} {w['last_name']}"
                for w in workers
                if 0<assigned_hours.get(w['email'],0)<4
            ]
            
            # Show schedule dialog
            self.show_schedule_dialog(
                schedule,
                assigned_hours,
                low,
                unassigned,
                workers,
                max_per_shift=1,
                max_hours_per_worker=0
            )
        except Exception as e:
            logging.error(f"Error viewing schedule: {e}")
            QMessageBox.critical(self, "Error", f"Error viewing schedule: {e}")

    def show_schedule_dialog(self,
                             schedule, assigned_hours, low_hours, unassigned,
                             all_workers=None, max_per_shift=1,
                             max_hours_per_worker=0):
        """
        Build a tab per day plus an "All" tab:
        left = tabbed `QTableWidget`
        below = worker-hours summary
        """
        dialog = QDialog(self)
        dialog.max_per_shift = max_per_shift
        dialog.setWindowTitle("Generated Schedule")
        dialog.setMinimumSize(1000,700)
        L = QVBoxLayout(dialog)
        tabs = QTabWidget()

        # collect rows
        all_rows = []
        day_tables = {}
        for day in DAYS:
            rows = []
            for idx, s in enumerate(schedule.get(day, [])):
                rows.append((day, s['start'], s['end'], ", ".join(s['assigned']), idx))
                all_rows.append((day, s['start'], s['end'], ", ".join(s['assigned']), idx))
            day_tables[day] = rows

        def build_table(rows):
            tbl = QTableWidget()
            tbl.setColumnCount(5)
            tbl.setHorizontalHeaderLabels(["Day","Start","End","Assigned","Actions"])
            tbl.setRowCount(len(rows))
            for i, (d, st, en, assigned, orig_idx) in enumerate(rows):
                itm = QTableWidgetItem(d)
                itm.setFlags(itm.flags() & ~Qt.ItemIsEditable)
                tbl.setItem(i,0,itm)
                s_it = QTableWidgetItem(format_time_ampm(st))
                tbl.setItem(i,1,s_it)
                e_it = QTableWidgetItem(format_time_ampm(en))
                tbl.setItem(i,2,e_it)
                a_it = QTableWidgetItem(assigned)
                if "Unfilled" in assigned:
                    a_it.setBackground(QColor(255,200,200))
                a_it.setFlags(a_it.flags() & ~Qt.ItemIsEditable)
                tbl.setItem(i,3,a_it)
                # actions
                ew = QWidget(); ewl = QHBoxLayout(ew); ewl.setContentsMargins(0,0,0,0)
                btn = QPushButton("Edit"); btn.setMinimumWidth(80)
                btn.setStyleSheet("background-color:#ffc107; padding:6px;")
                def make_cb(day, idx, row_idx, table):
                    return lambda: self.edit_shift_assignment(
                        day,
                        schedule[day][idx],
                        row_idx,
                        table,
                        all_workers,
                        dialog
                    )
                btn.clicked.connect(make_cb(d, orig_idx, i, tbl))
                ewl.addWidget(btn); ewl.addStretch()
                tbl.setCellWidget(i,4,ew)
            tbl.resizeColumnsToContents()
            tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            return tbl

        # add each day tab
        for day in DAYS:
            tabs.addTab(build_table(day_tables[day]), day)
        # All
        tabs.addTab(build_table(all_rows), "All")

        L.addWidget(tabs)

        # worker hours summary
        hrs_tbl = QTableWidget(); hrs_tbl.setColumnCount(3)
        hrs_tbl.setHorizontalHeaderLabels(["Worker","Hours","Status"])
        sorted_ws = sorted(assigned_hours.items(), key=lambda x: x[1], reverse=True)
        emails = {w['email'] for w in (all_workers or [])}
        for em in emails:
            if em not in assigned_hours:
                sorted_ws.append((em,0))
        hrs_tbl.setRowCount(len(sorted_ws))
        for i,(em,h) in enumerate(sorted_ws):
            name = em
            for w in all_workers or []:
                if w['email'] == em:
                    name = f"{w['first_name']} {w['last_name']}"
                    break
            itm = QTableWidgetItem(name); hrs_tbl.setItem(i,0, itm)
            hi = QTableWidgetItem(f"{h:.1f}")
            if h == 0:
                hi.setBackground(QColor(255,200,200))
            elif h < 4:
                hi.setBackground(QColor(255,255,200))
            hrs_tbl.setItem(i,1, hi)
            if h == 0:
                st = QTableWidgetItem("Unassigned"); st.setBackground(QColor(255,200,200))
            elif h < 4:
                st = QTableWidgetItem("Low Hours");  st.setBackground(QColor(255,255,200))
            else:
                st = QTableWidgetItem("OK")
            hrs_tbl.setItem(i,2, st)
        hrs_tbl.resizeColumnsToContents()
        if low_hours:
            lbl=QLabel(f"Workers <4h: {', '.join(low_hours)}")
            lbl.setStyleSheet("color:red;")
            L.addWidget(lbl)
        if unassigned:
            lbl=QLabel(f"No hours: {', '.join(unassigned)}")
            lbl.setStyleSheet("color:red;font-weight:bold;")
            L.addWidget(lbl)
        L.addWidget(hrs_tbl)

        dialog.hours_table = hrs_tbl
        
        dialog.schedule       = schedule
        dialog.assigned_hours = assigned_hours
        dialog.all_workers    = all_workers

        # bottom buttons
        btm = QHBoxLayout()
        save  = StyleHelper.create_button("Save Schedule")
        email = StyleHelper.create_button("Email Schedule")
        prnt  = StyleHelper.create_button("Print Schedule")
        close = StyleHelper.create_button("Close", primary=False)
        override_btn = StyleHelper.create_button("Override Shifts")
        
        # Add Firebase save button if Firebase is enabled
        if self.firebase_enabled:
            save_fb = StyleHelper.create_button("Save to Firebase")
            save_fb.setStyleSheet("background-color: #28a745; color: white;")
            save_fb.clicked.connect(lambda: self.save_schedule_to_firebase(dialog, schedule))
            btm.addWidget(save_fb)
        
        for b in (save, email, prnt, close, override_btn):
            btm.addWidget(b)
        L.addLayout(btm)

        save.clicked.connect(lambda: self.save_schedule(dialog, schedule))
        email.clicked.connect(lambda: self.email_schedule_dialog(schedule))
        prnt.clicked.connect(lambda: self.print_schedule(schedule))
        close.clicked.connect(dialog.reject)
        override_btn.clicked.connect(lambda: ShiftOverrideDialog(
            dialog.schedule,
            dialog.assigned_hours,
            all_workers,
            max_hours_per_worker,
            max_per_shift,
            dialog
        ).exec_())

        dialog.exec_()

    def _on_time_edited(self, item, schedule, dialog, tbl):
        col = item.column()
        if col not in (1,2):
            return
        new_txt = item.text().strip()
        try:
            dt = datetime.strptime(new_txt, "%I:%M %p")
        except:
            QMessageBox.warning(self, "Invalid Time",
                                "Please enter time as H:MM AM/PM")
            return
        hr = dt.hour + dt.minute/60
        row = item.row()
        day = tbl.item(row,0).text()
        idx = 0
        for d in DAYS:
            if d == day:
                idx += [tbl.item(r,0).text() for r in range(row)].count(day)
                break
            idx += len(schedule.get(d, []))
        shift = schedule[day][idx]
        key = 'start' if col==1 else 'end'
        shift[key] = f"{dt.hour:02d}:{dt.minute:02d}"
        item.setText(format_time_ampm(shift[key]))
        self.update_worker_hours_tab(dialog, dialog.hours_table)

    def update_worker_hours_tab(self, dialog, hrs_tbl):
        assigned = {w['email']: 0 for w in dialog.all_workers}
        for day, shifts in dialog.schedule.items():
            for s in shifts:
                sh = time_to_hour(s['start'])
                eh = time_to_hour(s['end'])
                dur = eh - sh
                for em in s.get('raw_assigned', []):
                    assigned[em] = assigned.get(em,0) + dur

        sorted_ws = sorted(assigned.items(), key=lambda x: x[1], reverse=True)
        for i,(em,h) in enumerate(sorted_ws):
            if i >= hrs_tbl.rowCount():
                break
            name = em
            for w in self.get_workers():
                if w['email'] == em:
                    name = f"{w['first_name']} {w['last_name']}"
                    break
            hrs_tbl.item(i,0).setText(name)
            itm = hrs_tbl.item(i,1)
            itm.setText(f"{h:.1f}")
            if h == 0:
                itm.setBackground(QColor(255,200,200))
            elif h < 4:
                itm.setBackground(QColor(255,255,200))
            else:
                itm.setBackground(QColor(255,255,255))
            st = hrs_tbl.item(i,2)
            if h == 0:
                st.setText("Unassigned"); st.setBackground(QColor(255,200,200))
            elif h < 4:
                st.setText("Low Hours");  st.setBackground(QColor(255,255,200))
            else:
                st.setText("OK");         st.setBackground(QColor(255,255,255))
        dialog.assigned_hours = assigned

    def edit_shift_assignment(self, day, shift, row, table, all_workers, parent_dialog):
        if not all_workers:
            QMessageBox.warning(self, "Warning",
                                "No workers available to edit this shift.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(
            f"Edit Shift: {day} {format_time_ampm(shift['start'])}-{format_time_ampm(shift['end'])}"
        )
        dlg.setMinimumSize(500,500)
        L = QVBoxLayout(dlg)

        inst = QLabel(
            f"Select workers for {day} "
            f"{format_time_ampm(shift['start'])} - {format_time_ampm(shift['end'])}:"
        )
        inst.setStyleSheet("font-weight:bold; font-size:14px;")
        L.addWidget(inst)

        avail = shift.get('all_available', [])
        if not avail:
            msg = QLabel(
                "No workers are available during this time slot based on availability."
            )
            msg.setStyleSheet("color:red;")
            msg.setWordWrap(True)
            L.addWidget(msg)
            note = QLabel("Showing all workers; some may be unavailable.")
            note.setWordWrap(True)
            L.addWidget(note)
            avail = all_workers

        lst = QListWidget()
        lst.setStyleSheet("QListWidget::item { padding:5px; }")
        for w in avail:
            it = QListWidgetItem(f"{w['first_name']} {w['last_name']}")
            it.setData(Qt.UserRole, w)
            it.setCheckState(
                Qt.Checked if f"{w['first_name']} {w['last_name']}" in shift['assigned']
                else Qt.Unchecked
            )
            lst.setSelectionMode(QListWidget.NoSelection)
            lst.addItem(it)
        L.addWidget(lst)

        btns = QHBoxLayout()
        save   = StyleHelper.create_button("Save");   save.setMinimumWidth(120)
        cancel = StyleHelper.create_button("Cancel", primary=False); cancel.setMinimumWidth(120)
        btns.addWidget(save); btns.addWidget(cancel)
        L.addLayout(btns)

        save.clicked.connect(lambda: self.update_shift_assignment(
            dlg, day, shift, row, table, lst, parent_dialog
        ))
        cancel.clicked.connect(dlg.reject)

        dlg.exec_()

    def update_shift_assignment(self, dialog, day, shift, row, table, worker_list, parent_dialog):
        selected = []
        for i in range(worker_list.count()):
            it = worker_list.item(i)
            if it.checkState() == Qt.Checked:
                selected.append(it.data(Qt.UserRole))

        if len(selected) > parent_dialog.max_per_shift:
            QMessageBox.warning(
                dialog, "Too Many",
                f"Cannot assign more than {parent_dialog.max_per_shift} workers to a shift."
            )
            return

        shift['assigned']     = [f"{w['first_name']} {w['last_name']}" for w in selected] or ["Unfilled"]
        shift['raw_assigned'] = [w['email'] for w in selected] or []

        itm = QTableWidgetItem(", ".join(shift['assigned']))
        if "Unfilled" in shift['assigned']:
            itm.setBackground(QColor(255,200,200))
        table.setItem(row,3,itm)

        parent_dialog.schedule[day] = [
            s if s is not shift else shift
            for s in parent_dialog.schedule[day]
        ]
        self.update_worker_hours_tab(parent_dialog, parent_dialog.hours_table)

        dialog.accept()

    def get_workers(self):
        # Try Firebase first if enabled
        if self.firebase_enabled:
            try:
                firebase_workers = fb_get_workers(self.workplace)
                if firebase_workers:
                    ws = []
                    for worker in firebase_workers:
                        ws.append({
                            "first_name": worker.get("first_name", "").strip(),
                            "last_name": worker.get("last_name", "").strip(),
                            "email": worker.get("email", "").strip(),
                            "work_study": worker.get("work_study", False),
                            "availability": worker.get("availability", {})
                        })
                    return ws
            except Exception as e:
                logging.error(f"Error getting workers from Firebase: {e}")
                # Fall back to Excel method
        
        # If Firebase failed or is disabled, use Excel
        path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
        if not os.path.exists(path): return []
        try:
            df = pd.read_excel(path); df.columns = df.columns.str.strip()
            df = df.dropna(subset=['Email'], how='all')
            df = df[df['Email'].str.strip()!='']
            df = df[~df['Email'].str.contains('nan', case=False, na=False)]
            ws = []
            for _, r in df.iterrows():
                fn = r.get("First Name","").strip()
                ln = r.get("Last Name","").strip()
                em = r.get("Email","").strip()
                if not em or em=="nan": continue
                wk = str(r.get("Work Study","")).strip().lower() in ['yes','y','true']
                
                # Get availability if possible
                avail_col = next((c for c in df.columns if 'available' in c.lower()), None)
                avail_text = str(r.get(avail_col, "")) if avail_col else ""
                if pd.isna(avail_text) or avail_text == "nan":
                    avail_text = ""
                    
                parsed_avail = parse_availability(avail_text)
                
                ws.append({
                    "first_name": fn,
                    "last_name": ln,
                    "email": em,
                    "work_study": wk,
                    "availability": parsed_avail,
                    "availability_text": avail_text
                })
            return ws
        except Exception as e:
            logging.error(f"Error getting workers from Excel: {e}")
            return []

    def get_workers_from_table(self):
        """Get workers data from the UI table"""
        workers = []
        
        # Loop through rows in the table
        for row in range(self.workers_table.rowCount()):
            # Get data from columns
            first_name = self.workers_table.item(row, 0)
            last_name = self.workers_table.item(row, 1)
            email = self.workers_table.item(row, 2)
            work_study = self.workers_table.item(row, 3)
            availability = self.workers_table.item(row, 4)
            
            # Validate required fields
            if (first_name and last_name and email and 
                first_name.text().strip() and 
                last_name.text().strip() and 
                email.text().strip()):
                
                # Parse availability
                avail_text = availability.text() if availability else ""
                parsed_avail = parse_availability(avail_text)
                
                # Create worker data
                worker_data = {
                    "first_name": first_name.text().strip(),
                    "last_name": last_name.text().strip(),
                    "email": email.text().strip(),
                    "work_study": (work_study.text().strip().lower() in ['yes', 'y', 'true'] 
                                  if work_study else False),
                    "availability": parsed_avail,
                    "availability_text": avail_text
                }
                
                workers.append(worker_data)
        
        return workers

    def save_schedule(self, dialog, schedule):
        try:
            jp = os.path.join(DIRS['saved_schedules'], f"{self.workplace}_current.json")
            with open(jp,"w") as f:
                json.dump(schedule, f, indent=4)

            xp = os.path.join(DIRS['saved_schedules'], f"{self.workplace}_current.xlsx")
            with pd.ExcelWriter(xp, engine='openpyxl') as writer:
                for day in DAYS:
                    shifts = schedule.get(day, [])
                    if not shifts: continue
                    rows = [{
                        "Start":    format_time_ampm(s['start']),
                        "End":      format_time_ampm(s['end']),
                        "Assigned": ", ".join(s['assigned'])
                    } for s in shifts]
                    pd.DataFrame(rows).to_excel(writer, sheet_name=day, index=False)
                all_rows = []
                for day, shifts in schedule.items():
                    for s in shifts:
                        all_rows.append({
                            "Day":      day,
                            "Start":    format_time_ampm(s['start']),
                            "End":      format_time_ampm(s['end']),
                            "Assigned": ", ".join(s['assigned'])
                        })
                if all_rows:
                    pd.DataFrame(all_rows).to_excel(writer, sheet_name="Full Schedule", index=False)

            QMessageBox.information(dialog, "Success", f"Schedule saved to:\n{xp}")

        except Exception as e:
            logging.error(f"Error saving schedule: {e}")
            QMessageBox.critical(dialog, "Error", f"Error saving schedule: {e}")

    def save_schedule_to_firebase(self, dialog, schedule):
        """Save schedule to Firebase"""
        if not self.firebase_enabled:
            QMessageBox.warning(self, "Warning", "Firebase is not enabled.")
            return
            
        try:
            # Format schedule for Firebase
            firebase_schedule = {
                "days": schedule,
                "created_at": datetime.now().isoformat(),
                "workplace_id": self.workplace,
                "name": f"{self.workplace} Schedule {datetime.now().strftime('%Y-%m-%d')}"
            }
            
            # Save to Firebase
            result = self.data_manager.save_schedule(firebase_schedule)
            
            if result:
                QMessageBox.information(dialog, "Success", "Schedule saved to Firebase successfully.")
            else:
                QMessageBox.warning(dialog, "Warning", "Failed to save schedule to Firebase.")
                
        except Exception as e:
            logging.error(f"Error saving schedule to Firebase: {e}")
            QMessageBox.critical(dialog, "Error", f"Error saving schedule to Firebase: {e}")

    def email_schedule_dialog(self, schedule):
        dialog = QDialog(self)
        dialog.setWindowTitle("Email Schedule")
        dialog.setMinimumWidth(400)
        L = QVBoxLayout(dialog)

        form = QFormLayout()
        sender = QLineEdit(); form.addRow("Sender Email:", sender)
        pwd = QLineEdit(); pwd.setEchoMode(QLineEdit.Password)
        form.addRow("Sender Password:", pwd)
        note = QLabel(
            "Note: Gmail may require an App Password under your Google Account Security settings."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-style:italic;color:#666;")
        form.addRow("", note)

        rcpt = QTextEdit()
        for w in self.get_workers():
            if w['email']:
                rcpt.append(w['email'])
        form.addRow("Recipients:", rcpt)
        L.addLayout(form)

        btns = QHBoxLayout()
        send   = StyleHelper.create_button("Send")
        cancel = StyleHelper.create_button("Cancel", primary=False)
        btns.addWidget(send); btns.addWidget(cancel)
        L.addLayout(btns)

        send.clicked.connect(lambda: self.send_schedule_email(
            dialog, schedule, sender.text(),
            pwd.text(), rcpt.toPlainText().splitlines()
        ))
        cancel.clicked.connect(dialog.reject)

        dialog.exec_()

    def send_schedule_email(self, dialog, schedule,
                            sender_email, sender_password, recipients):
        if not sender_email or not sender_password or not recipients:
            QMessageBox.warning(
                dialog, "Warning",
                "Sender email, password, and recipients are required."
            )
            return
        try:
            success, msg = send_schedule_email(
                self.workplace, schedule, recipients,
                sender_email, sender_password
            )
            if success:
                QMessageBox.information(dialog, "Success", msg)
                dialog.accept()
            else:
                QMessageBox.critical(dialog, "Error", msg)
        except Exception as e:
            logging.error(f"Error sending email: {e}")
            QMessageBox.critical(dialog, "Error", f"Error sending email: {e}")

    def print_schedule(self, schedule):
        try:
            printer = QPrinter()
            dlg = QPrintDialog(printer, self)
            if dlg.exec_() != QDialog.Accepted:
                return
            doc = QTextDocument()
            html = f"<html><body><h1>{self.workplace.replace('_',' ').title()} Schedule</h1>"
            for day in DAYS:
                if schedule.get(day):
                    html += f"<h2>{day}</h2><table border='1'><tr><th>Start</th><th>End</th><th>Assigned</th></tr>"
                    for s in schedule[day]:
                        cls = ' style="color:red;"' if "Unfilled" in s['assigned'] else ""
                        html += (
                            f"<tr><td>{format_time_ampm(s['start'])}</td>"
                            f"<td>{format_time_ampm(s['end'])}</td>"
                            f"<td{cls}>{', '.join(s['assigned'])}</td></tr>"
                        )
                    html += "</table>"
            html += "</body></html>"
            doc.setHtml(html)
            doc.print_(printer)
            QMessageBox.information(self, "Success", "Schedule sent to printer.")
        except Exception as e:
            logging.error(f"Error printing schedule: {e}")
            QMessageBox.critical(self, "Error", f"Error printing schedule: {e}")

    def show_last_minute_dialog(self):
        dlg = LastMinuteAvailabilityDialog(self.workplace, self)
        dlg.exec_()
        
    def sync_with_firebase(self):
        """Sync data with Firebase for this workplace"""
        if not self.firebase_enabled:
            QMessageBox.warning(self, "Firebase Not Enabled", 
                             "Firebase connection is not available. Please connect first.")
            return False
            
        try:
            # Create progress dialog
            progress = QProgressDialog("Syncing with Firebase...", "Cancel", 0, 100, self)
            progress.setWindowTitle("Firebase Sync")
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(10)
            
            # Load workplace data
            if self.data_manager.load_workplace(self.workplace):
                progress.setValue(50)
                
                # Update UI with Firebase data
                self.load_workers_table()
                progress.setValue(75)
                
                self.load_hours_table()
                progress.setValue(100)
                
                # Close progress dialog after a short delay
                QTimer.singleShot(500, progress.close)
                
                QMessageBox.information(self, "Sync Complete", 
                                    f"Successfully synced data for {self.workplace}.")
                return True
                
            progress.close()
            QMessageBox.warning(self, "Sync Failed", 
                             f"Failed to load workplace data for {self.workplace}.")
            return False
            
        except Exception as e:
            logging.error(f"Error syncing with Firebase: {e}")
            QMessageBox.critical(self, "Error", f"Error syncing with Firebase: {e}")
            return False
    
    def export_workers_to_firebase(self):
        """Export workers from Excel to Firebase"""
        if not self.firebase_enabled:
            QMessageBox.warning(self, "Firebase Not Enabled", 
                             "Firebase connection is not available. Please connect first.")
            return
        
        try:
            # First try to export directly from the UI table
            workers = self.get_workers_from_table()
            
            if not workers:
                # Fall back to Excel if UI table is empty
                path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
                if not os.path.exists(path):
                    QMessageBox.warning(self, "No Excel File", 
                                     "No Excel file found for this workplace.")
                    return
                    
                # Read Excel file
                df = pd.read_excel(path)
                df.columns = df.columns.str.strip()
                df = df.dropna(subset=['Email'], how='all')
                df = df[df['Email'].str.strip() != '']
                df = df[~df['Email'].str.contains('nan', case=False, na=False)]
                
                if len(df) == 0:
                    QMessageBox.warning(self, "No Workers", 
                                     "No valid workers found in Excel file.")
                    return
                
                # Create progress dialog
                progress = QProgressDialog("Exporting workers to Firebase...", "Cancel", 0, len(df), self)
                progress.setWindowTitle("Firebase Export")
                progress.setWindowModality(Qt.WindowModal)
                
                # Export each worker
                success_count = 0
                for i, row in df.iterrows():
                    if progress.wasCanceled():
                        break
                        
                    progress.setValue(i)
                    progress.setLabelText(f"Exporting {row.get('First Name', '')} {row.get('Last Name', '')}...")
                    
                    fn = row.get("First Name", "").strip()
                    ln = row.get("Last Name", "").strip()
                    em = row.get("Email", "").strip()
                    ws = str(row.get("Work Study", "")).strip().lower() in ['yes', 'y', 'true']
                    
                    # Get availability
                    avail_col = next((c for c in df.columns if 'available' in c.lower()), None)
                    avail_text = str(row.get(avail_col, "")) if avail_col else ""
                    if pd.isna(avail_text) or avail_text == "nan":
                        avail_text = ""
                    
                    parsed_avail = parse_availability(avail_text)
                    
                    # Create worker data
                    worker_data = {
                        "first_name": fn,
                        "last_name": ln,
                        "email": em,
                        "work_study": ws,
                        "availability": parsed_avail,
                        "availability_text": avail_text
                    }
                    
                    # Save to Firebase
                    if fb_save_worker(self.workplace, worker_data):
                        success_count += 1
            else:
                # Export workers from UI table
                progress = QProgressDialog("Exporting workers to Firebase...", "Cancel", 0, len(workers), self)
                progress.setWindowTitle("Firebase Export")
                progress.setWindowModality(Qt.WindowModal)
                
                # Export each worker
                success_count = 0
                for i, worker in enumerate(workers):
                    if progress.wasCanceled():
                        break
                        
                    progress.setValue(i)
                    progress.setLabelText(f"Exporting {worker.get('first_name', '')} {worker.get('last_name', '')}...")
                    
                    # Save to Firebase
                    if fb_save_worker(self.workplace, worker):
                        success_count += 1
            
            progress.setValue(len(workers))
            
            # Show results
            QMessageBox.information(self, "Export Complete", 
                                 f"Successfully exported {success_count} workers to Firebase.")
            
            # Reload workers table
            self.load_workers_table()
            
        except Exception as e:
            logging.error(f"Error exporting workers to Firebase: {e}")
            QMessageBox.critical(self, "Error", f"Error exporting workers to Firebase: {e}")
    
    def import_workers_from_firebase(self):
        """Import workers from Firebase to Excel"""
        if not self.firebase_enabled:
            QMessageBox.warning(self, "Firebase Not Enabled", 
                             "Firebase connection is not available. Please connect first.")
            return
        
        try:
            # Get workers from Firebase
            firebase_workers = fb_get_workers(self.workplace)
            
            if not firebase_workers:
                QMessageBox.warning(self, "No Workers", 
                                 "No workers found in Firebase for this workplace.")
                return
            
            # Create DataFrame
            rows = []
            for worker in firebase_workers:
                # Format availability from object to string
                avail = worker.get("availability_text", "")
                if not avail:
                    avail_obj = worker.get("availability", {})
                    for day, times in avail_obj.items():
                        for time_range in times:
                            if avail:
                                avail += ", "
                            avail += f"{day} {time_range['start']}-{time_range['end']}"
                
                rows.append({
                    "First Name": worker.get("first_name", ""),
                    "Last Name": worker.get("last_name", ""),
                    "Email": worker.get("email", ""),
                    "Work Study": "Yes" if worker.get("work_study", False) else "No",
                    "Days & Times Available": avail,
                    "firebase_id": worker.get("id", "")  # Store Firebase ID for future reference
                })
            
            df = pd.DataFrame(rows)
            
            # Save to Excel
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            df.to_excel(path, index=False)
            
            # Reload workers table
            self.load_workers_table()
            
            QMessageBox.information(self, "Import Complete", 
                                 f"Successfully imported {len(firebase_workers)} workers from Firebase.")
            
        except Exception as e:
            logging.error(f"Error importing workers from Firebase: {e}")
            QMessageBox.critical(self, "Error", f"Error importing workers from Firebase: {e}")
    
    def sync_hours_with_firebase(self):
        """Sync hours of operation with Firebase"""
        if not self.firebase_enabled:
            QMessageBox.warning(self, "Firebase Not Enabled", 
                             "Firebase connection is not available. Please connect first.")
            return
        
        try:
            # Get hours from Firebase
            hours = self.data_manager.get_hours_of_operation()
            
            if not hours:
                # If no hours in Firebase, ask if user wants to upload current hours
                reply = QMessageBox.question(
                    self, "No Hours Found",
                    "No hours of operation found in Firebase. Would you like to upload current hours?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    # Get hours from app_data
                    local_hours = self.app_data.get(self.workplace, {}).get('hours_of_operation', {})
                    
                    if not local_hours:
                        QMessageBox.warning(self, "No Hours Defined", 
                                         "No hours of operation defined locally either.")
                        return
                    
                    # Save to Firebase
                    if self.data_manager.update_hours_of_operation(local_hours):
                        QMessageBox.information(self, "Upload Complete", 
                                             "Successfully uploaded hours of operation to Firebase.")
                    else:
                        QMessageBox.warning(self, "Upload Failed", 
                                         "Failed to upload hours of operation to Firebase.")
                
                return
            
            # Update local app_data
            data = load_data()
            data.setdefault(self.workplace, {})['hours_of_operation'] = hours
            if save_data(data):
                self.app_data = data
                self.load_hours_table()
                QMessageBox.information(self, "Sync Complete", 
                                     "Successfully synced hours of operation from Firebase.")
            else:
                QMessageBox.warning(self, "Sync Failed", 
                                 "Failed to save hours of operation locally.")
            
        except Exception as e:
            logging.error(f"Error syncing hours with Firebase: {e}")
            QMessageBox.critical(self, "Error", f"Error syncing hours with Firebase: {e}")
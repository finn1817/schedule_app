# schedule_app/ui/hours_of_operation_dialog.py

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFormLayout, QMessageBox, QTimeEdit,
    QProgressDialog, QCheckBox
)
from PyQt5.QtCore import QTime, Qt
from core.data import load_data, save_data, get_data_manager
from core.config import DAYS, firebase_available
from .style_helper import StyleHelper

class HoursOfOperationDialog(QDialog):
    """Single-window hours-of-operation for each day."""
    def __init__(self, workplace, hours_data, parent=None):
        super().__init__(parent)
        self.workplace = workplace
        # hours_data: {day: [ {start, end}, ... ] }
        # we only take the first block if present
        self.hours_data = hours_data or {}
        self.day_widgets = {}
        self.data_manager = get_data_manager()
        self.firebase_available = firebase_available()
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"Hours of Operation - {self.workplace.replace('_',' ').title()}")
        self.setMinimumSize(500, 600)
        layout = QVBoxLayout(self)

        # Firebase indicator if available
        if self.firebase_available:
            firebase_indicator = QLabel("✅ Changes will be saved to Firebase")
            firebase_indicator.setStyleSheet("color: #28a745; font-weight: bold;")
            layout.addWidget(firebase_indicator)
        else:
            firebase_indicator = QLabel("❌ Firebase not available - changes will be saved locally only")
            firebase_indicator.setStyleSheet("color: #dc3545; font-weight: bold;")
            layout.addWidget(firebase_indicator)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        sl = QVBoxLayout(content)
        sl.setContentsMargins(0,0,0,0)

        for day in DAYS:
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(4,4,4,4)

            lbl = QLabel(day)
            lbl.setFixedWidth(80)
            hl.addWidget(lbl)

            start_edit = QTimeEdit()
            # switch to 12-hour display with AM/PM
            start_edit.setDisplayFormat("h:mm AP")
            end_edit   = QTimeEdit()
            end_edit.setDisplayFormat("h:mm AP")

            # populate existing if any
            blocks = self.hours_data.get(day, [])
            if blocks:
                b = blocks[0]
                st = QTime.fromString(b['start'], "HH:mm")
                en = QTime.fromString(b['end'],   "HH:mm")
                if st.isValid(): start_edit.setTime(st)
                if en.isValid(): end_edit.setTime(en)

            hl.addWidget(QLabel("Start:"))
            hl.addWidget(start_edit)
            hl.addWidget(QLabel("End:"))
            hl.addWidget(end_edit)
            hl.addStretch()

            sl.addWidget(row)
            self.day_widgets[day] = (start_edit, end_edit)

        content.setLayout(sl)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Add checkbox for Firebase save if available
        if self.firebase_available:
            self.use_firebase_checkbox = QCheckBox("Save to Firebase")
            self.use_firebase_checkbox.setChecked(True)
            layout.addWidget(self.use_firebase_checkbox)

        btns = QHBoxLayout()
        btns.addStretch()
        save = StyleHelper.create_button("Save")
        cancel = StyleHelper.create_button("Cancel", primary=False)
        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        save.clicked.connect(self.save_hours)
        cancel.clicked.connect(self.reject)

    def save_hours(self):
        new = {}
        for day, (st, en) in self.day_widgets.items():
            new[day] = [{
                "start": st.time().toString("HH:mm"),
                "end":   en.time().toString("HH:mm")
            }]

        # Show progress dialog
        progress = QProgressDialog("Saving hours of operation...", None, 0, 100, self)
        progress.setWindowTitle("Saving")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(10)
        progress.show()

        save_to_firebase = self.firebase_available and (
            hasattr(self, 'use_firebase_checkbox') and self.use_firebase_checkbox.isChecked()
        )

        # Save to Firebase if enabled and selected
        firebase_success = False
        if save_to_firebase:
            progress.setValue(30)
            progress.setLabelText("Saving to Firebase...")
            
            try:
                # Make sure the data manager is using the correct workplace
                self.data_manager.current_workplace_id = self.workplace
                
                # Update hours of operation in Firebase
                firebase_success = self.data_manager.update_hours_of_operation(new)
                
                if firebase_success:
                    progress.setValue(60)
                    progress.setLabelText("Successfully saved to Firebase")
                else:
                    progress.setValue(60)
                    progress.setLabelText("Failed to save to Firebase, saving locally...")
            except Exception as e:
                import logging
                logging.error(f"Error saving hours to Firebase: {e}")
                progress.setValue(60)
                progress.setLabelText("Error saving to Firebase, saving locally...")
                firebase_success = False
        
        # Always save locally as backup
        progress.setValue(70)
        progress.setLabelText("Saving locally...")
        
        data = load_data()
        data.setdefault(self.workplace, {})['hours_of_operation'] = new
        local_success = save_data(data)
        
        progress.setValue(100)
        
        # Check results and show appropriate message
        if local_success or firebase_success:
            self.hours_data = new
            
            if firebase_success and local_success:
                QMessageBox.information(self, "Success", "Hours saved successfully to both Firebase and local storage.")
            elif firebase_success:
                QMessageBox.information(self, "Partial Success", "Hours saved to Firebase but failed to save locally.")
            elif local_success:
                if save_to_firebase:
                    QMessageBox.warning(self, "Partial Success", "Hours saved locally but failed to save to Firebase.")
                else:
                    QMessageBox.information(self, "Success", "Hours saved locally.")
            
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to save hours to disk or Firebase.")
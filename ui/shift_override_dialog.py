# schedule_app/ui/shift_override_dialog.py

from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QListWidget, QPushButton, QFormLayout,
    QComboBox, QTimeEdit, QMessageBox, QCheckBox, QProgressDialog
)
from PyQt5.QtCore import Qt
from core.parser import time_to_hour, format_time_ampm
from core.scheduler import is_worker_available, hour_to_time_str
from core.config import DAYS, firebase_available
from core.data import get_data_manager
import logging

logger = logging.getLogger(__name__)

class ShiftOverrideDialog(QDialog):
    """
    A dialog that lets the admin manually add or reassign shifts,
    viewing the live schedule on the left and availability on the right.
    """
    def __init__(self, schedule, assigned_hours, all_workers,
                 max_hours_per_worker, max_per_shift, parent=None):
        super().__init__(parent)
        self.schedule             = schedule
        self.assigned_hours       = assigned_hours
        self.all_workers          = all_workers
        self.max_hours_per_worker = max_hours_per_worker
        self.max_per_shift        = max_per_shift
        self.data_manager         = get_data_manager()
        self.firebase_available   = firebase_available()
        self.parent_dialog        = parent
        
        self.setWindowTitle("Manual Shift Override")
        self.resize(900, 600)
        self._build_ui()
        self._populate_schedule()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Firebase indicator if available
        if self.firebase_available:
            firebase_indicator = QLabel("✅ Firebase Connected - Changes can be saved to Firebase")
            firebase_indicator.setStyleSheet("color: #28a745; font-weight: bold;")
            main_layout.addWidget(firebase_indicator)

        # Top: schedule table + availability list
        top_layout = QHBoxLayout()

        # -- schedule table
        self.sch_table = QTableWidget()
        self.sch_table.setColumnCount(4)
        self.sch_table.setHorizontalHeaderLabels(
            ["Day", "Start", "End", "Assigned"]
        )
        self.sch_table.verticalHeader().setVisible(False)
        self.sch_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sch_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sch_table.setSelectionMode(QTableWidget.SingleSelection)
        self.sch_table.itemSelectionChanged.connect(self._on_row_selected)
        top_layout.addWidget(self.sch_table, stretch=3)

        # -- availability list
        avail_layout = QVBoxLayout()
        avail_layout.addWidget(QLabel("Availability for Selected Shift:"))
        self.avail_list = QListWidget()
        avail_layout.addWidget(self.avail_list, stretch=1)
        top_layout.addLayout(avail_layout, stretch=1)

        main_layout.addLayout(top_layout)

        # Bottom: form to add a new shift
        form = QFormLayout()
        self.day_cb   = QComboBox()
        self.day_cb.addItems(DAYS)
        self.start_te = QTimeEdit()
        self.start_te.setDisplayFormat("HH:mm")
        self.end_te   = QTimeEdit()
        self.end_te.setDisplayFormat("HH:mm")

        form.addRow("Day:",        self.day_cb)
        form.addRow("Start Time:", self.start_te)
        form.addRow("End   Time:", self.end_te)
        main_layout.addLayout(form)

        # Add Firebase checkbox if available
        if self.firebase_available:
            self.save_to_firebase = QCheckBox("Save schedule to Firebase when closing")
            self.save_to_firebase.setChecked(True)
            main_layout.addWidget(self.save_to_firebase)

        # Buttons
        btn_layout = QHBoxLayout()
        add_btn   = QPushButton("Add Shift")
        self.save_btn = QPushButton("Save Changes")
        close_btn = QPushButton("Close")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

        add_btn.clicked.connect(self._on_add_shift)
        self.save_btn.clicked.connect(self._on_save_changes)
        close_btn.clicked.connect(self.close)
        
        # Style save button
        self.save_btn.setStyleSheet("background-color: #28a745; color: white;")

    def _populate_schedule(self):
        """
        Clear and refill the schedule table, rebuilding the row→(day, index) map.
        """
        self.sch_table.clearContents()
        self.sch_table.setRowCount(0)
        self._row_map = []

        rows = []
        for day in DAYS:
            for idx, shift in enumerate(self.schedule.get(day, [])):
                rows.append((
                    day,
                    shift['start'],
                    shift['end'],
                    ", ".join(shift['assigned'])
                ))
                self._row_map.append((day, idx))

        self.sch_table.setRowCount(len(rows))
        for i, (day, s, e, assigned) in enumerate(rows):
            self.sch_table.setItem(i, 0, QTableWidgetItem(day))
            self.sch_table.setItem(i, 1,
                QTableWidgetItem(format_time_ampm(s))
            )
            self.sch_table.setItem(i, 2,
                QTableWidgetItem(format_time_ampm(e))
            )
            itm = QTableWidgetItem(assigned)
            itm.setFlags(itm.flags() & ~Qt.ItemIsEditable)
            self.sch_table.setItem(i, 3, itm)

        self.sch_table.resizeColumnsToContents()

    def _on_row_selected(self):
        """
        Show which workers are available for the selected shift.
        """
        self.avail_list.clear()
        sel = self.sch_table.currentRow()
        if sel < 0 or sel >= len(self._row_map):
            return

        day, idx = self._row_map[sel]
        shift = self.schedule[day][idx]
        s_h = time_to_hour(shift['start'])
        e_h = time_to_hour(shift['end'])

        for w in self.all_workers:
            name  = f"{w['first_name']} {w['last_name']}"
            avail = is_worker_available(w, day, s_h, e_h)
            mark  = "✔️" if avail else "✖️"
            self.avail_list.addItem(f"{name} — {mark}")

    def _on_add_shift(self):
        """
        Validate and insert a brand-new shift, up to max_per_shift workers.
        NO longer gating by prior assigned_hours—just checks actual availability.
        """
        day   = self.day_cb.currentText()
        start = self.start_te.time().toString("HH:mm")
        end   = self.end_te.time().toString("HH:mm")
        s_h   = time_to_hour(start)
        e_h   = time_to_hour(end)
        if e_h <= s_h:
            QMessageBox.warning(self, "Invalid Times",
                                "End time must be after start time.")
            return

        # --- HERE'S THE FIX: only check is_worker_available, drop the hours cap ---
        elig = [
            w for w in self.all_workers
            if is_worker_available(w, day, s_h, e_h)
        ]

        if not elig:
            QMessageBox.information(self, "No One Available",
                                    "No workers can cover that time slot.")
            return

        # pick up to max_per_shift
        chosen = elig[: self.max_per_shift]
        for w in chosen:
            em = w['email']
            self.assigned_hours[em] = self.assigned_hours.get(em, 0) + (e_h - s_h)
            self.schedule.setdefault(day, []).append({
                "start":         hour_to_time_str(s_h),
                "end":           hour_to_time_str(e_h),
                "assigned":      [f"{w['first_name']} {w['last_name']}"],
                "available":     [f"{x['first_name']} {x['last_name']}" for x in elig],
                "raw_assigned":  [em],
                "all_available": elig
            })

        # fill any leftover slots as Unfilled
        for _ in range(self.max_per_shift - len(chosen)):
            self.schedule.setdefault(day, []).append({
                "start":         hour_to_time_str(s_h),
                "end":           hour_to_time_str(e_h),
                "assigned":      ["Unfilled"],
                "available":     [f"{x['first_name']} {x['last_name']}" for x in elig],
                "raw_assigned":  [],
                "all_available": elig
            })

        self._populate_schedule()
        QMessageBox.information(
            self, "Shift Added",
            f"Added shift on {day} {format_time_ampm(start)} – {format_time_ampm(end)}"
        )
        
        # Update parent dialog if available
        if hasattr(self.parent_dialog, 'update_worker_hours_tab') and hasattr(self.parent_dialog, 'hours_table'):
            self.parent_dialog.update_worker_hours_tab(self.parent_dialog, self.parent_dialog.hours_table)

    def _on_save_changes(self):
        """Save current schedule to both local storage and Firebase if enabled"""
        try:
            # Show progress dialog
            progress = QProgressDialog("Saving schedule changes...", None, 0, 100, self)
            progress.setWindowTitle("Saving")
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(10)
            progress.show()
            
            # Save locally
            progress.setValue(30)
            progress.setLabelText("Saving locally...")
            
            # Save to local storage
            import os
            import json
            from core.config import DIRS
            import pandas as pd
            
            # Determine current workplace from parent dialog or use fallback
            workplace = None
            if hasattr(self.parent_dialog, 'workplace'):
                workplace = self.parent_dialog.workplace
            elif hasattr(self.data_manager, 'current_workplace_id'):
                workplace = self.data_manager.current_workplace_id
            
            if workplace:
                # Save JSON
                jp = os.path.join(DIRS['saved_schedules'], f"{workplace}_current.json")
                with open(jp, "w") as f:
                    json.dump(self.schedule, f, indent=4)
                
                # Save Excel
                progress.setValue(50)
                progress.setLabelText("Creating Excel file...")
                
                xp = os.path.join(DIRS['saved_schedules'], f"{workplace}_current.xlsx")
                with pd.ExcelWriter(xp, engine='openpyxl') as writer:
                    for day in DAYS:
                        shifts = self.schedule.get(day, [])
                        if not shifts: continue
                        rows = [{
                            "Start":    format_time_ampm(s['start']),
                            "End":      format_time_ampm(s['end']),
                            "Assigned": ", ".join(s['assigned'])
                        } for s in shifts]
                        pd.DataFrame(rows).to_excel(writer, sheet_name=day, index=False)
                    
                    # All shifts in one sheet
                    all_rows = []
                    for day, shifts in self.schedule.items():
                        for s in shifts:
                            all_rows.append({
                                "Day":      day,
                                "Start":    format_time_ampm(s['start']),
                                "End":      format_time_ampm(s['end']),
                                "Assigned": ", ".join(s['assigned'])
                            })
                    if all_rows:
                        pd.DataFrame(all_rows).to_excel(writer, sheet_name="Full Schedule", index=False)
                
                # Save to Firebase if enabled and selected
                if self.firebase_available and hasattr(self, 'save_to_firebase') and self.save_to_firebase.isChecked():
                    progress.setValue(70)
                    progress.setLabelText("Saving to Firebase...")
                    
                    # Format schedule for Firebase
                    firebase_schedule = {
                        "days": self.schedule,
                        "created_at": self.data_manager.current_workplace_id,
                        "workplace_id": workplace,
                        "name": f"{workplace} Schedule (Override)"
                    }
                    
                    # Set the current workplace in data manager
                    self.data_manager.current_workplace_id = workplace
                    
                    # Save to Firebase
                    result = self.data_manager.save_schedule(firebase_schedule)
                    
                    progress.setValue(90)
                    
                    if result:
                        progress.setLabelText("Saved to Firebase successfully")
                    else:
                        progress.setLabelText("Failed to save to Firebase")
                
                progress.setValue(100)
                
                QMessageBox.information(self, "Success", "Schedule changes saved successfully.")
            else:
                progress.setValue(100)
                QMessageBox.warning(self, "Warning", "Couldn't determine workplace - only saved to memory")
        
        except Exception as e:
            logger.error(f"Error saving schedule changes: {e}")
            QMessageBox.critical(self, "Error", f"Error saving schedule: {str(e)}")
    
    def closeEvent(self, event):
        """Handle dialog close event"""
        # Ask if user wants to save changes if they haven't clicked Save button
        reply = QMessageBox.question(
            self, "Save Changes?",
            "Do you want to save your schedule changes before closing?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self._on_save_changes()
            event.accept()
        elif reply == QMessageBox.No:
            event.accept()
        else:
            event.ignore()
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
    QLineEdit, QTextEdit, QHeaderView, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from PyQt5.QtGui import QTextDocument

from core.config import DIRS, DAYS
from core.data import load_data, save_data
from core.parser import parse_availability, format_time_ampm, time_to_hour
from core.scheduler import create_shifts_from_availability
from core.exporter import send_schedule_email
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
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Title
        title = StyleHelper.create_section_title(
            self.workplace.replace('_',' ').title()
        )
        layout.addWidget(title)

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

        btn = StyleHelper.create_button("Edit Hours of Operation")
        btn.clicked.connect(self.manage_hours)
        L.addWidget(btn)

        self.tabs.addTab(tab, "Hours of Operation")

    def load_workers_table(self):
        self.workers_table.setRowCount(0)
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
            logging.error(f"Error loading workers: {e}")
            QMessageBox.critical(self, "Error", f"Error loading workers: {e}")

    def load_hours_table(self):
        self.hours_table.setRowCount(0)
        hours = self.app_data.get(self.workplace, {}).get('hours_of_operation', {})
        total = sum(len(v) for v in hours.values())
        self.hours_table.setRowCount(total)
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
        layout.addLayout(form)

        btns = QHBoxLayout()
        save = StyleHelper.create_button("Save")
        cancel = StyleHelper.create_button("Cancel", primary=False)
        btns.addWidget(save); btns.addWidget(cancel)
        layout.addLayout(btns)

        save.clicked.connect(lambda: self.save_worker(
            dialog, fn.text(), ln.text(), em.text(),
            ws.currentText(), avail.toPlainText()
        ))
        cancel.clicked.connect(dialog.reject)

        dialog.exec_()

    def save_worker(self, dialog, first_name, last_name, email, work_study, availability):
        if not first_name or not last_name or not email:
            QMessageBox.warning(dialog, "Warning",
                                "First name, last name, and email are required.")
            return
        try:
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            if os.path.exists(path):
                df = pd.read_excel(path); df.columns = df.columns.str.strip()
                df = df.dropna(subset=['Email'], how='all')
                df = df[df['Email'].str.strip() != '']
                df = df[~df['Email'].str.contains('nan', case=False, na=False)]
                if email in df['Email'].values:
                    QMessageBox.warning(dialog, "Warning", "Worker already exists.")
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
            self.load_workers_table()
            dialog.accept()
        except Exception as e:
            logging.error(f"Error saving worker: {e}")
            QMessageBox.critical(dialog, "Error", f"Error saving worker: {e}")

    def edit_worker_dialog(self, row, email):
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
            layout.addLayout(form)

            btns = QHBoxLayout()
            save = StyleHelper.create_button("Save")
            cancel = StyleHelper.create_button("Cancel", primary=False)
            btns.addWidget(save); btns.addWidget(cancel)
            layout.addLayout(btns)

            save.clicked.connect(lambda: self.update_worker(
                dialog, email, fn.text(), ln.text(),
                ws.currentText(), avail.toPlainText()
            ))
            cancel.clicked.connect(dialog.reject)

            dialog.exec_()

        except Exception as e:
            logging.error(f"Error editing worker: {e}")
            QMessageBox.critical(self, "Error", f"Error editing worker: {e}")

    def update_worker(self, dialog, email, first_name, last_name, work_study, availability):
        if not first_name or not last_name:
            QMessageBox.warning(dialog, "Warning", "First and last name are required.")
            return
        try:
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            df = pd.read_excel(path); df.columns = df.columns.str.strip()
            mask = df['Email']==email
            if not mask.any():
                QMessageBox.warning(dialog, "Warning", "Worker not found.")
                return
            df.loc[mask,"First Name"] = first_name
            df.loc[mask,"Last Name"]  = last_name
            df.loc[mask,"Work Study"]  = work_study
            col = next((c for c in df.columns if 'available' in c.lower()), None)
            if col:
                df.loc[mask,col] = availability
            df.to_excel(path, index=False)
            self.load_workers_table()
            dialog.accept()
        except Exception as e:
            logging.error(f"Error updating worker: {e}")
            QMessageBox.critical(dialog, "Error", f"Error updating worker: {e}")

    def delete_worker(self, email):
        confirm = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete the worker with email {email}?",
            QMessageBox.Yes|QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            df = pd.read_excel(path); df.columns = df.columns.str.strip()
            if email not in df['Email'].values:
                QMessageBox.warning(self, "Warning", "Worker not found.")
                return
            df = df[df['Email']!=email]
            df.to_excel(path, index=False)
            self.load_workers_table()
            QMessageBox.information(self, "Success", "Worker deleted successfully.")
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

        path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
        if os.path.exists(path):
            try:
                df = pd.read_excel(path)
                cols = df.columns.tolist()
                empty = pd.DataFrame(columns=cols)
                empty.to_excel(path, index=False)
                self.load_workers_table()
                QMessageBox.information(self, "All Workers Removed",
                                        "All workers have been removed.")
            except Exception as e:
                logging.error(f"Error removing all workers: {e}")
                QMessageBox.critical(self, "Error",
                                     f"Could not remove workers:\n{e}")
        else:
            QMessageBox.information(self, "No File",
                                    "No worker file found to clear.")

    def manage_hours(self):
        hours = self.app_data.get(self.workplace, {}).get('hours_of_operation', {})
        dialog = HoursOfOperationDialog(self.workplace, hours, self)
        if dialog.exec_() == QDialog.Accepted:
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
        if not os.path.exists(path):
            QMessageBox.warning(self, "Warning", "No Excel file found. Upload one first.")
            return
        if self.workplace not in self.app_data or not self.app_data[self.workplace].get('hours_of_operation'):
            QMessageBox.warning(self, "Warning", "Define hours of operation first.")
            return

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
            dialog, max_hours.value(), max_workers.value()
        ))
        cancel.clicked.connect(dialog.reject)
        dialog.exec_()

    def do_generate_schedule(self, dialog, max_hours_per_worker, max_workers_per_shift):
        try:
            path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
            df = pd.read_excel(path); df.columns = df.columns.str.strip()
            df = df.dropna(subset=['Email'], how='all')
            df = df[df['Email'].str.strip() != '']
            df = df[~df['Email'].str.contains('nan', case=False, na=False)]

            workers = []
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

            hours_op = self.app_data[self.workplace]['hours_of_operation']
            schedule, assigned_hours, low_hours, unassigned, alt_sols, unfilled, ws_issues = \
                create_shifts_from_availability(
                    hours_op, workers,
                    self.workplace,
                    max_hours_per_worker,
                    max_workers_per_shift
                )

            dialog.accept()

            if unfilled or ws_issues:
                alt = AlternativeSolutionsDialog(alt_sols, unfilled, ws_issues, self)
                alt.exec_()

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
        path = os.path.join(DIRS['saved_schedules'], f"{self.workplace}_current.json")
        if not os.path.exists(path):
            QMessageBox.warning(self, "Warning", "No saved schedule found.")
            return
        try:
            with open(path, "r") as f:
                schedule = json.load(f)
            workers = self.get_workers()
            assigned_hours = {}
            for day, shifts in schedule.items():
                for s in shifts:
                    sh = time_to_hour(s['start'])
                    eh = time_to_hour(s['end'])
                    for em in s.get('raw_assigned', []):
                        assigned_hours[em] = assigned_hours.get(em,0)+(eh-sh)

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
        # nothing changed here; full original logic applies
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
        # unchanged
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
        # unchanged
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
        # unchanged logic
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
        # unchanged
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
                ws.append({
                    "first_name": fn,
                    "last_name": ln,
                    "email": em,
                    "work_study": wk
                })
            return ws
        except Exception as e:
            logging.error(f"Error getting workers: {e}")
            return []

    def save_schedule(self, dialog, schedule):
        # unchanged
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

    def email_schedule_dialog(self, schedule):
        # unchanged
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
        # unchanged
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
        # unchanged
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
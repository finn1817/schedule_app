# schedule_app/ui/last_minute_availability_dialog.py

import os, logging, pandas as pd
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QFormLayout, QHBoxLayout,
    QComboBox, QTimeEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox
)
from PyQt5.QtCore import QTime
from .style_helper import StyleHelper
from core.config import DIRS
from core.parser import parse_availability, format_time_ampm

DAYS = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

class LastMinuteAvailabilityDialog(QDialog):
    def __init__(self, workplace, parent=None):
        super().__init__(parent)
        self.workplace = workplace
        self.workers = []
        self.initUI()
        self.loadWorkers()

    def initUI(self):
        self.setWindowTitle(f"Last Minute Availability - {self.workplace.replace('_',' ').title()}")
        self.setMinimumSize(700, 500)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Check Last Minute Availability"))

        form = QFormLayout()
        self.day = QComboBox(); self.day.addItems(DAYS)
        form.addRow("Day:", self.day)
        hl = QHBoxLayout()
        self.st = QTimeEdit(); self.st.setDisplayFormat("HH:mm"); self.st.setTime(QTime(9,0))
        self.et = QTimeEdit(); self.et.setDisplayFormat("HH:mm"); self.et.setTime(QTime(17,0))
        hl.addWidget(QLabel("Start:")); hl.addWidget(self.st)
        hl.addWidget(QLabel("End:")); hl.addWidget(self.et)
        form.addRow("Time:", hl)
        layout.addLayout(form)

        chk = StyleHelper.create_action_button("Check Availability")
        chk.clicked.connect(self.checkAvailability)
        layout.addWidget(chk)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(3)
        self.tbl.setHorizontalHeaderLabels(["Name","Email","Work Study"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tbl)

        layout.addWidget(StyleHelper.create_button("Close", primary=False))
        layout.itemAt(layout.count()-1).widget().clicked.connect(self.accept)

    def loadWorkers(self):
        path = os.path.join(DIRS['workplaces'], f"{self.workplace}.xlsx")
        if not os.path.exists(path):
            QMessageBox.warning(self, "Warning", "No Excel file found.")
            return
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip()
            df = df.dropna(subset=['Email'], how='all')
            df = df[df['Email'].str.strip()!='']
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
        except Exception as e:
            logging.error(f"Load workers: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def checkAvailability(self):
        day = self.day.currentText()
        st = self.st.time().toString("HH:mm")
        et = self.et.time().toString("HH:mm")
        avail = []
        for w in self.workers:
            for b in w['availability'].get(day, []):
                if b['start_hour'] <= int(st[:2]) and int(et[:2]) <= b['end_hour']:
                    avail.append(w)
                    break
        self.tbl.setRowCount(len(avail))
        for i, w in enumerate(avail):
            self.tbl.setItem(i,0,QTableWidgetItem(f"{w['first_name']} {w['last_name']}"))
            self.tbl.setItem(i,1,QTableWidgetItem(w['email']))
            self.tbl.setItem(i,2,QTableWidgetItem("Yes" if w['work_study'] else "No"))
        if not avail:
            QMessageBox.warning(self, "No Available Workers",
                f"No workers on {day} from {format_time_ampm(st)} to {format_time_ampm(et)}.")

# schedule_app/ui/hours_of_operation_dialog.py

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFormLayout, QMessageBox, QTimeEdit
)
from PyQt5.QtCore import QTime
from core.data import load_data, save_data
from core.config import DAYS
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
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"Hours of Operation - {self.workplace.replace('_',' ').title()}")
        self.setMinimumSize(500, 600)
        layout = QVBoxLayout(self)

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
        # persist into data file immediately
        data = load_data()
        data.setdefault(self.workplace, {})['hours_of_operation'] = new
        if not save_data(data):
            QMessageBox.critical(self, "Error", "Failed to save hours to disk.")
            return
        self.hours_data = new
        self.accept()

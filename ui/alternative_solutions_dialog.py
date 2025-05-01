# schedule_app/ui/alternative_solutions_dialog.py

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QGroupBox, QScrollArea,
    QWidget, QHBoxLayout, QPushButton
)
from core.parser import format_time_ampm
from .style_helper import StyleHelper

class AlternativeSolutionsDialog(QDialog):
    def __init__(self, alternative_solutions, unfilled_shifts, work_study_issues=None, parent=None):
        super().__init__(parent)
        self.alternative_solutions = alternative_solutions
        self.unfilled_shifts = unfilled_shifts
        self.work_study_issues = work_study_issues or []
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Schedule Suggestions")
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)

        title = QLabel("Suggestions for Unfilled Shifts")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        cl = QVBoxLayout(content)

        # Work‐study issues
        if self.work_study_issues:
            gb_ws = QGroupBox("Work Study Issues")
            gl_ws = QVBoxLayout(gb_ws)
            gl_ws.addWidget(QLabel("These students don't have exactly 5 hours:"))
            for w in self.work_study_issues:
                gl_ws.addWidget(QLabel(f"• {w}"))
            gl_ws.addWidget(QLabel("Suggestion: Adjust their shifts manually."))
            cl.addWidget(gb_ws)

        # Unfilled‐shifts suggestions
        if not self.unfilled_shifts:
            cl.addWidget(QLabel("All shifts are filled!"))
        else:
            for u in self.unfilled_shifts:
                day   = u['day']
                start = format_time_ampm(u['start'])
                end   = format_time_ampm(u['end'])
                gb = QGroupBox(f"{day} {start}–{end}")
                gl = QVBoxLayout(gb)
                key = f"{u['day']} {u['start']}-{u['end']}"
                sols = self.alternative_solutions.get(key, [])
                if sols:
                    gl.addWidget(QLabel("These workers could cover if hours increased:"))
                    for w in sols:
                        gl.addWidget(QLabel(f"• {w}"))
                    gl.addWidget(QLabel("Suggestion: Increase max hours or reassign."))
                else:
                    gl.addWidget(QLabel("No alternatives available."))
                    gl.addWidget(QLabel("Suggestion: Adjust hours or recruit more staff."))
                cl.addWidget(gb)

        content.setLayout(cl)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        close = StyleHelper.create_button("Close", primary=False)
        close.clicked.connect(self.accept)
        layout.addWidget(close)

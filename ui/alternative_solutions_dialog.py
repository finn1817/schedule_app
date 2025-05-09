# schedule_app/ui/alternative_solutions_dialog.py

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QGroupBox, QScrollArea,
    QWidget, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from core.parser import format_time_ampm
from core.config import firebase_available
from .style_helper import StyleHelper
import logging
import pandas as pd
import os

logger = logging.getLogger(__name__)

class AlternativeSolutionsDialog(QDialog):
    def __init__(self, alternative_solutions, unfilled_shifts, work_study_issues=None, parent=None):
        super().__init__(parent)
        self.alternative_solutions = alternative_solutions
        self.unfilled_shifts = unfilled_shifts
        self.work_study_issues = work_study_issues or []
        self.firebase_available = firebase_available()
        self.parent = parent
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Schedule Suggestions")
        self.setMinimumSize(800, 500)
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
            
            # Add more detailed heading
            gl_ws.addWidget(QLabel("Work study students with scheduling issues:"))
            
            # Create a table for work study issues
            ws_table = QTableWidget()
            ws_table.setColumnCount(2)
            ws_table.setHorizontalHeaderLabels(["Student", "Issue"])
            ws_table.setRowCount(len(self.work_study_issues))
            
            for i, student_issue in enumerate(self.work_study_issues):
                # Check if this contains an explicit issue message
                if ":" in student_issue:
                    student, issue = student_issue.split(":", 1)
                    ws_table.setItem(i, 0, QTableWidgetItem(student.strip()))
                    ws_table.setItem(i, 1, QTableWidgetItem(issue.strip()))
                else:
                    # Default case for backward compatibility
                    ws_table.setItem(i, 0, QTableWidgetItem(student_issue))
                    ws_table.setItem(i, 1, QTableWidgetItem("Adjust shifts to equal 5 hours total"))
            
            ws_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            gl_ws.addWidget(ws_table)
            
            # Add explanatory text
            note = QLabel("Work study students must have exactly 5 hours per week. Check their availability or adjust hours of operation.")
            note.setWordWrap(True)
            note.setStyleSheet("color: #dc3545; font-style: italic;")
            gl_ws.addWidget(note)
            
            cl.addWidget(gb_ws)

        # Unfilled‐shifts suggestions
        if not self.unfilled_shifts:
            all_filled = QLabel("🎉 All shifts are filled! No suggestions needed.")
            all_filled.setStyleSheet("font-size:14px; color:green; font-weight:bold;")
            cl.addWidget(all_filled)
        else:
            # Create a summary first
            summary = QLabel(f"Found {len(self.unfilled_shifts)} unfilled shifts that need attention.")
            summary.setStyleSheet("font-size:14px; color:#dc3545; font-weight:bold;")
            cl.addWidget(summary)
            
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
                    
                    # Create a table for potential workers
                    workers_table = QTableWidget()
                    workers_table.setColumnCount(2)
                    workers_table.setHorizontalHeaderLabels(["Worker", "Reason"])
                    workers_table.setRowCount(len(sols))
                    
                    for i, worker in enumerate(sols):
                        workers_table.setItem(i, 0, QTableWidgetItem(worker))
                        workers_table.setItem(i, 1, QTableWidgetItem("Exceeds max hours limit"))
                    
                    workers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                    gl.addWidget(workers_table)
                    
                    gl.addWidget(QLabel("Suggestion: Increase max hours or reassign shifts to balance workload."))
                else:
                    no_workers = QLabel("⚠️ No alternatives available for this shift.")
                    no_workers.setStyleSheet("color:#dc3545; font-weight:bold;")
                    gl.addWidget(no_workers)
                    gl.addWidget(QLabel("Suggestion: Adjust hours of operation or recruit more workers."))
                
                cl.addWidget(gb)

        content.setLayout(cl)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Button layout
        button_layout = QHBoxLayout()
        
        # Export button
        export_btn = StyleHelper.create_button("Export Suggestions")
        export_btn.clicked.connect(self.export_suggestions)
        button_layout.addWidget(export_btn)
        
        button_layout.addStretch()
        
        # Close button
        close = StyleHelper.create_button("Close", primary=False)
        close.clicked.connect(self.accept)
        button_layout.addWidget(close)
        
        layout.addLayout(button_layout)

    def export_suggestions(self):
        """Export suggestions to Excel file"""
        try:
            # Ask for save location
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Save Suggestions", 
                "", 
                "Excel Files (*.xlsx)"
            )
            
            if not file_path:
                return
                
            # Add .xlsx extension if not present
            if not file_path.lower().endswith('.xlsx'):
                file_path += '.xlsx'
            
            # Create Excel writer
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # Work study issues
                if self.work_study_issues:
                    ws_data = []
                    for student_issue in self.work_study_issues:
                        # Parse out the issue if it exists
                        if ":" in student_issue:
                            student, issue = student_issue.split(":", 1)
                            ws_data.append({
                                'Student': student.strip(),
                                'Issue': issue.strip(),
                                'Recommendation': 'Check availability or adjust schedule'
                            })
                        else:
                            ws_data.append({
                                'Student': student_issue,
                                'Issue': 'Does not have exactly 5 hours',
                                'Recommendation': 'Adjust shifts to equal 5 hours total'
                            })
                    
                    pd.DataFrame(ws_data).to_excel(
                        writer, 
                        sheet_name='Work Study Issues',
                        index=False
                    )
                
                # Unfilled shifts
                if self.unfilled_shifts:
                    shifts_data = []
                    for shift in self.unfilled_shifts:
                        day = shift['day']
                        start = format_time_ampm(shift['start'])
                        end = format_time_ampm(shift['end'])
                        key = f"{day} {shift['start']}-{shift['end']}"
                        
                        alternatives = self.alternative_solutions.get(key, [])
                        alternatives_str = ', '.join(alternatives) if alternatives else 'None'
                        
                        shifts_data.append({
                            'Day': day,
                            'Start Time': start,
                            'End Time': end,
                            'Potential Workers': alternatives_str,
                            'Suggestion': 'Increase max hours or find additional workers' if alternatives else 'Recruit more workers or adjust hours'
                        })
                    
                    pd.DataFrame(shifts_data).to_excel(
                        writer, 
                        sheet_name='Unfilled Shifts',
                        index=False
                    )
                
                # Summary sheet
                summary_data = [{
                    'Total Unfilled Shifts': len(self.unfilled_shifts),
                    'Total Work Study Issues': len(self.work_study_issues),
                    'Generated On': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
                }]
                
                pd.DataFrame(summary_data).to_excel(
                    writer,
                    sheet_name='Summary',
                    index=False
                )
            
            # Show success message
            QMessageBox.information(
                self,
                "Export Complete",
                f"Suggestions exported successfully to:\n{file_path}"
            )
            
        except Exception as e:
            logger.error(f"Error exporting suggestions: {e}")
            QMessageBox.critical(
                self, 
                "Export Error", 
                f"Failed to export suggestions: {str(e)}"
            )
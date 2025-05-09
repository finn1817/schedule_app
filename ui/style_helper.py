# schedule_app/ui/style_helper.py

from PyQt5.QtWidgets import QLabel, QPushButton, QTableWidget, QHeaderView, QAbstractItemView
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtCore import Qt

class StyleHelper:
    @staticmethod
    def get_main_style():
        return """
            QMainWindow, QDialog { 
                background-color: #f0f2f5;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                border-radius: 6px;
                background-color: white;
            }
            
            QTabBar::tab {
                background-color: #e9ecef;
                color: #495057;
                padding: 8px 16px;
                border: 1px solid #dee2e6;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                min-width: 100px;
                font-weight: 500;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 3px solid #007bff;
                color: #007bff;
                font-weight: bold;
            }
            
            QTabBar::tab:hover:!selected {
                background-color: #f8f9fa;
            }
            
            QLineEdit, QTextEdit, QComboBox {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px;
                background-color: white;
            }
            
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                border-color: #80bdff;
                outline: 0;
                box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
            }
            
            QGroupBox {
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: 600;
                background-color: white;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 3px;
                background-color: white;
            }
            
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """

    @staticmethod
    def create_section_title(text):
        label = QLabel(text)
        label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #212529;
            padding: 12px 0;
            margin-bottom: 10px;
        """)
        return label

    @staticmethod
    def create_button(text, primary=True, icon=None):
        """Create a styled button"""
        btn = QPushButton(text)
        
        if primary:
            style = """
                QPushButton {
                    background-color: #007bff;
                    color: white;
                    border: none;
                    padding: 12px 20px;
                    border-radius: 6px;
                    font-weight: bold;
                    min-height: 36px;
                }
                QPushButton:hover {
                    background-color: #0069d9;
                }
                QPushButton:pressed {
                    background-color: #0062cc;
                }
                QPushButton:disabled {
                    background-color: #b8daff;
                }
            """
        else:
            style = """
                QPushButton {
                    background-color: #6c757d;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                    min-height: 36px;
                }
                QPushButton:hover {
                    background-color: #5a6268;
                }
                QPushButton:pressed {
                    background-color: #545b62;
                }
                QPushButton:disabled {
                    background-color: #c8cccf;
                }
            """
        
        btn.setStyleSheet(style)
        
        if icon:
            btn.setIcon(QIcon(icon))
        
        return btn

    @staticmethod
    def create_action_button(text, icon=None):
        """Create a highlighted action button"""
        btn = QPushButton(text)
        style = """
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
            QPushButton:disabled {
                background-color: #a9e0b6;
            }
        """
        btn.setStyleSheet(style)
        
        if icon:
            btn.setIcon(QIcon(icon))
            
        return btn

    @staticmethod
    def style_table(table):
        """Apply modern styling to table widgets"""
        table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 0px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #e9ecef;
            }
            QTableWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QHeaderView::section {
                background-color: #343a40;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        """)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Make table read-only
        table.setShowGrid(False)  # Hide grid lines for a cleaner look

class ModernTableWidget(QTableWidget):
    """A modernized table widget with better styling and functionality"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        # Set modern styling
        self.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 0px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #e9ecef;
            }
            QTableWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QHeaderView::section {
                background-color: #343a40;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        """)
        
        # Hide vertical header (row numbers)
        self.verticalHeader().setVisible(False)
        
        # Set selection behavior
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        
        # Hide grid
        self.setShowGrid(False)
        
        # Alternating row colors
        self.setAlternatingRowColors(True)
        
        # Auto-stretch last section
        self.horizontalHeader().setStretchLastSection(True)
        
        # Set resize mode
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        
        # No editing by default
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
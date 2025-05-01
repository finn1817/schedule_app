# schedule_app/ui/style_helper.py

from PyQt5.QtWidgets import QLabel, QPushButton
from PyQt5.QtGui import QFont

class StyleHelper:
    @staticmethod
    def get_main_style():
        return """
            QMainWindow, QDialog { background-color: #f0f2f5; }
            /* ... rest of your stylesheet ... */
        """

    @staticmethod
    def create_section_title(text):
        label = QLabel(text)
        font = label.font()
        font.setPointSize(12)
        font.setBold(True)
        label.setFont(font)
        return label

    @staticmethod
    def create_button(text, primary=True):
        btn = QPushButton(text)
        if not primary:
            btn.setStyleSheet("background-color: #6c757d; color: white;")
        return btn

    @staticmethod
    def create_action_button(text):
        btn = QPushButton(text)
        btn.setStyleSheet("background-color: #28a745; color: white;")
        return btn

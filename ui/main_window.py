# schedule_app/ui/main_window.py

from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel
from PyQt5.QtGui import QFont
from .workplace_tab import WorkplaceTab
from .style_helper import StyleHelper

APP_NAME = "Workplace Scheduler"
APP_VERSION = "1.0.0"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(StyleHelper.get_main_style())

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch()
        version = QLabel(f"v{APP_VERSION}")
        header.addWidget(version)
        layout.addLayout(header)

        tabs = QTabWidget()
        tabs.addTab(WorkplaceTab("esports_lounge"),     "eSports Lounge")
        tabs.addTab(WorkplaceTab("esports_arena"),      "eSports Arena")
        tabs.addTab(WorkplaceTab("it_service_center"),  "IT Service Center")
        layout.addWidget(tabs)

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6 import uic

import sys
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from Site import FillButton, AddSiteWindow, SiteDisplay
from utils import get_project_root
import numpy as np

class main_app(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.qtdesignerfile = get_project_root() / 'ui' / 'CGSim.ui'
        self.Ui_MainWindow, _ = uic.loadUiType(self.qtdesignerfile)
        self.ui = self.Ui_MainWindow()
        self.ui.setupUi(self)
        self.current_widget = None  # track current widget
        self.add_site_window = None
        self.display_site_window = None

        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(50)
        glow.setColor(QColor(255, 99, 0))
        glow.setOffset(0)
        self.ui.dynamicFrame.setGraphicsEffect(glow)
        if self.ui.dynamicFrame.layout() is None:
            self.ui.dynamicFrame.setLayout(QVBoxLayout())

        glow2 = QGraphicsDropShadowEffect()
        glow2.setBlurRadius(50)
        glow2.setColor(QColor(148, 0, 211))
        glow2.setOffset(0)
        self.ui.dynamicFrame_2.setGraphicsEffect(glow2)
        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.inner = QWidget()
        self.scrollArea.setWidget(self.inner)
        framelayout = QVBoxLayout(self.ui.dynamicFrame_2)
        framelayout.addWidget(self.scrollArea)
        self.grid = QGridLayout(self.inner)
        self.grid.setSpacing(40)
        self.button_count = 0
        self.columns = 6
        self.button_size = 80

        glow3 = QGraphicsDropShadowEffect()
        glow3.setBlurRadius(50)
        glow3.setColor(QColor(144, 238, 144))
        glow3.setOffset(0)
        self.ui.frame.setGraphicsEffect(glow3)
        if self.ui.frame.layout() is None:
            self.ui.frame.setLayout(QVBoxLayout())

        # Connect buttons
        self.ui.AskPanDAEnter.clicked.connect(self.AskPanDAEnter)
        self.ui.pushButton.clicked.connect(self.add_button)
        icon = QIcon("run_button.png")
        self.ui.pushButton_4.setIcon(icon)
        self.ui.pushButton_4.setIconSize(QSize(40, 40))
        self.ui.pushButton_4.setStyleSheet("text-align: left; padding-left: 8px;")

    def add_button(self):
        # Create/open the second window
        self.add_site_window = AddSiteWindow()
        self.add_site_window.text_submitted.connect(self.create_button)

        # Show second window to get text
        self.add_site_window.show()
        self.add_site_window.raise_()

    def create_button(self, SiteName):
        btn = FillButton(SiteName)
        btn.setFixedSize(self.button_size, self.button_size)

        row = self.button_count // self.columns
        col = self.button_count % self.columns

        self.grid.addWidget(btn, row, col)
        self.button_count += 1

        btn.clicked.connect(lambda: self.site_display(SiteName))

    def site_display(self,SiteName):
        # Create/open the second window
        self.display_site_window = SiteDisplay(SiteName)
        self.display_site_window.show()
        self.display_site_window.raise_()


    def AskPanDAEnter(self):

        text = self.ui.AskPanDABox.toPlainText();

        if (text == ""):
            self.clear_current_widget()
        elif(text == "site load at BNL histogram"):
            self.show_plot()
        elif (text == "jobs at BNL table"):
            self.show_table()
        elif (text == "generate a summary of site load at BNL"):
            self.show_text(text)
        else:
            pass

        if (text != ""):
            self.ui.AskPanDARecent.append(f"{text}\n")


    def clear_current_widget(self):
        if self.current_widget:
            self.ui.dynamicFrame.layout().removeWidget(self.current_widget)
            self.current_widget.deleteLater()
            self.current_widget = None

    def show_table(self):
        self.clear_current_widget()
        table = QTableView()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels([
        "Site", "Job-ID", "Job State", "Cores", "Memory",
        "Site Cores Available", "Site Cores Occupied",
        "User", "Queue", "Submit Time", "Elapsed Time"
        ])


        data = []
        job_states = ["Pending", "Running", "Finished"]
        users = ["alice", "bob", "carol", "dave"]
        queues = ["short", "medium", "long"]
        import random
        from datetime import datetime, timedelta

        for i in range(1000):
            submit_time = datetime.now() - timedelta(days=7) + timedelta(seconds=random.randint(0, 7 * 24 * 3600))
            duration = timedelta(seconds=random.randint(300, 3600))  # 5-60 min
            end_time = submit_time + duration
            cores = random.randint(1, 8)
            memory = f"{random.choice([100, 200, 500, 1024])} MB"
            job_state = random.choice(job_states)
            user = random.choice(users)
            queue = random.choice(queues)
            available = 4800+6*i
            occupied = 11000-available

            job = [
                "BNL",
                2090000 + i*43,
                job_state,
                cores,
                memory,
                available,
                occupied,
                user,
                queue,
                submit_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time.strftime("%Y-%m-%d %H:%M:%S")
            ]
            data.append(job)

        for row in data:
            model.appendRow([QStandardItem(str(x)) for x in row])

        table.setModel(model)
        self.ui.dynamicFrame.layout().addWidget(table)
        header = table.horizontalHeader()
        for i in range(model.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.current_widget = table

    def show_text(self,input_text):

        site_load_report = """
        During the simulation at BNL, the site had a total of 11,000 cores available.

        At the start of the simulation, several jobs were already running:
        - Job 2090909: 4 cores
        - Job 2090910: 8 cores
        - Job 2090911: 16 cores

        New jobs were submitted throughout the simulation, increasing the load. For example:
        - Job 2090912 ran with 32 cores
        - Job 2090913 ran with 64 cores

        At peak load, the site had approximately 6,500 cores actively in use, leaving 4,500 cores free.

        Memory usage varied across jobs, ranging from 100 MB to 2 GB per job.

        The average number of running jobs at any point was around 12, while 5–8 jobs were typically queued or pending.

        The site cores availability fluctuated depending on job completions, but the total cores remained constant at 11,000.

        By the end of the simulation, the load decreased as jobs finished, with roughly 3,200 cores free and 7,800 cores in use.

        Overall, the site load at BNL showed that the resource utilization was moderate to high, with peak usage reaching almost 60% of total cores.
        """

        self.clear_current_widget()
        text = QTextEdit()
        text.setReadOnly(True)
        text.setFontFamily("Georgia")
        text.setFontPointSize(18)
        text.append(f"<h2>Site Load Report at BNL</h2>")
        text.append(site_load_report)
        QTimer.singleShot(1, lambda: text.verticalScrollBar().setValue(text.verticalScrollBar().minimum()))
        self.ui.dynamicFrame.layout().addWidget(text)
        self.current_widget = text

    def show_plot(self):
        self.clear_current_widget()

        # Example data
        data = np.random.normal(loc=50, scale=10, size=500)

        # Create figure and canvas
        figure = Figure()
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)

        from datetime import datetime, timedelta

        # Parameters
        num_points = 1000
        total_cores = 11000
        num_bins = 30  # number of time bins

        # Generate timestamps (1-minute intervals)
        times = np.array([datetime.now() - timedelta(days=7) + timedelta(minutes=i) for i in range(num_points)])

        # Simulate core usage: wave pattern + noise
        x = np.linspace(0, 2 * np.pi, num_points)
        core_usage = total_cores - (4800 + (total_cores - 4800) * (0.5 + 0.5 * np.cos(x)))
        noise = np.random.randint(-50, 50, size=num_points)
        core_usage_noisy = np.clip(core_usage + noise, 0, total_cores)

        # Convert datetime to numeric for histogram
        times_numeric = np.array([t.timestamp() for t in times])

        ax.hist(times_numeric, bins=num_bins, weights=core_usage_noisy, color='skyblue', edgecolor='black')
        ax.set_title("Core Usage at BNL Over Time")
        ax.set_xlabel("Time")
        ax.set_ylabel("Cores in Use")
        ax.grid(axis='y', alpha=0.75)

        # Format x-axis to datetime
        xticks = np.linspace(times_numeric.min(), times_numeric.max(), 6)
        xtick_labels = [datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') for ts in xticks]
        ax.set_xticks(xticks)
        ax.set_xticklabels(xtick_labels, rotation=45)

        ax.legend(["Core Usage"])
        figure.tight_layout()

        self.ui.dynamicFrame.layout().addWidget(canvas)
        self.current_widget = canvas

    def closeEvent(self, event):
        # Quit the entire application when main window closes
        QApplication.instance().quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    with open(str(get_project_root()/'ui'/'theme1.qss'), "r") as f:
        style = f.read()
        app.setStyleSheet(style)

    my_app = main_app()
    my_app.show()
    sys.exit(app.exec())


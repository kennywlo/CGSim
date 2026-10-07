from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtCharts import *
from PyQt6 import uic
from utils import get_project_root
import random
from Node import NodeDisplay

class FillButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.fill_ratio = 0.0
        self.fill_step = 0.05

        # OVERRIDE global button style
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #00eaff;
                border: 2px solid #00eaff;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        self.setFlat(True)  # prevent Qt from painting its own background
        self.clicked.connect(self.on_click)

        self.fill_ratio = min(1.0, self.fill_ratio + random.randint(1,20)*self.fill_step)
        self.update()

        self.timer_2 = QTimer()
        self.timer_2.timeout.connect(self.color_random)
        self.timer_2.start(1500)

    def color_random(self):
        self.fill_ratio = 0
        self.fill_ratio = min(1.0, self.fill_ratio + random.randint(1, 20) * self.fill_step)
        self.update()


    def on_click(self):
        self.fill_ratio = min(1.0, self.fill_ratio + self.fill_step)
        self.update()

    def get_fill_color(self):
        # Smooth green → yellow → red transition
        r = int(255 * self.fill_ratio)
        g = int(255 * (1 - self.fill_ratio))
        return QColor(r, g, 0, 180)  # transparency included

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # --- Draw the vertical fill area (bottom → top) ---
        fill_h = int(h * self.fill_ratio)
        y_start = h - fill_h
        fill_color = self.get_fill_color()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_color)
        painter.drawRoundedRect(0, y_start, w, fill_h, 8, 8)

        # Draw border + text usually
        super().paintEvent(event)

class SiteDisplay(QMainWindow):
    def __init__(self,SiteName):
        super().__init__()

        # Load the UI
        self.qtdesignerfile = get_project_root() / 'ui' / 'SiteDisplay.ui'
        self.Ui_MainWindow, _ = uic.loadUiType(self.qtdesignerfile)
        self.ui = self.Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle(SiteName)

        self.add_color_grid(self.ui.widget_3, num_cells=1000, cells_per_row=10)
        self.ui.textBrowser.setStyleSheet("""
            QTextBrowser {
                border: none;               /* remove border */
                background: transparent;    /* make background blend */
                font-size: 25pt;            /* text size */
                color: #008f11;             /* neon green text, adjust as needed */
                padding: 0;                 /* remove internal padding */
                margin: 0;                  /* remove margins */
            }
        """)
        self.ui.textBrowser.append("Active")
        font = QFont()
        font.setPointSize(14)
        self.ui.pushButton.setFont(font)
        self.ui.pushButton_2.setFont(font)


        # ----------------- CYBERPUNK NEON COLORS -----------------
        neon_colors = [
            QColor("#cfcfcf"),
            QColor("#b6ff4f"),
            QColor("#00b300"),
            QColor("#ff073a")
        ]

        # ----------------- CREATE PIE SERIES -----------------
        series = QPieSeries()
        labels = ["Pending", "Running", "Finished", "Failed"]
        values = [1, 1, 1, 1]
        self.slices = []

        for i in range(len(labels)):
            slice_ = series.append(labels[i], values[i])
            slice_.setBrush(neon_colors[i % len(neon_colors)])
            slice_.setPen(QPen(QColor("#00ffff"), 2))
            slice_.setLabelColor(QColor("#00ffff"))
            slice_.setLabelVisible(True)
            self.slices.append(slice_)
            slice_.hovered.connect(self.on_hover)
            slice_.clicked.connect(self.on_click)

        # ----------------- CREATE CHART -----------------
        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("Workload Monitoring")
        font = QFont()
        font.setPointSize(20)
        chart.setTitleFont(font)
        chart.setTitleBrush(QColor("#00eaff"))
        chart.setBackgroundBrush(QColor("#0d0d0f"))  # pure black
        chart.setPlotAreaBackgroundBrush(QColor("#0d0d0f"))  # pure black
        chart.setPlotAreaBackgroundVisible(True)
        chart.legend().setLabelColor(QColor("#00faff"))
        chart.legend().hide()
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)

        # ----------------- CREATE CHART VIEW -----------------
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_view.setStyleSheet("background: transparent;")

        # ----------------- ADD TO YOUR WIDGET -----------------
        # Make sure the widget has a layout
        if self.ui.widget.layout() is None:
            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            self.ui.widget.setLayout(layout)
        self.ui.widget.layout().addWidget(chart_view)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_chart)
        self.timer.start(1500)

        #----------------------------------

        # ----------------------------
        # 1. Data
        # ----------------------------
        self.sites_2 = ["BNL", "MWT2", "AGLT2", "Beijing-LCG2"]

        # Create bar data
        self.incoming_2 = QBarSet("Incoming")
        self.outgoing_2 = QBarSet("Outgoing")

        self.incoming_2.setColor(QColor("#008f11"))
        self.outgoing_2.setColor(QColor("#0033cc"))


        self.incoming_2.append([random.randint(10, 100) for _ in self.sites_2])
        self.outgoing_2.append([random.randint(10, 100) for _ in self.sites_2])

        # Connect click and hover events
        self.incoming_2.clicked.connect(self.bar_clicked_2)
        self.outgoing_2.clicked.connect(self.bar_clicked_2)
        self.incoming_2.hovered.connect(self.bar_hovered_2)
        self.outgoing_2.hovered.connect(self.bar_hovered_2)

        self.series_2 = QBarSeries()
        self.series_2.append(self.incoming_2)
        self.series_2.append(self.outgoing_2)

        # ----- CHART CONFIG -----
        self.chart_2 = QChart()
        self.chart_2.addSeries(self.series_2)
        self.chart_2.setTitle("Data Transfers")
        self.chart_2.setTitleFont(font)
        self.chart_2.setTitleBrush(QColor("#00eaff"))
        self.chart_2.setBackgroundBrush(QColor("#0d0d0f"))
        self.chart_2.setPlotAreaBackgroundBrush(QColor("#0d0d0f"))
        self.chart_2.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)

        # AXIS X
        self.axis_x_2 = QBarCategoryAxis()
        self.axis_x_2.setTitleText("Sites")
        self.axis_x_2.setTitleFont(QFont("Arial", 14))
        self.axis_x_2.setTitleBrush(QColor("#00eaff"))
        self.axis_x_2.setLabelsFont(QFont("Arial", 12))
        self.axis_x_2.setLabelsColor(QColor("#00eaff"))
        self.axis_x_2.setLabelsAngle(-35)
        self.axis_x_2.append(self.sites_2)

        # AXIS Y
        self.axis_y_2 = QValueAxis()
        self.axis_y_2.setTitleText("Data (GB)")
        self.axis_y_2.setTitleFont(QFont("Arial", 14))
        self.axis_y_2.setTitleBrush(QColor("#00eaff"))
        self.axis_y_2.setLabelsFont(QFont("Arial", 12))
        self.axis_y_2.setLabelsColor(QColor("#00eaff"))
        self.axis_y_2.setRange(0, 120)

        # Attach axes
        self.chart_2.addAxis(self.axis_x_2, Qt.AlignmentFlag.AlignBottom)
        self.chart_2.addAxis(self.axis_y_2, Qt.AlignmentFlag.AlignLeft)
        self.series_2.attachAxis(self.axis_x_2)
        self.series_2.attachAxis(self.axis_y_2)

        # VIEW
        bar_view = QChartView(self.chart_2)
        bar_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar_view.setMinimumHeight(400)

        if self.ui.widget_2.layout() is None:
            self.ui.widget_2.setLayout(QVBoxLayout())
        self.ui.widget_2.layout().addWidget(bar_view)

        # UPDATE TIMER
        self.timer_2 = QTimer()
        self.timer_2.timeout.connect(self.update_data_2)
        self.timer_2.start(1500)

        # ----------------- CLICK HANDLER -----------------
    def bar_clicked_2(self, index):
        sender = self.sender()  # Identify which QBarSet
        site = self.sites_2[index]

        if sender == self.incoming_2:
            value = self.incoming_2.at(index)
            bar_type = "Incoming"
        else:
            value = self.outgoing_2.at(index)
            bar_type = "Outgoing"

        QMessageBox.information(None, "Bar Clicked",
                                f"{site}\n{bar_type}: {value}")

    # ----------------- HOVER HANDLER -----------------
    def bar_hovered_2(self, status, index):
        if status:
            site = self.sites_2[index]
            inc = self.incoming_2.at(index)
            out = self.outgoing_2.at(index)
            QToolTip.showText(QCursor.pos(),
                              f"{site}\nIncoming: {inc}\nOutgoing: {out}")

    # ----------------- DATA UPDATE -----------------
    def update_data_2(self):
        random.shuffle(self.sites_2)
        for i in range(len(self.sites_2)):
            self.incoming_2.replace(i, random.randint(10, 100))
            self.outgoing_2.replace(i, random.randint(10, 100))

        # Update Y-axis dynamically
        max_val = max(
            max(self.incoming_2.at(i) for i in range(len(self.sites_2))),
            max(self.outgoing_2.at(i) for i in range(len(self.sites_2)))
        )
        self.axis_y_2.setRange(0, max(120, max_val + 10))
        self.axis_x_2.clear()
        self.axis_x_2.append(self.sites_2)

        self.chart_2.update()

    # ----------------- HOVER EFFECT -----------------



    def on_hover(self, state):
        slice_ = self.sender()
        if state:
            slice_.setExploded(True)
            slice_.setPen(QPen(QColor("#ff00f5"), 4))
            QToolTip.showText(QCursor.pos(), f"Jobs: {int(slice_.value())}")
        else:
            slice_.setExploded(False)
            slice_.setPen(QPen(QColor("#00ffff"), 2))
            QToolTip.hideText()

        # ----------------- CLICK EFFECT -----------------

    def on_click(self):
        slice_ = self.sender()
        print(f"Clicked: {slice_.label()} → {slice_.value()}")

    def update_chart(self):
        for slice_ in self.slices:
            # randomly change value (or use real data)
            new_value = 5
            if(slice_.label() == "Failed"):
                new_value = random.randint(500, 800)
            if (slice_.label() == "Pending"):
                new_value = random.randint(2000, 6000)
            if (slice_.label() == "Running"):
                new_value = random.randint(1000, 5000)
            if (slice_.label() == "Finished"):
                new_value = random.randint(1000, 5000)
            slice_.setValue(new_value)


    def show_node(self):
        self.display_site_window = NodeDisplay()
        self.display_site_window.show()
        self.display_site_window.raise_()

    def add_color_grid(self, placeholder, num_cells=10000, cells_per_row=7):
        # Create a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        # Container widget for the grid
        container = QWidget()
        scroll.setWidget(container)

        # Grid layout
        grid_layout = QGridLayout(container)

        # Fill grid with color cells
        for i in range(num_cells):
            row = i // cells_per_row
            col = i % cells_per_row
            cell = FillButton()
            cell.setFixedSize(30,30)
            grid_layout.addWidget(cell, row, col)
            cell.clicked.connect(self.show_node)

        label = QLabel("Nodes")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(24)  # change size as needed
        label.setFont(font)

        # Add scroll area to the placeholder's layout
        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(scroll)
        placeholder.setLayout(layout)

class AddSiteWindow(QMainWindow):

    #Signals
    text_submitted = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.qtdesignerfile = get_project_root() / 'ui' / 'AddSite.ui'
        self.Ui_MainWindow, _ = uic.loadUiType(self.qtdesignerfile)
        self.ui = self.Ui_MainWindow()
        self.ui.setupUi(self)

        # Connect button to emit signal
        self.ui.pushButton.clicked.connect(self.add_site)
        self.ui.pushButton_2.clicked.connect(self.add_row)
        self.ui.pushButton_3.clicked.connect(self.delete_selected_rows)

        # Set up model for table
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([
            "CPU", "Units","Cores", "BW", "LAT", "RAM",
            "Disks", "Disk Sizes", "(R) BWs", "(W) BWs"
        ])
        self.ui.tableView.setModel(self.model)
        self.model.insertRow(0)
        header = self.ui.tableView.horizontalHeader()
        for i in range(self.model.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            self.ui.tableView.setColumnWidth(i, 140)

        self.ui.tableView.setStyleSheet(style)

        font = QFont()
        font.setPointSize(12)
        self.ui.tableView.setFont(font)
        self.ui.tableView.verticalHeader().setDefaultSectionSize(50)

        self.model2 = QStandardItemModel()
        self.model2.setHorizontalHeaderLabels([
            "Site", "BW (GHz)", "LAT (ms)"
        ])
        self.model2.insertRow(0)
        self.ui.tableView_2.setModel(self.model2)
        header2 = self.ui.tableView_2.horizontalHeader()
        for i in range(self.model.columnCount()):
            header2.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            self.ui.tableView_2.setColumnWidth(i, 102)
        #header2.setStretchLastSection(True)
        self.ui.tableView_2.setStyleSheet(style)
        self.ui.tableView_2.setFont(font)
        self.ui.tableView_2.verticalHeader().setDefaultSectionSize(50)

    def add_site(self):
        text = self.ui.lineEdit.text()
        self.text_submitted.emit(text)
        self.close()

    def add_row(self):
        row_count = self.model.rowCount()
        # Add a new row with default empty items
        self.model.insertRow(row_count)
        for col in range(self.model.columnCount()):
            self.model.setItem(row_count, col, QStandardItem(""))

    def delete_selected_rows(self):
        selected_indexes = self.ui.tableView.selectionModel().selectedRows()
        for index in sorted(selected_indexes, reverse=True):
            self.model.removeRow(index.row())


style = """
            /* Main table without outer border */
            QTableView {
                background: transparent;
                color: #00ffcc;                          /* Neon bluish-green text */
                border: none;                             /* Removed outer border */
                border-radius: 8px;
                gridline-color: rgba(0, 255, 204, 0.3);
                alternate-background-color: rgba(10, 25, 25, 0.1);
                selection-background-color: #00ffcc;
                selection-color: #0f1f1f;
            }


            QTableView::item:hover {
                background-color: rgba(0, 102, 102, 0.5);
                color: #ffffff;
            }

            /* Headers - transparent with glow */
            QHeaderView::section {
                border: none;
                border-bottom: 2px solid #00cc99;       /* Subtle underline */
                background: transparent;                  /* Transparent header */
                color: #00ffcc;                           /* Neon bluish-green text */
                padding: 6px;
                font-weight: bold;
                font-size: 14px;
                border-left: 1px solid rgba(0, 255, 204, 0.4);
                border-right: 1px solid rgba(0, 255, 204, 0.4);
                border-top: 1px solid rgba(0, 255, 204, 0.2);
            }

            QHeaderView::section:hover {
                background: transparent;
                color: #ffffff;
                border-left: 1px solid rgba(51, 255, 204, 0.6);
                border-right: 1px solid rgba(51, 255, 204, 0.6);
                border-top: 1px solid rgba(51, 255, 204, 0.4);
            }

            /* Scrollbar - vertical */
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 0px 0px 0px 0px;
            }

            QScrollBar::handle:vertical {
                background: #00ffcc;
                min-height: 20px;
                border-radius: 6px;
            }

            QScrollBar::handle:vertical:hover {
                background: #66ffe0;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                subcontrol-origin: margin;
            }

            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            /* Scrollbar - horizontal */
            QScrollBar:horizontal {
                background: transparent;
                height: 12px;
                margin: 0px 0px 0px 0px;
            }

            QScrollBar::handle:horizontal {
                background: #00ffcc;
                min-width: 20px;
                border-radius: 6px;
            }

            QScrollBar::handle:horizontal:hover {
                background: #66ffe0;
            }

            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                subcontrol-origin: margin;
            }

            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """
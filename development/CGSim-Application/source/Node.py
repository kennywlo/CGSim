from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtCharts import *
from PyQt6 import uic
import psutil
from utils import get_project_root
import random
import pyqtgraph as pg

import sys
import random
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen
from PyQt6.QtWidgets import QWidget, QApplication

class MemoryBar(QWidget):
    def __init__(self):
        super().__init__()
        self.percent = 0  # 0–100
        self.mem = psutil.virtual_memory()

        self.setMinimumSize(300, 40)
        self.setMouseTracking(True)  # enable hover events

        # Timer to update memory usage
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_value)
        self.timer.start(500)  # update every 0.5s

    def update_value(self):
        self.mem = psutil.virtual_memory()
        self.percent = self.mem.percent
        self.update()

    # ---- HOVER TOOLTIP ----
    def mouseMoveEvent(self, event):
        used_gb = self.mem.used / (1024**3)
        total_gb = self.mem.total / (1024**3)
        tip = f"Memory Usage: {used_gb:.2f} GB / {total_gb:.2f} GB ({self.percent:.0f}%)"
        QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    # ---- DRAWING ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Border rectangle area
        border_x = 5
        border_y = 5
        border_w = w - 10
        border_h = h - 10

        # Draw border
        pen = QPen(Qt.GlobalColor.black, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(border_x, border_y, border_w, border_h, 5, 5)

        # Compute filled bar width
        usable_w = border_w - 2
        filled_w = int(usable_w * (self.percent / 100))

        # Compute color
        if self.percent < 50:
            r = int(255 * (self.percent / 50))
            g = 255
        else:
            r = 255
            g = int(255 * (1 - (self.percent - 50) / 50))
        color = QColor(r, g, 0)

        # Draw filled section
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(border_x + 1, border_y + 1,
                                filled_w, border_h - 2, 5, 5)


class Speedometer(QWidget):
    def __init__(self):
        super().__init__()
        self.value = 0  # 0–100 (%)
        self.setMinimumSize(1, 1)

        # Timer – replace random with real memory later
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_value)
        self.timer.start(300)

    def update_value(self):
        # random for now (you can change this to real memory)
        self.value = psutil.cpu_percent(interval=None)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        size = min(rect.width(), rect.height()) - 20
        cx = rect.width() // 2
        cy = rect.height() // 2
        radius = size // 2

        # -- Background arc --
        pen_bg = QPen(QColor(180, 180, 180, 80), 18)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(cx - radius, cy - radius, size, size,
                        135 * 16, 270 * 16)

        # -- Value arc --
        angle_span = int((self.value / 100) * 270)
        pen_val = QPen(QColor(60, 160, 255), 20)
        pen_val.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_val)
        painter.drawArc(cx - radius, cy - radius, size, size,
                        135 * 16, angle_span * 16)

        # -- Text --
        painter.setPen(QColor(220, 220, 220))
        painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                         f"{self.value:.0f}%")

        painter.setFont(QFont("Arial", 12))
        #painter.drawText(self.rect().adjusted(0, 40, 0, 0),
                    #     Qt.AlignmentFlag.AlignCenter,
                     #    "Memory")

class NodeDisplay(QMainWindow):
    def __init__(self):
        super().__init__()

        # Load the UI
        self.qtdesignerfile = get_project_root() / 'ui' / 'NodeDisplay.ui'
        self.Ui_MainWindow, _ = uic.loadUiType(self.qtdesignerfile)
        self.ui = self.Ui_MainWindow()
        self.ui.setupUi(self)
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

        layout = QVBoxLayout(self.ui.frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.ui.frame.setLayout(layout)

        self.gauge = Speedometer()
        layout.addWidget(self.gauge)

        layout = QVBoxLayout(self.ui.frame_2)
        layout.setContentsMargins(0, 0, 0, 0)
        self.ui.frame_2.setLayout(layout)

        self.bar = MemoryBar()
        layout.addWidget(self.bar)

        cpu = "Intel(R) Core(TM) i7-11700K @ 3.60GHz"
        cores = 32
        bandwidth = "45 GB/s"
        latency = "80 ns"
        ram = "32 GB DDR4 3200 MHz"
        disks = 2
        disk_sizes = "1 TB NVMe SSD, 2 TB SATA HDD"
        read_bw = "3500 MB/s, 200 MB/s"
        write_bw = "3000 MB/s, 180 MB/s"

        html_text = f"""
        <html>
            <body style="font-family: Arial, monospace; font-size: 11pt;">
                <p><b>CPU:</b> {cpu}</p>
                <p><b>Cores:</b> {cores}</p>
                <p><b>Bandwidth:</b> {bandwidth}</p>
                <p><b>Latency:</b> {latency}</p>
                <p><b>RAM:</b> {ram}</p>
                <p><b>Disks:</b> {disks}</p>
                <p><b>Disk Sizes:</b> {disk_sizes}</p>
                <p><b>Read Bandwidths (R):</b> {read_bw}</p>
                <p><b>Write Bandwidths (W):</b> {write_bw}</p>
            </body>
        </html>
        """

        self.ui.textBrowser_2.setHtml(html_text)

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
                new_value = random.randint(5, 8)
            if (slice_.label() == "Pending"):
                new_value = random.randint(20, 60)
            if (slice_.label() == "Running"):
                new_value = random.randint(10, 50)
            if (slice_.label() == "Finished"):
                new_value = random.randint(10, 50)
            slice_.setValue(new_value)

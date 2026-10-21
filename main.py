
import sys
import random
import sqlite3
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QComboBox, QScrollArea, QSizePolicy
)


STYLE = """
QMainWindow, QWidget {
    background: #0b0f14;
    color: #e5e7eb;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QFrame#Sidebar {
    background: #10151d;
    border-right: 1px solid #252c36;
}
QFrame#Panel {
    background: #111720;
    border: 1px solid #27313d;
    border-radius: 10px;
}
QLabel#Brand {
    color: #ff9f43;
    font-size: 27px;
    font-weight: 800;
}
QLabel#Muted { color: #8793a3; }
QLabel#Heading {
    color: #f3f4f6;
    font-size: 19px;
    font-weight: 700;
}
QLabel#Metric {
    color: #ffffff;
    font-size: 27px;
    font-weight: 700;
}
QLabel#DetailValue {
    color: #e5e7eb;
    font-size: 12px;
    font-weight: 600;
}
QPushButton {
    background: #1a222e;
    color: #e5e7eb;
    border: 1px solid #303b49;
    border-radius: 6px;
    padding: 10px;
    text-align: left;
}
QPushButton:hover { background: #273343; }
QPushButton#Primary {
    background: #f28c28;
    color: #111111;
    font-weight: 800;
    text-align: center;
}
QPushButton#Primary:hover { background: #ffad55; }
QLineEdit, QComboBox {
    background: #0d131b;
    color: #e5e7eb;
    border: 1px solid #303b49;
    border-radius: 6px;
    padding: 8px;
    min-height: 22px;
}
QComboBox QAbstractItemView {
    background: #111720;
    color: #e5e7eb;
    selection-background-color: #303d4e;
}
QTableWidget {
    background: #111720;
    alternate-background-color: #151d27;
    color: #e5e7eb;
    border: none;
    gridline-color: #27313d;
    selection-background-color: #303d4e;
}
QHeaderView::section {
    background: #18212c;
    color: #aeb8c5;
    padding: 9px;
    border: none;
}
QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background: #10151d;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #465363;
    min-height: 35px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #ff9f43;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
"""


class LocationMap(QWidget):
    """Stylized map displaying simulated incident locations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.incidents = []
        self.selected_id = None
        self.setMinimumHeight(260)
        self.setMinimumWidth(280)

    def set_data(self, incidents, selected_id=None):
        self.incidents = list(incidents)
        self.selected_id = selected_id
        self.update()

    def project(self, lat, lon):
        w, h = self.width(), self.height()
        x = w * 0.50 + (lon - 78.4867) * 1550
        y = h * 0.53 - (lat - 17.3850) * 1800
        return QPointF(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor("#0b1820"))

        painter.setPen(QPen(QColor("#142a32"), 1))
        for x in range(0, w, 28):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 28):
            painter.drawLine(0, y, w, y)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#112c2b"))

        for x, y, rw, rh in [
            (0.04, 0.14, 0.19, 0.24),
            (0.64, 0.60, 0.25, 0.23),
            (0.31, 0.04, 0.13, 0.13),
        ]:
            painter.drawRoundedRect(
                int(w * x), int(h * y),
                int(w * rw), int(h * rh), 12, 12
            )

        roads = [
            [QPointF(-20, h * .78), QPointF(w * .20, h * .60),
             QPointF(w * .43, h * .48), QPointF(w * .66, h * .30),
             QPointF(w + 20, h * .17)],
            [QPointF(w * .13, -20), QPointF(w * .25, h * .26),
             QPointF(w * .50, h * .52), QPointF(w * .72, h * .77),
             QPointF(w * .86, h + 20)],
            [QPointF(-10, h * .35), QPointF(w * .29, h * .42),
             QPointF(w * .58, h * .40), QPointF(w + 10, h * .48)],
            [QPointF(w * .55, -10), QPointF(w * .52, h * .32),
             QPointF(w * .60, h * .62), QPointF(w * .48, h + 10)],
        ]

        for color, width in [("#30434a", 8), ("#52636a", 2)]:
            painter.setPen(QPen(
                QColor(color), width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin
            ))
            for points in roads:
                path = QPainterPath()
                path.moveTo(points[0])
                for point in points[1:]:
                    path.lineTo(point)
                painter.drawPath(path)

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#8199a4"))

        for nx, ny, label in [
            (0.09, 0.11, "KUKATPALLY"),
            (0.09, 0.91, "GACHIBOWLI"),
            (0.59, 0.13, "SECUNDERABAD"),
            (0.59, 0.91, "HYDERABAD"),
        ]:
            painter.drawText(int(w * nx), int(h * ny), label)

        painter.setPen(QColor("#ffad55"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(14, 22, "HYDERABAD REGION")

        for incident in self.incidents:
            point = self.project(incident["lat"], incident["lon"])
            x, y = point.x(), point.y()

            if not (-15 <= x <= w + 15 and -15 <= y <= h + 15):
                continue

            selected = incident["id"] == self.selected_id
            active = incident["status"] == "Active"
            color = QColor("#ff5b62" if active else "#50c99a")

            if selected:
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 13, 13)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(
                color.red(), color.green(), color.blue(), 55
            ))
            painter.drawEllipse(QPointF(x, y), 11, 11)

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#10151d"), 1))
            painter.drawEllipse(QPointF(x, y), 5, 5)

            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.setPen(QColor("#e5e7eb"))
            painter.drawText(
                min(max(4, int(x + 9)), max(4, w - 72)),
                min(max(34, int(y - 8)), max(34, h - 6)),
                f"#{incident['id']}"
            )

        painter.fillRect(
            0, h - 27, w, 27, QColor(8, 14, 19, 235)
        )
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#ffad55"))
        painter.drawText(
            12, h - 9, "DEMO MAP | SIMULATED LOCATIONS — NOT LIVE GPS"
        )
        painter.end()


class SentraConsole(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "SENTRA Command | Emergency Response Console"
        )
        self.resize(1440, 900)
        self.setMinimumSize(850, 600)

        # Reuse the existing database; do not delete sentra.db.
        self.db = sqlite3.connect("sentra.db")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY,
                time TEXT,
                location TEXT,
                lat REAL,
                lon REAL,
                priority TEXT,
                status TEXT,
                source TEXT
            )
        """)
        self.db.commit()

        self.incidents = []
        self.selected_id = None
        self.next_id = self.db.execute(
            "SELECT COALESCE(MAX(id), 1000) + 1 FROM incidents"
        ).fetchone()[0]
        self.metrics = {}

        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.create_sidebar())

        # The main dashboard is now inside a real vertical scroll area.
        self.scroll = QScrollArea()
        self.scroll.setObjectName("MainScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        content = QWidget()
        content.setMinimumWidth(700)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )

        main = QVBoxLayout(content)
        main.setContentsMargins(22, 20, 22, 20)
        main.setSpacing(14)

        main.addLayout(self.create_topbar())
        main.addLayout(self.create_metrics())

        middle = self.create_middle()
        main.addLayout(middle)

        main.addWidget(self.create_details_panel())

        table_panel = self.create_incident_table()
        table_panel.setMinimumHeight(420)
        main.addWidget(table_panel)

        main.addStretch(1)

        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)

        self.setStyleSheet(STYLE)
        self.load_incidents()

        self.clock = QTimer(self)
        self.clock.timeout.connect(self.update_clock)
        self.clock.start(1000)
        self.update_clock()

    def create_sidebar(self):
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(205)

        box = QVBoxLayout(side)
        box.setContentsMargins(15, 24, 15, 18)
        box.setSpacing(12)

        brand = QLabel("SENTRA")
        brand.setObjectName("Brand")
        box.addWidget(brand)

        sub = QLabel("COMMAND CENTER")
        sub.setObjectName("Muted")
        box.addWidget(sub)
        box.addSpacing(18)

        for name in [
            "◈  Overview", "⊙  Emergency Alerts", "⌖  Live Map",
            "▤  Incident Records", "♧  Responders",
            "◉  Device Status", "⚙  System Settings",
        ]:
            btn = QPushButton(name)
            btn.setMinimumHeight(42)
            box.addWidget(btn)

        box.addStretch()

        status = QLabel("● SIMULATION MODE")
        status.setStyleSheet("color: #ffb454; font-weight: 700;")
        box.addWidget(status)

        note = QLabel("No real emergency\nservices connected.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        box.addWidget(note)

        return side

    def create_topbar(self):
        row = QHBoxLayout()
        left = QVBoxLayout()

        title = QLabel("Emergency Operations")
        title.setObjectName("Heading")
        left.addWidget(title)

        subtitle = QLabel("Monitoring and incident coordination")
        subtitle.setObjectName("Muted")
        left.addWidget(subtitle)

        row.addLayout(left)
        row.addStretch()

        self.clock_label = QLabel()
        self.clock_label.setStyleSheet(
            "color: #ffad55; font-weight: 700;"
        )
        row.addWidget(self.clock_label)

        return row

    def create_metrics(self):
        grid = QGridLayout()
        grid.setSpacing(10)

        for col, (name, key, color) in enumerate([
            ("TOTAL INCIDENTS", "total", "#f59e0b"),
            ("ACTIVE ALERTS", "active", "#ff626b"),
            ("ACKNOWLEDGED", "ack", "#50c99a"),
            ("RESOLVED", "resolved", "#75a7ff"),
        ]):
            panel = QFrame()
            panel.setObjectName("Panel")

            box = QVBoxLayout(panel)
            box.setContentsMargins(12, 12, 12, 12)

            label = QLabel(name)
            label.setObjectName("Muted")
            label.setWordWrap(True)

            value = QLabel("0")
            value.setObjectName("Metric")
            value.setStyleSheet(f"color: {color};")

            box.addWidget(label)
            box.addWidget(value)
            self.metrics[key] = value
            grid.addWidget(panel, 0, col)

        return grid

    def create_middle(self):
        row = QHBoxLayout()
        row.setSpacing(12)

        map_panel = QFrame()
        map_panel.setObjectName("Panel")

        map_box = QVBoxLayout(map_panel)
        map_box.setContentsMargins(12, 12, 12, 12)

        heading = QLabel("INCIDENT LOCATION OVERVIEW")
        heading.setStyleSheet("font-weight: 700;")
        map_box.addWidget(heading)

        self.map_widget = LocationMap()
        map_box.addWidget(self.map_widget)

        row.addWidget(map_panel, 3)

        actions = QFrame()
        actions.setObjectName("Panel")
        actions.setMinimumWidth(220)

        action_box = QVBoxLayout(actions)
        action_box.setContentsMargins(14, 14, 14, 14)
        action_box.setSpacing(10)

        heading = QLabel("QUICK ACTIONS")
        heading.setStyleSheet("font-weight: 700;")
        action_box.addWidget(heading)

        sos = QPushButton("+  SIMULATE SOS ALERT")
        sos.setObjectName("Primary")
        sos.setMinimumHeight(44)
        sos.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        sos.clicked.connect(self.simulate_sos)
        action_box.addWidget(sos)

        ack = QPushButton("✓  Acknowledge Selected")
        ack.setMinimumHeight(40)
        ack.clicked.connect(
            lambda: self.change_status("Acknowledged")
        )
        action_box.addWidget(ack)

        resolve = QPushButton("✓  Resolve Selected")
        resolve.setMinimumHeight(40)
        resolve.clicked.connect(
            lambda: self.change_status("Resolved")
        )
        action_box.addWidget(resolve)

        heading = QLabel("COMMUNICATION STATUS")
        heading.setObjectName("Muted")
        action_box.addSpacing(8)
        action_box.addWidget(heading)

        for text in [
            "GPS · SIMULATED",
            "SATELLITE · SIMULATED",
            "AUDIO · NOT CONNECTED",
            "POLICE LINK · OFFLINE",
        ]:
            label = QLabel("●  " + text)
            label.setWordWrap(True)
            label.setStyleSheet("color:#a9b5c4; padding:3px;")
            action_box.addWidget(label)

        action_box.addStretch()
        row.addWidget(actions, 1)

        return row

    def create_details_panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        heading_row = QHBoxLayout()

        heading = QLabel("SELECTED INCIDENT DETAILS")
        heading.setObjectName("Heading")
        heading_row.addWidget(heading)
        heading_row.addStretch()

        self.detail_status = QLabel("NO INCIDENT SELECTED")
        self.detail_status.setStyleSheet(
            "color:#ffad55; font-weight:700;"
        )
        heading_row.addWidget(self.detail_status)
        outer.addLayout(heading_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

        fields = [
            ("Incident ID", "id"), ("Time", "time"),
            ("Location", "location"), ("Priority", "priority"),
            ("Status", "status"), ("Source", "source"),
            ("Latitude", "lat"), ("Longitude", "lon"),
        ]

        self.detail_labels = {}

        for index, (label_text, key) in enumerate(fields):
            col = index % 4
            row = index // 4

            field_label = QLabel(label_text.upper())
            field_label.setObjectName("Muted")

            value_label = QLabel("—")
            value_label.setObjectName("DetailValue")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            cell = QVBoxLayout()
            cell.setSpacing(3)
            cell.addWidget(field_label)
            cell.addWidget(value_label)

            grid.addLayout(cell, row, col)
            self.detail_labels[key] = value_label

        outer.addLayout(grid)

        self.detail_note = QLabel(
            "Select an incident in the table to inspect its details."
        )
        self.detail_note.setObjectName("Muted")
        self.detail_note.setWordWrap(True)
        outer.addWidget(self.detail_note)

        return panel

    def update_details(self, incident=None):
        if incident is None:
            self.detail_status.setText("NO INCIDENT SELECTED")

            for label in self.detail_labels.values():
                label.setText("—")

            self.detail_note.setText(
                "Select an incident in the table to inspect its details."
            )
            return

        values = {
            "id": f"#{incident['id']}",
            "time": incident["time"],
            "location": incident["location"],
            "priority": incident["priority"],
            "status": incident["status"],
            "source": incident["source"],
            "lat": f"{incident['lat']:.5f}",
            "lon": f"{incident['lon']:.5f}",
        }

        for key, value in values.items():
            self.detail_labels[key].setText(str(value))

        status = incident["status"]
        self.detail_status.setText(status.upper())

        color = (
            "#ff626b" if status == "Active"
            else "#50c99a" if status == "Resolved"
            else "#75a7ff"
        )
        self.detail_status.setStyleSheet(
            f"color:{color}; font-weight:700;"
        )

        self.detail_note.setText(
            "DEMO RECORD — coordinates are simulated, not live GPS."
        )

    def create_incident_table(self):
        panel = QFrame()
        panel.setObjectName("Panel")

        box = QVBoxLayout(panel)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(10)

        header = QHBoxLayout()

        title = QLabel("Incident Management")
        title.setObjectName("Heading")
        header.addWidget(title)
        header.addStretch()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_table)
        header.addWidget(refresh)
        box.addLayout(header)

        filter_row = QHBoxLayout()

        self.incident_search = QLineEdit()
        self.incident_search.setPlaceholderText(
            "Search ID, location, priority or source..."
        )
        self.incident_search.setClearButtonEnabled(True)
        self.incident_search.textChanged.connect(self.refresh_table)
        filter_row.addWidget(self.incident_search, 2)

        self.status_filter = QComboBox()
        self.status_filter.addItems([
            "All Statuses", "Active", "Acknowledged", "Resolved"
        ])
        self.status_filter.currentTextChanged.connect(
            self.refresh_table
        )
        filter_row.addWidget(self.status_filter, 1)

        self.priority_filter = QComboBox()
        self.priority_filter.addItems([
            "All Priorities", "HIGH", "MEDIUM", "LOW"
        ])
        self.priority_filter.currentTextChanged.connect(
            self.refresh_table
        )
        filter_row.addWidget(self.priority_filter, 1)

        box.addLayout(filter_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Incident ID", "Time", "Location",
            "Priority", "Status", "Source"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setMinimumHeight(260)
        self.table.itemSelectionChanged.connect(self.show_selected)

        box.addWidget(self.table, 1)
        return panel

    def simulate_sos(self):
        locations = [
            ("Hyderabad, Telangana", 17.3850, 78.4867),
            ("Secunderabad, Telangana", 17.4399, 78.4983),
            ("Gachibowli, Hyderabad", 17.4401, 78.3489),
            ("Kukatpally, Hyderabad", 17.4948, 78.3996),
        ]

        city, lat, lon = random.choice(locations)

        incident = {
            "id": self.next_id,
            "time": datetime.now().strftime("%H:%M:%S"),
            "location": city,
            "lat": lat + random.uniform(-0.002, 0.002),
            "lon": lon + random.uniform(-0.002, 0.002),
            "priority": "HIGH",
            "status": "Active",
            "source": "SIMULATED DEVICE",
        }

        self.db.execute(
            """
            INSERT INTO incidents
            (id, time, location, lat, lon, priority, status, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident["id"], incident["time"],
                incident["location"], incident["lat"],
                incident["lon"], incident["priority"],
                incident["status"], incident["source"]
            )
        )
        self.db.commit()

        self.incidents.insert(0, incident)
        self.next_id += 1
        self.selected_id = incident["id"]

        self.refresh_table()

        QMessageBox.information(
            self,
            "Simulated SOS",
            f"TEST ALERT ONLY\n\n"
            f"Incident: #{incident['id']}\n"
            f"Location: {city}\n\n"
            "No real emergency services were contacted."
        )

    def change_status(self, status):
        row = self.table.currentRow()

        if row < 0 or self.table.item(row, 0) is None:
            QMessageBox.warning(
                self, "Select Incident",
                "Select an incident in the table first."
            )
            return

        incident_id = int(
            self.table.item(row, 0).text().replace("#", "")
        )

        incident = next(
            (item for item in self.incidents
             if item["id"] == incident_id),
            None
        )

        if incident is None:
            return

        if incident["status"] == "Resolved":
            QMessageBox.information(
                self, "Closed Case",
                "This incident is already resolved."
            )
            return

        incident["status"] = status

        self.db.execute(
            "UPDATE incidents SET status = ? WHERE id = ?",
            (status, incident_id)
        )
        self.db.commit()

        self.selected_id = incident_id
        self.refresh_table()

    def load_incidents(self):
        rows = self.db.execute(
            """
            SELECT id, time, location, lat, lon,
                   priority, status, source
            FROM incidents ORDER BY id DESC
            """
        ).fetchall()

        self.incidents = [
            {
                "id": r[0],
                "time": r[1],
                "location": r[2],
                "lat": r[3],
                "lon": r[4],
                "priority": r[5],
                "status": r[6],
                "source": r[7],
            }
            for r in rows
        ]

        self.refresh_table()

    def refresh_table(self):
        selected_id = self.selected_id

        search = self.incident_search.text().strip().lower()
        status_filter = self.status_filter.currentText()
        priority_filter = self.priority_filter.currentText()

        filtered = []

        for incident in self.incidents:
            searchable = " ".join([
                str(incident["id"]),
                incident["time"],
                incident["location"],
                incident["priority"],
                incident["status"],
                incident["source"],
            ]).lower()

            if search and search not in searchable:
                continue

            if (
                status_filter != "All Statuses"
                and incident["status"] != status_filter
            ):
                continue

            if (
                priority_filter != "All Priorities"
                and incident["priority"].upper() != priority_filter
            ):
                continue

            filtered.append(incident)

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)

        selected_row = -1

        for row, incident in enumerate(filtered):
            self.table.insertRow(row)

            values = [
                f"#{incident['id']}",
                incident["time"],
                incident["location"],
                incident["priority"],
                incident["status"],
                incident["source"],
            ]

            for col, value in enumerate(values):
                self.table.setItem(
                    row, col, QTableWidgetItem(str(value))
                )

            if incident["id"] == selected_id:
                selected_row = row

        if selected_row >= 0:
            self.table.selectRow(selected_row)

        self.table.setUpdatesEnabled(True)
        self.table.blockSignals(False)

        self.metrics["total"].setText(str(len(self.incidents)))
        self.metrics["active"].setText(str(sum(
            item["status"] == "Active" for item in self.incidents
        )))
        self.metrics["ack"].setText(str(sum(
            item["status"] == "Acknowledged" for item in self.incidents
        )))
        self.metrics["resolved"].setText(str(sum(
            item["status"] == "Resolved" for item in self.incidents
        )))

        if selected_row >= 0:
            self.selected_id = selected_id
            selected = next(
                item for item in self.incidents
                if item["id"] == selected_id
            )
            self.update_details(selected)
        else:
            self.selected_id = None
            self.update_details(None)

        self.map_widget.set_data(self.incidents, self.selected_id)

    def show_selected(self):
        row = self.table.currentRow()

        if row < 0 or self.table.item(row, 0) is None:
            return

        incident_id = int(
            self.table.item(row, 0).text().replace("#", "")
        )

        incident = next(
            (item for item in self.incidents
             if item["id"] == incident_id),
            None
        )

        if incident is None:
            return

        self.selected_id = incident_id
        self.update_details(incident)
        self.map_widget.set_data(self.incidents, self.selected_id)

    def update_clock(self):
        self.clock_label.setText(
            datetime.now().astimezone().strftime(
                "%d %b %Y  |  %H:%M:%S"
            )
        )

    def closeEvent(self, event):
        self.db.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SentraConsole()
    window.show()
    sys.exit(app.exec())

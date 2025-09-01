#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FT-897 CAT Control – minimal but complete GUI demo.

This version bundles a simple serial interface, a full amateur-band table
for the Yaesu FT-897 and a PTT safety timer that automatically releases the
transmitter after three minutes.  The implementation is intentionally
compact while still providing a functional desktop application with memory
presets and repeater support.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    import serial  # type: ignore
    from serial.tools import list_ports  # type: ignore
except Exception:  # pragma: no cover - during syntax check serial may be absent
    serial = None
    list_ports = None


# ---------------------------------------------------------------------------
# Low level CAT stub --------------------------------------------------------
# ---------------------------------------------------------------------------
class FT897CAT:
    """Very small wrapper around the FT-897 CAT interface.

    Only the commands required by this demo are implemented.  The serial
    communication is extremely small and does not perform any retries.
    """

    MODE_MAP = {
        "LSB": 0x00,
        "USB": 0x01,
        "CW": 0x02,
        "CWR": 0x03,
        "AM": 0x04,
        "FM": 0x08,
        "DIG": 0x0A,
        "PKT": 0x0C,
        "FMN": 0x88,
    }

    def __init__(self) -> None:
        self.is_connected = False
        self.serial: Optional[serial.Serial] = None
        self.lock = threading.Lock()

    # --- connection -----------------------------------------------------
    def connect(self, port: str, baud: int) -> bool:
        if serial is None:
            return False
        try:
            self.serial = serial.Serial(port, baudrate=baud, timeout=0.5)
            self.is_connected = True
            return True
        except Exception:
            self.is_connected = False
            return False

    def disconnect(self) -> None:
        if self.serial:
            try:
                self.serial.close()
            except Exception:
                pass
        self.is_connected = False

    # --- primitive commands -------------------------------------------
    def _send(self, data: bytes) -> bool:
        if not self.serial:
            return False
        try:
            self.serial.write(data)
            self.serial.flush()
            time.sleep(0.05)
            return True
        except Exception:
            return False

    def ptt_on(self) -> None:
        self._send(b"\x00\x00\x00\x00\x08")

    def ptt_off(self) -> None:
        self._send(b"\x00\x00\x00\x00\x88")

    def set_frequency(self, hz: int) -> None:
        digits = f"{hz//10:08d}"  # 10Hz units
        bcd = bytes(int(digits[i:i+2]) for i in range(0, 8, 2))
        self._send(bcd + b"\x01")

    def set_mode(self, mode: str) -> None:
        code = FT897CAT.MODE_MAP.get(mode.upper())
        if code is not None:
            self._send(bytes([code, 0, 0, 0, 0x07]))

    def set_split(self, enable: bool) -> None:
        cmd = b"\x00\x00\x00\x00\x02" if enable else b"\x00\x00\x00\x00\x82"
        self._send(cmd)

    def set_repeater(self, direction: str) -> None:
        mapping = {"minus": 0x09, "plus": 0x49, "simplex": 0x89}
        code = mapping.get(direction, 0x89)
        self._send(bytes([code, 0, 0, 0, 0x09]))

    def set_offset(self, hz: int) -> None:
        hz = max(0, min(hz, 20_000_000))
        digits = f"{hz//10:08d}"
        bcd = bytes(int(digits[i:i+2]) for i in range(0, 8, 2))
        self._send(bcd + b"\xF9")


# ---------------------------------------------------------------------------
# GUI components ------------------------------------------------------------
# ---------------------------------------------------------------------------
class StatusThread(QThread):
    freq = pyqtSignal(int)

    def __init__(self, cat: FT897CAT) -> None:
        super().__init__()
        self.cat = cat
        self.running = False

    def run(self) -> None:  # pragma: no cover - GUI thread
        self.running = True
        while self.running:
            time.sleep(0.2)

    def stop(self) -> None:
        self.running = False


class MemoryDialog(QDialog):
    def __init__(self, items: List[Tuple[str, int, str]], parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Memory presets")
        layout = QVBoxLayout(self)
        self.listw = QListWidget(self)
        for label, freq, mode in items:
            item = QListWidgetItem(f"{label} – {freq/1_000_000:.4f} MHz {mode}")
            item.setData(Qt.UserRole, (freq, mode))
            self.listw.addItem(item)
        layout.addWidget(self.listw)
        self.listw.itemActivated.connect(self.accept)

    def selected(self) -> Optional[Tuple[int, str]]:
        item = self.listw.currentItem()
        return None if not item else item.data(Qt.UserRole)


class RadioControlApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cat = FT897CAT()
        self.status_thread = StatusThread(self.cat)

        self.setWindowTitle("FT-897 CAT Control")
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # connection row -------------------------------------------------
        conn = QHBoxLayout()
        self.port_combo = QComboBox()
        if list_ports:
            for p in list_ports.comports():
                self.port_combo.addItem(p.device)
        conn.addWidget(self.port_combo)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn.addWidget(self.connect_btn)
        layout.addLayout(conn)

        # frequency/PTT row ---------------------------------------------
        self.freq_label = QLabel("---")
        self.freq_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.freq_label)

        self.ptt_btn = QPushButton("PTT")
        self.ptt_btn.setCheckable(True)
        self.ptt_btn.pressed.connect(self.handle_ptt_on)
        self.ptt_btn.released.connect(self.handle_ptt_off)
        self.ptt_btn.setEnabled(False)
        layout.addWidget(self.ptt_btn)

        # timers --------------------------------------------------------
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(100)
        self.heartbeat.timeout.connect(self.cat.ptt_on)

        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.handle_ptt_off)

        # memory presets ------------------------------------------------
        self.memories: List[Tuple[str, int, str]] = [
            ("145.500 FM call", 145_500_000, "FM"),
            ("OK0AD repeater", 145_600_000, "FM"),
            ("433.500 FM call", 433_500_000, "FM"),
        ]

        # full band configuration table --------------------------------
        self.band_table: Dict[str, Dict[str, Tuple[int, int]]] = {
            "160 m": {"range": (1_800_000, 2_000_000), "step": 1_000, "mode": "LSB"},
            "80 m": {"range": (3_500_000, 3_800_000), "step": 1_000, "mode": "LSB"},
            "40 m": {"range": (7_000_000, 7_200_000), "step": 1_000, "mode": "LSB"},
            "30 m": {"range": (10_100_000, 10_150_000), "step": 1_000, "mode": "USB"},
            "20 m": {"range": (14_000_000, 14_350_000), "step": 1_000, "mode": "USB"},
            "17 m": {"range": (18_068_000, 18_168_000), "step": 1_000, "mode": "USB"},
            "15 m": {"range": (21_000_000, 21_450_000), "step": 1_000, "mode": "USB"},
            "12 m": {"range": (24_890_000, 24_990_000), "step": 1_000, "mode": "USB"},
            "10 m": {"range": (28_000_000, 29_700_000), "step": 1_000, "mode": "USB"},
            "6 m": {"range": (50_000_000, 52_000_000), "step": 1_000, "mode": "USB"},
            "2 m": {"range": (144_000_000, 146_000_000), "step": 1_000, "mode": "FM"},
            "70 cm": {"range": (430_000_000, 440_000_000), "step": 1_000, "mode": "FM"},
        }

        # memory table --------------------------------------------------
        self.mem_table = QTableWidget(0, 3)
        self.mem_table.setHorizontalHeaderLabels(["Label", "Freq MHz", "Mode"])
        self.mem_table.cellDoubleClicked.connect(self.tune_memory)
        layout.addWidget(self.mem_table)
        self.update_memory_table()

        self.status_thread.start()

    # ------------------------------------------------------------------
    # memory handling ---------------------------------------------------
    # ------------------------------------------------------------------
    def update_memory_table(self) -> None:
        self.mem_table.setRowCount(len(self.memories))
        for row, (label, freq, mode) in enumerate(self.memories):
            self.mem_table.setItem(row, 0, QTableWidgetItem(label))
            self.mem_table.setItem(row, 1, QTableWidgetItem(f"{freq/1_000_000:.4f}"))
            self.mem_table.setItem(row, 2, QTableWidgetItem(mode))

    def tune_memory(self, row: int, _col: int) -> None:
        freq = self.memories[row][1]
        mode = self.memories[row][2]
        self.cat.set_frequency(freq)
        self.cat.set_mode(mode)

    # ------------------------------------------------------------------
    # repeater utilities -------------------------------------------------
    # ------------------------------------------------------------------
    def plan_for_repeater(self, freq: int) -> Tuple[int, str, str]:
        if 50_000_000 <= freq <= 52_000_000:
            return 600_000, "minus", "FM"
        if 144_000_000 <= freq <= 146_000_000:
            return 600_000, "minus", "FM"
        if 430_000_000 <= freq <= 440_000_000:
            return 7_600_000, "minus", "FM"
        return 0, "simplex", "FM"

    # ------------------------------------------------------------------
    # connection and PTT -------------------------------------------------
    # ------------------------------------------------------------------
    def toggle_connection(self) -> None:
        if self.cat.is_connected:
            self.status_thread.stop()
            self.status_thread.wait()
            self.cat.disconnect()
            self.connect_btn.setText("Connect")
            self.ptt_btn.setEnabled(False)
            return

        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, "Error", "No serial port selected")
            return
        if self.cat.connect(port, 9600):
            self.connect_btn.setText("Disconnect")
            self.ptt_btn.setEnabled(True)
            self.status_thread.start()
        else:
            QMessageBox.critical(self, "Error", "Failed to open serial port")

    def handle_ptt_on(self) -> None:
        if not self.cat.is_connected:
            return
        self.cat.ptt_on()
        self.heartbeat.start()
        self.timeout.start(180_000)  # three minutes
        self.ptt_btn.setChecked(True)

    def handle_ptt_off(self) -> None:
        if not self.cat.is_connected:
            return
        self.heartbeat.stop()
        self.timeout.stop()
        self.cat.ptt_off()
        self.ptt_btn.setChecked(False)


# ---------------------------------------------------------------------------
# Main entry ----------------------------------------------------------------
# ---------------------------------------------------------------------------
def main() -> None:  # pragma: no cover - GUI application
    app = QApplication(sys.argv)
    win = RadioControlApp()
    win.resize(800, 600)
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()

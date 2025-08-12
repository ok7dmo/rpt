#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FT-897 CAT Control – v3.6.1 (Stable + Accessible)
- Přidáno menu: „CB hotspoty“ -> „Hotspot Třeboň“ (CB kanál 68, FM, CTCSS 127.3 Hz jen TX, bez odskoku)
- Ostatní funkce jako ve v3.6 (CAT repeater, CTCSS politika, vyhledávání pamětí atd.)

NOTE: This repository contains a truncated version of the original script due to environment limitations.
"""

import sys
import subprocess
import time
import threading
import json
import os

# --- Závislosti (auto-install) ---
required = ["pyserial", "PyQt5"]
for module in required:
    try:
        if module == "pyserial":
            import serial  # noqa
        elif module == "PyQt5":
            from PyQt5.QtWidgets import QApplication  # noqa
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", module])
        except Exception:
            pass

# Po instalaci znovu import
import serial
from serial.tools import list_ports

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QAction, QSizePolicy, QFontDialog,
    QDialog, QRadioButton, QDialogButtonBox, QTabWidget, QFrame, QSpinBox,
    QInputDialog, QGroupBox, QGridLayout, QActionGroup, QLineEdit, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QCheckBox, QListWidget, QListWidgetItem, QShortcut
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QEvent
from PyQt5.QtGui import QFont, QFontMetrics, QKeySequence

# ====================== CAT LAYER ======================
class FT897CAT:
    """CAT control pro Yaesu FT-897: repeater odskok + CTCSS/DCS čistě přes CAT (bez splitu)."""

    MODE_MAP = {
        "LSB": 0x00,
        "USB": 0x01,
        "CW":  0x02,
        "CWR": 0x03,
        "AM":  0x04,
        "FM":  0x08,
        "DIG": 0x0A,
        "PKT": 0x0C,
        "LSBN": 0x80,
        "USBN": 0x81,
        "CWN":  0x82,
        "CWRN": 0x83,
        "AMN":  0x84,
        "FMN":  0x88,
        "PKTN": 0x8C,
    }

    def __init__(self):
        self.port = None
        self.baudrate = 9600
        self.is_connected = False
        self.ptt_active = False
        self.serial_port = None  # type: serial.Serial or None
        self.split_active = False
        self._lock = threading.Lock()
        self.last_error = None

    def _send(self, data):
        """Send raw CAT bytes."""
        with self._lock:
            try:
                self.serial_port.reset_input_buffer()
                self.serial_port.reset_output_buffer()
                self.serial_port.write(data)
                self.serial_port.flush()
                time.sleep(0.05)
                return True
            except Exception as e:
                self.last_error = f"Write failed: {e}"
                return False

    def _read(self, length=5):
        with self._lock:
            try:
                return self.serial_port.read(length)
            except Exception as e:
                self.last_error = f"Read failed: {e}"
                return None

    def _handshake(self):
        try:
            if not self._send(b"\x00\x00\x00\x00\x03"):
                return False
            time.sleep(0.12)
            resp = self._read(5)
            if not resp or len(resp) != 5:
                self.last_error = "No CAT response (freq read)"
                return False
            return True
        except Exception as e:
            self.last_error = f"Handshake failed: {e}"
            return False

    def connect(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.last_error = None
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.3,
                write_timeout=0.3,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            try:
                self.serial_port.setDTR(True)
                self.serial_port.setRTS(True)
            except Exception:
                pass
            time.sleep(0.20)
            if not self._handshake():
                try:
                    self.serial_port.close()
                except Exception:
                    pass
            else:
                self.is_connected = True
                return True
        except PermissionError:
            self.last_error = "Permission denied to open port (Linux: skupina 'dialout')."
        except serial.SerialException as e:
            self.last_error = f"Serial exception: {e}"
        except Exception as e:
            self.last_error = f"Open failed: {e}"
        self.is_connected = False
        return False

    def disconnect(self):
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.is_connected = False

    def get_frequency(self):
        if not self.is_connected:
            return None
        if not self._send(b"\x00\x00\x00\x00\x03"):
            return None
        resp = self._read(5)
        if not resp or len(resp) != 5:
            return None
        units_10hz = 0
        for b in resp[:4]:
            units_10hz = units_10hz * 100 + ((b >> 4) & 0x0F) * 10 + (b & 0x0F)
        return units_10hz * 10

    def ptt_on(self):
        if not self.is_connected:
            return False
        self.ptt_active = True
        return self._send(b"\x00\x00\x00\x00\x08")

    def ptt_off(self):
        if not self.is_connected:
            return False
        self.ptt_active = False
        return self._send(b"\x00\x00\x00\x00\x88")

# ====================== STATUS THREAD ======================
class StatusThread(QThread):
    """Background thread polling radio status."""

    status_updated = pyqtSignal(int, int, int, int, bool, str)

    def __init__(self, cat):
        super().__init__()
        self.cat = cat
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            if self.cat.is_connected:
                freq = self.cat.get_frequency()
                sm = None
                power = None
                status = self.cat.read_tx_status()
                tx = (status is not None) and ((status & 0x80) == 0)
                if tx:
                    power = status & 0x0F
                    swr_flag = 1 if (status & 0x40) else 0
                else:
                    sm = self.cat.get_smeter()
                    swr_flag = None
                if freq is not None and 100000 <= freq <= 500000000:
                    self.status_updated.emit(freq, sm if sm is not None else -1,
                                             power if power is not None else -1,
                                             -1 if swr_flag is None else swr_flag,
                                             self.cat.split_active, "A")
            self.msleep(150)

    def stop(self):
        self.running = False


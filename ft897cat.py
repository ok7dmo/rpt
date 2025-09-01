#!/usr/bin/env python3
"""Simple FT-897 CAT demo with PTT safety timer.

This script is intentionally compact and focuses on demonstrating the PTT
heartbeat/timeout logic together with a complete band configuration table.
It avoids Python 3.10+ syntax so that it runs on older interpreters as well.
"""

from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FT897CAT(object):
    """Very small stub for the radio interface.

    Real CAT communication is outside the scope of this example.  We merely
    print to stdout to indicate that a command would have been sent.
    """

    def ptt_on(self) -> None:
        print("PTT ON")

    def ptt_off(self) -> None:
        print("PTT OFF")


class RadioControlApp(QMainWindow):
    """Demonstrates timer handling and band configuration for the FT-897."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FT-897 CAT Demo")
        self.cat = FT897CAT()

        # --- timers -------------------------------------------------------
        self.ptt_heartbeat = QTimer(self)
        self.ptt_heartbeat.setInterval(100)
        self.ptt_heartbeat.timeout.connect(self.cat.ptt_on)

        self.ptt_timeout = QTimer(self)
        self.ptt_timeout.setSingleShot(True)
        self.ptt_timeout.timeout.connect(self.handle_ptt_off)

        # --- band table ---------------------------------------------------
        # Full list of amateur bands supported by the FT-897.
        self.band_configs = {
            "160 m": {"range": (1_800_000, 2_000_000), "step": 1_000, "mode": "LSB"},
            "80 m":  {"range": (3_500_000, 3_800_000), "step": 1_000, "mode": "LSB"},
            "40 m":  {"range": (7_000_000, 7_200_000), "step": 1_000, "mode": "LSB"},
            "30 m":  {"range": (10_100_000, 10_150_000), "step": 1_000, "mode": "USB"},
            "20 m":  {"range": (14_000_000, 14_350_000), "step": 1_000, "mode": "USB"},
            "17 m":  {"range": (18_068_000, 18_168_000), "step": 1_000, "mode": "USB"},
            "15 m":  {"range": (21_000_000, 21_450_000), "step": 1_000, "mode": "USB"},
            "12 m":  {"range": (24_890_000, 24_990_000), "step": 1_000, "mode": "USB"},
            "10 m":  {"range": (28_000_000, 29_700_000), "step": 1_000, "mode": "USB"},
            "6 m":   {"range": (50_000_000, 52_000_000), "step": 1_000, "mode": "USB"},
            "2 m":   {"range": (144_000_000, 146_000_000), "step": 1_000, "mode": "FMN"},
            "70 cm": {"range": (430_000_000, 440_000_000), "step": 1_000, "mode": "FM"},
        }

        # --- minimal GUI --------------------------------------------------
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.info_label = QLabel("PTT OFF", alignment=Qt.AlignCenter)
        layout.addWidget(self.info_label)

        self.ptt_button = QPushButton("PTT", self)
        self.ptt_button.setCheckable(True)
        self.ptt_button.pressed.connect(self.handle_ptt_on)
        self.ptt_button.released.connect(self.handle_ptt_off)
        layout.addWidget(self.ptt_button)

    # ------------------------------------------------------------------
    def handle_ptt_on(self) -> None:
        """Enable PTT and start safety timers."""
        self.cat.ptt_on()
        self.info_label.setText("PTT ON")
        self.ptt_heartbeat.start()
        self.ptt_timeout.start(180_000)  # auto-release after three minutes

    def handle_ptt_off(self) -> None:
        """Release PTT and stop timers."""
        self.ptt_heartbeat.stop()
        self.ptt_timeout.stop()
        self.cat.ptt_off()
        self.info_label.setText("PTT OFF")


def main() -> None:
    app = QApplication([])
    win = RadioControlApp()
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()

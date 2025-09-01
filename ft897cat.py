from PyQt5.QtCore import QTimer

class FT897CAT:
    """Minimal stub representing CAT commands."""
    def ptt_on(self):
        print("PTT ON")
    def ptt_off(self):
        print("PTT OFF")

class RadioControlApp:
    """Demonstrates timer handling and band configuration for FT-897."""
    def __init__(self):
        self.cat = FT897CAT()
        # Heartbeat keeps PTT asserted; interval in milliseconds
        self.ptt_heartbeat = QTimer()
        self.ptt_heartbeat.setInterval(100)
        self.ptt_heartbeat.timeout.connect(self.cat.ptt_on)
        # Timeout releases PTT after a safety period
        self.ptt_timeout = QTimer()
        self.ptt_timeout.setSingleShot(True)
        self.ptt_timeout.timeout.connect(self.handle_ptt_off)
        # Full list of amateur bands supported by the FT-897
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

    def handle_ptt_on(self):
        """Enable PTT and start safety timers."""
        self.cat.ptt_on()
        self.ptt_heartbeat.start(100)       # ensure heartbeat interval
        self.ptt_timeout.start(180_000)     # auto-release after 3 minutes

    def handle_ptt_off(self):
        """Release PTT and stop timers."""
        self.ptt_heartbeat.stop()
        self.cat.ptt_off()
        self.ptt_timeout.stop()

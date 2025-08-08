import threading
import time

class FT897CAT:
    """CAT control for Yaesu FT-897 with native repeater support."""

    MODE_MAP = {
        "LSB": 0x00,
        "USB": 0x01,
        "CW": 0x02,
        "CWR": 0x03,
        "AM": 0x04,
        "FM": 0x08,
        "DIG": 0x06,
    }

    def __init__(self, serial_port=None):
        self.serial_port = serial_port
        self.is_connected = serial_port is not None
        self._lock = threading.Lock()

    # --- low level helpers -------------------------------------------------
    def _send(self, data: bytes) -> bool:
        try:
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            self.serial_port.write(data)
            self.serial_port.flush()
            time.sleep(0.05)
            return True
        except Exception:
            return False

    def set_frequency(self, freq_hz: int) -> bool:
        units_10hz = int(freq_hz // 10)
        digits = f"{units_10hz:08d}"
        bcd = bytearray((int(digits[i]) << 4) | int(digits[i + 1]) for i in range(0, 8, 2))
        return self._send(bytes(bcd) + b"\x01")

    def set_mode(self, mode: str) -> bool:
        code = self.MODE_MAP.get(mode)
        if code is None:
            return False
        return self._send(bytes([code, 0, 0, 0, 0x07]))

    def set_repeater_offset_mode(self, mode: str) -> bool:
        mapping = {"minus": 0x09, "plus": 0x49, "simplex": 0x89}
        code = mapping.get(mode)
        if code is None:
            return False
        return self._send(bytes([code, 0, 0, 0, 0x09]))

    def set_repeater_offset_frequency(self, freq_hz: int) -> bool:
        units_10hz = int(freq_hz // 10)
        digits = f"{units_10hz:08d}"
        bcd = bytearray((int(digits[i]) << 4) | int(digits[i + 1]) for i in range(0, 8, 2))
        bcd.append(0xF9)
        return self._send(bytes(bcd))

    def set_ctcss_tone(self, tone_hz: float) -> bool:
        tone_tenths = int(round(tone_hz * 10))
        digits = f"{tone_tenths:04d}"
        bcd = bytearray((int(digits[i]) << 4) | int(digits[i + 1]) for i in range(0, 4, 2))
        cmd = bcd + bcd + b"\x0B"
        return self._send(bytes(cmd))

    def set_ctcss_dcs_mode(self, mode: str) -> bool:
        mapping = {
            "off": b"\x8A\x00\x00\x00\x0A",
            "ctcss_enc": b"\x4A\x00\x00\x00\x0A",
        }
        cmd = mapping.get(mode)
        return self._send(cmd) if cmd else False

    def split_off(self) -> bool:
        return self._send(b"\x00\x00\x00\x00\x82")

    # --- new high level helper --------------------------------------------
    def configure_repeater(self, rx_freq_hz: int, offset_hz: int, direction: str,
                           tone: float | None = None, mode: str = "FM") -> bool:
        """Configure radio for repeater operation using native offset commands.

        Parameters
        ----------
        rx_freq_hz: int
            Repeater output frequency in Hz (radio receives here).
        offset_hz: int
            Repeater offset in Hz, e.g. 600_000 for 2 m or 7_600_000 for 70 cm.
        direction: str
            'plus', 'minus' or 'simplex'.
        tone: float | None
            Optional CTCSS tone in Hz. If ``None`` CTCSS is disabled.
        mode: str
            Operating mode, default 'FM'.
        """
        if not self.is_connected:
            return False
        self.split_off()  # ensure split disabled
        if not self.set_frequency(rx_freq_hz):
            return False
        self.set_mode(mode)
        self.set_repeater_offset_frequency(offset_hz)
        self.set_repeater_offset_mode(direction)
        if tone:
            if not self.set_ctcss_tone(tone):
                return False
            self.set_ctcss_dcs_mode("ctcss_enc")
        else:
            self.set_ctcss_dcs_mode("off")
        return True

    # Example convenience wrapper for Czech repeaters
    def configure_czech_repeater(self, rx_freq_hz: int, band: str,
                                 tone: float | None = None, mode: str = "FM") -> bool:
        offsets = {"2m": 600_000, "70cm": 7_600_000}
        offset = offsets.get(band)
        if offset is None:
            raise ValueError("Unknown band")
        return self.configure_repeater(rx_freq_hz, offset, "minus", tone, mode)

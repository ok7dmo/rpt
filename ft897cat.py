"""Minimal CAT control driver for Yaesu FT-897 used by the web server.

The original desktop application pulls in a long list of dependencies.  For
the lightweight web version we only need the ``pyserial`` package to talk to
the radio.  Users sometimes try to run the server without having pyserial
installed which previously caused an immediate crash during import.

To make the web server start even without pyserial, the import is wrapped in a
try/except block.  Connection attempts will then fail gracefully with an error
message rather than raising ``ModuleNotFoundError``.
"""

try:  # pragma: no cover - optional dependency
    import serial  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    serial = None  # type: ignore

import time
import threading


class FT897CAT:
    """Simple CAT control for the Yaesu FT-897 transceiver.

    Only a subset of the original desktop application's functionality is
    implemented here.  It is enough for frequency control, reading status and
    basic PTT handling which are exposed through the FastAPI web server.
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
    }

    def __init__(self):
        self.port = None
        self.baudrate = 9600
        self.is_connected = False
        self.serial_port = None
        self._lock = threading.Lock()
        self.last_error = None

    # ---- low level helpers -------------------------------------------------
    def _send(self, data: bytes) -> bool:
        """Send raw CAT command bytes to the radio."""
        with self._lock:
            try:
                self.serial_port.reset_input_buffer()
                self.serial_port.reset_output_buffer()
                self.serial_port.write(data)
                self.serial_port.flush()
                time.sleep(0.05)
                return True
            except Exception as e:  # pragma: no cover - serial errors
                self.last_error = f"Write failed: {e}"
                return False

    def _read(self, length: int = 5) -> bytes | None:
        with self._lock:
            try:
                return self.serial_port.read(length)
            except Exception as e:  # pragma: no cover - serial errors
                self.last_error = f"Read failed: {e}"
                return None

    def _handshake(self) -> bool:
        try:
            if not self._send(b"\x00\x00\x00\x00\x03"):
                return False
            time.sleep(0.12)
            resp = self._read(5)
            if not resp or len(resp) != 5:
                self.last_error = "No CAT response (freq read)"
                return False
            return True
        except Exception as e:  # pragma: no cover - serial errors
            self.last_error = f"Handshake failed: {e}"
            return False

    # ---- connection --------------------------------------------------------
    def connect(self, port: str, baudrate: int = 9600) -> bool:
        if serial is None:  # pragma: no cover - depends on environment
            self.last_error = "pyserial is not installed"
            return False

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
            self.last_error = "Permission denied to open port"
        except serial.SerialException as e:
            self.last_error = f"Serial exception: {e}"
        except Exception as e:  # pragma: no cover
            self.last_error = f"Open failed: {e}"
        self.is_connected = False
        return False

    def disconnect(self) -> None:
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.is_connected = False

    # ---- basic status ------------------------------------------------------
    def get_frequency(self) -> int | None:
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

    def get_smeter(self) -> int | None:
        if not self.is_connected:
            return None
        with self._lock:
            try:
                self.serial_port.reset_input_buffer()
                self.serial_port.reset_output_buffer()
                self.serial_port.write(b"\x00\x00\x00\x00\xe7")
                time.sleep(0.1)
                resp = self.serial_port.read(1)
            except Exception:  # pragma: no cover - serial errors
                return None
        if not resp:
            return None
        return resp[0] & 0x0F

    def read_tx_status(self) -> int | None:
        if not self.is_connected:
            return None
        if not self._send(b"\x00\x00\x00\x00\xf7"):
            return None
        resp = self._read(1)
        if not resp:
            return None
        return resp[0]

    # ---- PTT ----------------------------------------------------------------
    def ptt_on(self) -> bool:
        if not self.is_connected:
            return False
        return self._send(b"\x00\x00\x00\x00\x08")

    def ptt_off(self) -> bool:
        if not self.is_connected:
            return False
        return self._send(b"\x00\x00\x00\x00\x88")

    # ---- Tuning / mode ------------------------------------------------------
    def set_frequency(self, freq_hz: int) -> bool:
        if not self.is_connected:
            return False
        units_10hz = int(freq_hz // 10)
        digits = f"{units_10hz:08d}"
        bcd = bytearray()
        for i in range(0, 8, 2):
            bcd.append((int(digits[i]) << 4) | int(digits[i + 1]))
        return self._send(bytes(bcd) + b"\x01")

    def set_mode(self, mode: str) -> bool:
        if not self.is_connected:
            return False
        code = self.MODE_MAP.get(mode)
        if code is None:
            return False
        cmd = bytes([code, 0x00, 0x00, 0x00, 0x07])
        return self._send(cmd)


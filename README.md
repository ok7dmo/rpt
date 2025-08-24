# FT-897 Web Control

This repository provides a minimal FastAPI based web server to control a Yaesu
FT-897 transceiver over its CAT interface.  It exposes a handful of HTTP
endpoints for connection management, frequency tuning and PTT control and comes
with a very small HTML frontend.

## Usage

Install dependencies and start the server:

```bash
pip install fastapi uvicorn pyserial
uvicorn app:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.  If
`pyserial` is missing the server will still start, but attempts to connect to
the radio will fail with a clear error message.

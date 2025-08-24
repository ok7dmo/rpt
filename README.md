# FT-897 Web Control

This repository provides a minimal FastAPI based web server to control a Yaesu
FT-897 transceiver over its CAT interface.  It exposes a handful of HTTP
endpoints for connection management, frequency tuning and PTT control and comes
with a very small HTML frontend.

## Usage

```bash
uvicorn app:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.  The
server relies on the `serial` module to talk to the radio; make sure the CAT
interface is connected and accessible.

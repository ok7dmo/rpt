from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ft897cat import FT897CAT

app = FastAPI(title="FT-897 Web Control")

# expose static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

# template renderer
templates = Jinja2Templates(directory="templates")

# global CAT instance
radio = FT897CAT()


class ConnectRequest(BaseModel):
    port: str
    baudrate: int = 9600


class FrequencyRequest(BaseModel):
    frequency: int


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    freq = radio.get_frequency() if radio.is_connected else None
    return templates.TemplateResponse(
        "index.html", {"request": request, "frequency": freq}
    )


@app.post("/connect")
async def connect(req: ConnectRequest):
    if radio.connect(req.port, req.baudrate):
        return {"status": "connected"}
    raise HTTPException(status_code=400, detail=radio.last_error or "Failed to connect")


@app.post("/disconnect")
async def disconnect():
    radio.disconnect()
    return {"status": "disconnected"}


@app.get("/status")
async def status():
    if not radio.is_connected:
        raise HTTPException(400, detail="Radio not connected")
    freq = radio.get_frequency()
    sm = radio.get_smeter()
    tx = radio.read_tx_status()
    return {"frequency": freq, "smeter": sm, "tx_status": tx}


@app.get("/frequency")
async def get_frequency():
    freq = radio.get_frequency()
    if freq is None:
        raise HTTPException(400, detail="Radio not connected")
    return {"frequency": freq}


@app.post("/frequency")
async def set_frequency(req: FrequencyRequest):
    if radio.set_frequency(req.frequency):
        return {"status": "ok"}
    raise HTTPException(400, detail="Failed to set frequency")


@app.post("/ptt/on")
async def ptt_on():
    if radio.ptt_on():
        return {"status": "tx"}
    raise HTTPException(400, detail="PTT failed")


@app.post("/ptt/off")
async def ptt_off():
    if radio.ptt_off():
        return {"status": "rx"}
    raise HTTPException(400, detail="PTT failed")


# Convenience: run with `uvicorn app:app --reload`

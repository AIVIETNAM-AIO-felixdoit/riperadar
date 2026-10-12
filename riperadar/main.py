from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .advisor import make_plan  # noqa: E402
from .classifier import get_classifier  # noqa: E402
from .pipeline import scan  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="RipeRadar")


@app.on_event("startup")
async def warm_up():
    # Load CLIP once at boot so the first scan in the demo is fast
    await run_in_threadpool(get_classifier)


@app.post("/api/scan")
async def api_scan(image: UploadFile = File(...), storage: str = Form("counter")):
    data = await image.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Image too large")
    storage = "fridge" if storage == "fridge" else "counter"
    try:
        result = await run_in_threadpool(scan, data, storage)
    except ValueError as e:
        raise HTTPException(400, str(e))
    result["plan"] = await run_in_threadpool(make_plan, result["items"], storage)
    return result


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")

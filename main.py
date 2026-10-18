"""Serve the built dashboard. Builds dist/ on startup if it is missing.

Run:  uvicorn main:app --port 8080     (or: python3 main.py)
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import build

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# All app code is in external files, so scripts need no 'unsafe-inline'.
# Styles keep it because the UI sets per-element style attributes.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'none'"
)

if not (DIST / "data.json").exists():
    build.main([])

app = FastAPI(docs_url=None, redoc_url=None)


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.endswith(".json"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/health")
def health():
    return {"status": "ok", "version": (ROOT / "VERSION").read_text().strip()}


@app.get("/api/ar")
def api_ar():
    return FileResponse(DIST / "data.json", media_type="application/json")


@app.post("/api/rebuild")
def rebuild():
    """Re-run the connector. Disabled unless AR_ALLOW_REBUILD=1 (no auth on this endpoint)."""
    if os.environ.get("AR_ALLOW_REBUILD") != "1":
        return JSONResponse({"error": "rebuild disabled"}, status_code=403)
    code = build.main([])
    return JSONResponse({"ok": code == 0}, status_code=200 if code == 0 else 500)


app.mount("/", StaticFiles(directory=DIST, html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

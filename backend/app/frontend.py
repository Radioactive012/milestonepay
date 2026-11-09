"""Serve the built React screens from the same server as the API, so the app is one website."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def mount_frontend(app: FastAPI, dist: Path = FRONTEND_DIST) -> bool:
    """Add the screens to the app if they've been built (`npm run build`). Call after all API routes."""
    dist = dist.resolve()
    if not (dist / "index.html").is_file():
        return False
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def screens(path: str):
        # unknown API addresses get a normal 404, not the web page
        if path.startswith(("api/", "webhooks/")):
            raise HTTPException(status_code=404, detail="Not found")
        file = (dist / path).resolve()
        if path and file.is_file() and dist in file.parents:
            return FileResponse(file)
        # every other address (/, /portal/<link>) is handled by the React app
        return FileResponse(dist / "index.html")

    return True

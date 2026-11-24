"""Serve the built React app from FastAPI (production / Docker only).

In development the React app runs on the Vite dev server, which proxies /api
to FastAPI, so none of this is used. In the Docker image the frontend is built
ahead of time and FastAPI serves it from the same origin as the API, which
keeps the session cookie first-party and removes the need for CORS.

This module is enabled only when FRONTEND_DIST_DIR is set.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# First URL segments that belong to the backend. A request below one of these
# that matches no real route must stay a JSON 404 and must never be answered
# with the React index.html.
BACKEND_PREFIXES = frozenset({"api", "health", "docs", "redoc", "openapi.json"})


def mount_frontend(application: FastAPI, dist_dir: Path) -> None:
    """Serve the built frontend in dist_dir and fall back to index.html.

    Call this AFTER every API router has been included: routes are matched in
    registration order, and the catch-all below must be the last one.
    """
    dist = dist_dir.expanduser().resolve()
    index_file = dist / "index.html"
    assets_dir = dist / "assets"

    if not index_file.is_file() or not assets_dir.is_dir():
        # Fail at startup rather than serving a broken site.
        raise RuntimeError(
            f"FRONTEND_DIST_DIR={dist} does not contain a built frontend "
            "(index.html and assets/ are required)."
        )

    # Hashed JS/CSS bundles produced by Vite.
    application.mount(
        "/assets",
        StaticFiles(directory=assets_dir),
        name="frontend-assets",
    )

    @application.api_route(
        "/{full_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    def serve_frontend(full_path: str) -> FileResponse:
        first_segment = full_path.split("/", 1)[0]
        if first_segment in BACKEND_PREFIXES:
            raise HTTPException(status_code=404, detail="Not Found")

        # Top-level files such as favicon.svg and robots.txt.
        if full_path:
            try:
                candidate = (dist / full_path).resolve()
                if candidate.is_file() and candidate.is_relative_to(dist):
                    return FileResponse(candidate)
            except (OSError, ValueError):
                pass

            # A missing file (for example /logo.png) is a real 404, not a
            # React route.
            if Path(full_path).suffix:
                raise HTTPException(status_code=404, detail="Not Found")

        # Any other path is a client-side React route (/contracts/123 ...).
        # no-cache makes browsers pick up the new bundle names after a deploy.
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

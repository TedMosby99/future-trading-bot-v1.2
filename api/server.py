"""
api/server.py
FastAPI application. Mounts all API routes and serves the UI.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.routes import bot, settings, positions, stats

app = FastAPI(title="TradingBot API", version="1.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bot.router,       prefix="/api")
app.include_router(settings.router,  prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(stats.router,     prefix="/api")


@app.get("/", include_in_schema=False)
async def serve_ui():
    return FileResponse("ui/index.html")

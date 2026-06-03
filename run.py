"""
run.py
Entry point. Starts the FastAPI server which serves both the API and the web UI.

Usage:
    python run.py

Then open: http://localhost:8000
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Verify setup has been run
if not os.path.exists("data/trades.db"):
    print("[ERROR] Database not found. Run: python setup.py")
    sys.exit(1)

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    print(f"\n{'='*50}")
    print(f"  Trading Bot")
    print(f"  UI → http://localhost:{port}")
    print(f"  API docs → http://localhost:{port}/api/docs")
    print(f"{'='*50}\n")

    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
    )

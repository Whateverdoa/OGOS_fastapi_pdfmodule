from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.endpoints import pdf
import os
import subprocess
import time

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description
)
START_TIME = time.time()

def _git_commit_short() -> str:
    # Prefer env var if provided
    commit = os.getenv("GIT_COMMIT")
    if commit:
        return commit[:7]
    # Try git command
    try:
        out = subprocess.run([
            "git", "rev-parse", "--short", "HEAD"
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return out.stdout.decode().strip()
    except Exception:
        return "unknown"

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Include routers
app.include_router(pdf.router)


@app.get("/")
async def root():
    return {
        "message": "PDF Dieline Processor API",
        "version": settings.api_version,
        "endpoints": {
            "analyze": "/api/pdf/analyze",
            "process": "/api/pdf/process",
            "process_with_json": "/api/pdf/process-with-json-file"
        }
    }


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }


@app.get("/version")
async def version():
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "git_commit": _git_commit_short(),
    }

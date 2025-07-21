from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.endpoints import pdf

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description
)

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

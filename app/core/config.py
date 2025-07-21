from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # API Settings
    api_title: str = "PDF Dieline Processor"
    api_version: str = "1.0.0"
    api_description: str = "FastAPI service for processing PDF dielines/stanslines"
    
    # File Settings
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    allowed_file_types: list = [".pdf", ".PDF"]
    temp_dir: str = "/tmp/pdf_processor"
    
    # Processing Settings
    default_spot_color: str = "stans"
    default_line_thickness: float = 0.5
    default_magenta_value: float = 1.0  # 100% magenta
    
    # CORS Settings
    cors_origins: list = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
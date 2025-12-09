import os
import shutil
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from ..core.config import settings

logger = logging.getLogger(__name__)

class FileManager:
    """
    Manages storage and cleanup of PDF files.
    """
    
    def __init__(self):
        self.storage_root = Path(settings.storage_dir)
        self.original_dir = self.storage_root / "original"
        self.processed_dir = self.storage_root / "processed"
        self.retention_days = settings.retention_days
        
        # Ensure directories exist
        self.original_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def save_original(self, file_path: str, filename: str) -> str:
        """
        Save a copy of the original uploaded file.
        
        Args:
            file_path: Path to the temporary uploaded file
            filename: Original filename
            
        Returns:
            Path to the saved file
        """
        try:
            # Add timestamp to filename to avoid collisions and track time
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{filename}"
            dest_path = self.original_dir / safe_filename
            
            shutil.copy2(file_path, dest_path)
            logger.info(f"Saved original file to {dest_path}")
            return str(dest_path)
        except Exception as e:
            logger.error(f"Failed to save original file: {e}")
            return ""

    def save_processed(self, file_path: str, filename: str) -> str:
        """
        Save a copy of the processed file.
        
        Args:
            file_path: Path to the processed file
            filename: Desired filename
            
        Returns:
            Path to the saved file
        """
        try:
            # Add timestamp if not already present (though processed files usually have unique names)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{filename}"
            dest_path = self.processed_dir / safe_filename
            
            shutil.copy2(file_path, dest_path)
            logger.info(f"Saved processed file to {dest_path}")
            return str(dest_path)
        except Exception as e:
            logger.error(f"Failed to save processed file: {e}")
            return ""

    def cleanup_old_files(self) -> int:
        """
        Delete files older than retention_days.
        
        Returns:
            Number of deleted files
        """
        deleted_count = 0
        cutoff_time = time.time() - (self.retention_days * 86400)
        
        for directory in [self.original_dir, self.processed_dir]:
            if not directory.exists():
                continue
                
            for file_path in directory.glob("*"):
                if not file_path.is_file():
                    continue
                    
                try:
                    # Check modification time
                    if file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted old file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {e}")
                    
        return deleted_count

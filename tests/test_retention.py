import os
import shutil
import time
import pytest
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from fastapi.testclient import TestClient
from main import app
from app.core.config import settings
from app.utils.file_manager import FileManager

client = TestClient(app)

# Mock storage dir for testing
TEST_STORAGE_DIR = "test_pdf_storage"

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup
    original_storage = settings.storage_dir
    settings.storage_dir = TEST_STORAGE_DIR
    
    # Create test dirs
    Path(TEST_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    
    yield
    
    # Teardown
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR)
    settings.storage_dir = original_storage

def test_pdf_retention_flow():
    # 1. Create a dummy PDF
    pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Kids [3 0 R]\n/Count 1\n/Type /Pages\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/MediaBox [0 0 595 842]\n/Resources <<\n/Font <<\n/F1 4 0 R\n>>\n>>\n/Parent 2 0 R\n/Contents 5 0 R\n>>\nendobj\n4 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\n5 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 24 Tf\n100 100 Td\n(Hello World) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000010 00000 n\n0000000060 00000 n\n0000000157 00000 n\n0000000304 00000 n\n0000000392 00000 n\ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n487\n%%EOF"
    
    files = {
        'pdf_file': ('test.pdf', pdf_content, 'application/pdf')
    }
    data = {
        'job_config': '{"reference":"test_ref","shape":"circle","width":100,"height":100}'
    }
    
    # 2. Upload and process
    response = client.post("/api/pdf/process", files=files, data=data)
    assert response.status_code == 200
    
    # 3. Verify files exist in storage
    fm = FileManager()
    # Re-init with test settings
    fm.storage_root = Path(TEST_STORAGE_DIR)
    fm.original_dir = fm.storage_root / "original"
    fm.processed_dir = fm.storage_root / "processed"
    
    originals = list(fm.original_dir.glob("*"))
    processed = list(fm.processed_dir.glob("*"))
    
    assert len(originals) >= 1
    assert len(processed) >= 1
    print(f"Originals found: {[f.name for f in originals]}")
    print(f"Processed found: {[f.name for f in processed]}")

def test_cleanup_logic():
    # 1. Create old files
    fm = FileManager()
    fm.storage_root = Path(TEST_STORAGE_DIR)
    fm.original_dir = fm.storage_root / "original"
    fm.processed_dir = fm.storage_root / "processed"
    
    fm.original_dir.mkdir(parents=True, exist_ok=True)
    
    old_file = fm.original_dir / "old_file.pdf"
    old_file.touch()
    
    # Set mtime to 8 days ago
    eight_days_ago = time.time() - (8 * 86400)
    os.utime(old_file, (eight_days_ago, eight_days_ago))
    
    new_file = fm.original_dir / "new_file.pdf"
    new_file.touch()
    
    # 2. Run cleanup
    deleted = fm.cleanup_old_files()
    
    # 3. Verify
    assert deleted == 1
    assert not old_file.exists()
    assert new_file.exists()

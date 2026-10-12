import os
import uuid

from backend.app.config import settings
from backend.app.deps import get_ingestor, get_current_user
from backend.core.schemas import IngestJob
from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

from backend.retrieval.index import get_indexer
from backend.core import db

def process_file(temp_path: str, original_filename: str, file_id: str, storage_id: str, job_id: str, ingestor, processing_preference: str = "mixed", pii_mode: str = "STRICT", uploader_role: str = "L1", uploader_name: str = "L1_Analyst", content_hash: str = None):
    try:
        db.update_ingestion_job(job_id, status="PROCESSING", stage="Parsing and extracting regions...", progress=10.0)
        chunks = ingestor.ingest(temp_path, original_filename, file_id, storage_id, processing_preference=processing_preference, pii_mode=pii_mode, uploader_role=uploader_role, uploader_name=uploader_name, content_hash=content_hash)
        
        # Move temp file to final location safely
        final_path = os.path.join(settings.upload_dir, storage_id)
        import shutil
        shutil.move(temp_path, final_path)
        
        # Clean up temp dir
        temp_dir = os.path.dirname(temp_path)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        text_count = sum(1 for c in chunks if c.content_type.value == "text")
        table_count = sum(1 for c in chunks if c.content_type.value == "table")
        image_count = sum(1 for c in chunks if c.content_type.value == "image")
        
        db.update_ingestion_job(
            job_id, 
            status="COMPLETED", 
            stage="Ready for Review", 
            progress=100.0,
            job_data={
                "chunk_count": len(chunks),
                "region_counts": {
                    "text": text_count,
                    "tables": table_count,
                    "images": image_count,
                    "charts": 0,
                    "ocr": 0
                }
            }
        )
    except Exception as e:
        db.update_ingestion_job(
            job_id,
            status="ERROR",
            stage=str(e),
            error_summary=str(e)
        )
        print(e)
        
        # 1. Clean up the newly uploaded temporary file and temp directory
        temp_dir = os.path.dirname(temp_path)
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        # Assets cleanup could go here if needed
        # But staging makes it safer

from fastapi import Form, Header, HTTPException
from typing import Optional

MAX_FILE_SIZE = 50 * 1024 * 1024 # 50 MB

@router.post("/upload", response_model=IngestJob)
async def upload(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...), 
    processing_preference: str = Form("mixed"),
    pii_mode: str = Form("STRICT"),
    document_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
    ingestor = Depends(get_ingestor)
):
    x_user_role = user["role"]
    x_user_name = user["name"]
    file_bytes = await file.read()
    
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")
        
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")
        
    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid file format. Not a PDF.")
        
    import fitz
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if doc.page_count < 1:
            raise Exception("No pages found")
        doc.close()
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed or corrupted PDF file.")
        
    job_id = str(uuid.uuid4())
    import hashlib
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    
    from backend.core import db
    if not document_id:
        existing = db.get_document_by_hash(content_hash)
        if existing:
            # Intentional deduplication policy
            raise HTTPException(status_code=409, detail=f"Exact document content already exists (ID: {existing['file_id']}).")
        
        file_id = str(uuid.uuid4()) # Logical document ID
    else:
        existing_doc = db.get_document(document_id)
        if not existing_doc:
            raise HTTPException(status_code=404, detail="Document ID to replace not found.")
        file_id = document_id
        
        # We must verify we can replace it here before saving file
        if existing_doc['status'] in ['PENDING_REVIEW', 'APPROVING', 'PROCESSING']:
            raise HTTPException(status_code=409, detail=f"Cannot replace document while it is in {existing_doc['status']} state.")

    storage_id = str(uuid.uuid4()) # Safe server-side storage name for physical file
    
    temp_dir = os.path.join(settings.upload_dir, job_id)
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, storage_id)
    
    with open(temp_path, "wb") as f:
        f.write(file_bytes)
        
    job_data = {
        "files": [file.filename],
        "chunk_count": 0
    }
    db.create_ingestion_job(job_id, file_id, storage_id, job_data)
    
    background_tasks.add_task(process_file, temp_path, file.filename, file_id, storage_id, job_id, ingestor, processing_preference, pii_mode, x_user_role, x_user_name, content_hash)
    
    return IngestJob(
        job_id=job_id,
        status="queued",
        stage="started",
        files=[file.filename],
        chunk_count=0
    )

@router.get("/status/{job_id}", response_model=IngestJob)
def status(job_id: str):
    job = db.get_ingestion_job(job_id)
    if not job:
        return IngestJob(
            job_id=job_id,
            status="not_found",
            stage="",
            files=[],
            chunk_count=0
        )
        
    job_data = {}
    import json
    if job.get('job_data'):
        job_data = json.loads(job['job_data'])
        
    return IngestJob(
        job_id=job['job_id'],
        status=job['status'].lower(),
        stage=job['stage'] or "",
        files=job_data.get('files', []),
        chunk_count=job_data.get('chunk_count', 0),
        region_counts=job_data.get('region_counts', None)
    )

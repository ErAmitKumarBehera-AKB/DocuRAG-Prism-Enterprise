import hashlib
import os
import re
from typing import List

from backend.core.interfaces import Ingestor
from backend.core.schemas import EvidenceChunk
from backend.ingest.parser import parse_document
from backend.retrieval.index import get_indexer
from backend.core import db

def redact_pii(text: str) -> str:
    if not text:
        return text
    # Redact Emails
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED EMAIL]', text)
    # Redact SSNs (simple pattern: XXX-XX-XXXX)
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED SSN]', text)
    # Redact Phones (simple US pattern)
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED PHONE]', text)
    return text

class RealIngestor(Ingestor):
    def ingest(self, path: str, original_filename: str, file_id: str, storage_id: str, processing_preference: str = "mixed", pii_mode: str = "STRICT", uploader_role: str = "L1", uploader_name: str = "L1_Analyst", content_hash: str = None) -> List[EvidenceChunk]:
        # Hash the file
        with open(path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
            
        # 1. Create document in SQLite DB
        import sqlite3
        try:
            db.create_document(file_id, original_filename, pii_mode, uploaded_by=uploader_name, staging_storage_id=storage_id, content_hash=content_hash)
        except sqlite3.IntegrityError as e:
            raise Exception("Duplicate upload detected concurrently.") from e
        
        temp_asset_dir = os.path.dirname(path)
        
        # 2. Parse document
        try:
            chunks = parse_document(path, file_id, storage_id, temp_asset_dir, processing_preference, pii_mode)
        except Exception as e:
            db.update_document_status(file_id, "FAILED", "System", "SYSTEM", "FAILED", f"Parsing error: {str(e)}")
            raise e
        
        # 3. Apply PII Masking if Strict
        if pii_mode == "STRICT":
            for c in chunks:
                c.text = redact_pii(c.text)
        
        # 4. Assign file_hash
        for c in chunks:
            c.file_hash = file_hash
            
        # 5. Save staging chunks and immediately index for real-time querying across the workspace
        try:
            db.save_staging_chunks(file_id, chunks)
            indexer = get_indexer()
            indexer.add(chunks)
            db.update_document_status(
                file_id, 
                "APPROVED", 
                uploader_name, 
                uploader_role, 
                "EXTRACTION_AND_INDEXED", 
                f"Extracted {len(chunks)} chunks and indexed into knowledge base."
            )
        except Exception as e:
            db.update_document_status(file_id, "FAILED", "System", "SYSTEM", "FAILED", f"Indexing error: {str(e)}")
            raise e
            
        import shutil
        from backend.app.config import settings
        
        # Move generated images to the real asset_dir
        for f_name in os.listdir(temp_asset_dir):
            if f_name.startswith(f"{file_id}_"):
                src = os.path.join(temp_asset_dir, f_name)
                # Ensure we only move files, not directories
                if os.path.isfile(src) and f_name != file_id:
                    shutil.move(src, os.path.join(settings.asset_dir, f_name))
        
        return chunks

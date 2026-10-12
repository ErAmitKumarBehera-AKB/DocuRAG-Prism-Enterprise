import json
import sqlite3
import os
from datetime import datetime, timezone
from typing import List, Dict, Any
from backend.app.config import settings

DB_PATH = settings.cache_db.replace("sqlite:///", "")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            file_id TEXT PRIMARY KEY,
            filename TEXT,
            status TEXT,
            uploaded_at TEXT,
            uploaded_by TEXT,
            pii_mode TEXT,
            version INTEGER DEFAULT 1,
            staging_storage_id TEXT,
            active_storage_id TEXT,
            content_hash TEXT
        )
    """)
    # Add columns for existing DBs safely
    try:
        c.execute("ALTER TABLE documents ADD COLUMN staging_storage_id TEXT")
        c.execute("ALTER TABLE documents ADD COLUMN active_storage_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_content_hash ON documents(content_hash) WHERE content_hash IS NOT NULL")
    except sqlite3.OperationalError:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            version INTEGER,
            actor TEXT,
            role TEXT,
            action TEXT,
            notes TEXT,
            timestamp TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS staging_chunks (
            chunk_id TEXT PRIMARY KEY,
            file_id TEXT,
            chunk_data TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_jobs (
            job_id TEXT PRIMARY KEY,
            file_id TEXT,
            storage_id TEXT,
            status TEXT,
            stage TEXT,
            progress REAL,
            error_summary TEXT,
            created_at TEXT,
            updated_at TEXT,
            job_data TEXT
        )
    """)
    conn.commit()
    conn.close()

def create_document(file_id: str, filename: str, pii_mode: str, uploaded_by: str = "L1_Analyst", staging_storage_id: str = None, content_hash: str = None):
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Check existing state before overwrite
        c.execute("SELECT status FROM documents WHERE file_id = ?", (file_id,))
        row = c.fetchone()
        if row and row['status'] in ['PENDING_REVIEW', 'APPROVING', 'PROCESSING']:
            raise ValueError(f"Cannot replace document while it is in {row['status']} state.")
            
        now = datetime.now(timezone.utc).isoformat()
        c.execute("""
            INSERT INTO documents (file_id, filename, status, uploaded_at, uploaded_by, pii_mode, version, staging_storage_id, content_hash)
            VALUES (?, ?, 'PROCESSING', ?, ?, ?, 1, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                status = 'PROCESSING',
                pii_mode = excluded.pii_mode,
                uploaded_by = excluded.uploaded_by,
                staging_storage_id = excluded.staging_storage_id,
                content_hash = excluded.content_hash,
                version = version + 1
        """, (file_id, filename, now, uploaded_by, pii_mode, staging_storage_id, content_hash))
        
        # get current version
        c.execute("SELECT version FROM documents WHERE file_id = ?", (file_id,))
        version = c.fetchone()[0]
        
        conn.commit()
    finally:
        conn.close()
    
    add_audit_log(file_id, version, uploaded_by, "L1", "UPLOADED", f"Document uploaded. PII Mode: {pii_mode}")
    return version

def get_document(file_id: str) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE file_id = ?", (file_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def list_documents() -> List[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM documents ORDER BY uploaded_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_document_by_hash(content_hash: str) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE content_hash = ?", (content_hash,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_document_status(file_id: str, status: str, actor: str, role: str, action: str, notes: str = ""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE documents SET status = ? WHERE file_id = ?", (status, file_id))
    
    if status == "APPROVED":
        c.execute("UPDATE documents SET active_storage_id = staging_storage_id WHERE file_id = ?", (file_id,))
        
    c.execute("SELECT version FROM documents WHERE file_id = ?", (file_id,))
    row = c.fetchone()
    version = row[0] if row else 1
    conn.commit()
    conn.close()
    
    add_audit_log(file_id, version, actor, role, action, notes)

def transition_document_status(file_id: str, from_statuses: List[str], to_status: str, actor: str, role: str, action: str, notes: str = "") -> bool:
    """Atomic transition of document status to prevent concurrent approvals/rejections"""
    conn = get_connection()
    c = conn.cursor()
    
    placeholders = ",".join(["?"] * len(from_statuses))
    c.execute(f"UPDATE documents SET status = ? WHERE file_id = ? AND status IN ({placeholders})", [to_status, file_id] + from_statuses)
    
    success = c.rowcount > 0
    
    if success:
        c.execute("SELECT version FROM documents WHERE file_id = ?", (file_id,))
        row = c.fetchone()
        version = row[0] if row else 1
        conn.commit()
        conn.close()
        
        # Don't log internal transitional states if not needed, but we should log if it's a real action
        if to_status not in ["APPROVING"]:
            add_audit_log(file_id, version, actor, role, action, notes)
        return True
    else:
        conn.commit()
        conn.close()
        return False

def add_audit_log(file_id: str, version: int, actor: str, role: str, action: str, notes: str = ""):
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("""
        INSERT INTO audit_logs (file_id, version, actor, role, action, notes, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (file_id, version, actor, role, action, notes, now))
    conn.commit()
    conn.close()

def get_audit_logs(file_id: str) -> List[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM audit_logs WHERE file_id = ? ORDER BY timestamp ASC", (file_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_staging_chunks(file_id: str, chunks: List[Any]):
    # chunks is List[EvidenceChunk]
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM staging_chunks WHERE file_id = ?", (file_id,))
        
        for chunk in chunks:
            # Convert enum back to string
            chunk_dict = chunk.dict()
            chunk_dict['content_type'] = chunk.content_type.value
            c.execute(
                "INSERT INTO staging_chunks (chunk_id, file_id, chunk_data) VALUES (?, ?, ?)",
                (chunk.chunk_id, file_id, json.dumps(chunk_dict))
            )
        conn.commit()
    finally:
        conn.close()

def get_staging_chunks(file_id: str) -> List[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT chunk_data FROM staging_chunks WHERE file_id = ?", (file_id,))
    rows = c.fetchall()
    conn.close()
    return [json.loads(row[0]) for row in rows]

def delete_document(file_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM documents WHERE file_id = ?", (file_id,))
    c.execute("DELETE FROM staging_chunks WHERE file_id = ?", (file_id,))
    c.execute("DELETE FROM audit_logs WHERE file_id = ?", (file_id,))
    try:
        c.execute("DELETE FROM ingestion_jobs WHERE file_id = ?", (file_id,))
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()
def create_ingestion_job(job_id: str, file_id: str = None, storage_id: str = None, initial_data: dict = None):
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("""
        INSERT INTO ingestion_jobs (job_id, file_id, storage_id, status, stage, progress, created_at, updated_at, job_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (job_id, file_id, storage_id, 'QUEUED', 'Queued', 0.0, now, now, json.dumps(initial_data) if initial_data else "{}"))
    conn.commit()
    conn.close()

def update_ingestion_job(job_id: str, status: str = None, stage: str = None, progress: float = None, error_summary: str = None, job_data: dict = None):
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    fields = []
    params = []
    
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if stage is not None:
        fields.append("stage = ?")
        params.append(stage)
    if progress is not None:
        fields.append("progress = ?")
        params.append(progress)
    if error_summary is not None:
        fields.append("error_summary = ?")
        params.append(error_summary)
    if job_data is not None:
        # We might want to merge, but simple replacement is fine for our limited case
        c.execute("SELECT job_data FROM ingestion_jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        existing_data = json.loads(row['job_data']) if row and row['job_data'] else {}
        existing_data.update(job_data)
        fields.append("job_data = ?")
        params.append(json.dumps(existing_data))
        
    if not fields:
        conn.close()
        return
        
    fields.append("updated_at = ?")
    params.append(now)
    params.append(job_id)
    
    c.execute(f"UPDATE ingestion_jobs SET {', '.join(fields)} WHERE job_id = ?", params)
    conn.commit()
    conn.close()

def get_ingestion_job(job_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def reconcile_abandoned_jobs():
    """Mark jobs that are PROCESSING/QUEUED as INTERRUPTED on startup"""
    conn = get_connection()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("""
        UPDATE ingestion_jobs 
        SET status = 'INTERRUPTED', stage = 'Interrupted during server restart', updated_at = ? 
        WHERE status IN ('PROCESSING', 'QUEUED')
    """, (now,))
    conn.commit()
    conn.close()

def reconcile_abandoned_documents():
    """Reconcile documents stuck in transitional states on startup."""
    conn = get_connection()
    c = conn.cursor()
    
    def fetch_and_update(status_from, status_to):
        c.execute("SELECT file_id, version FROM documents WHERE status = ?", (status_from,))
        docs = c.fetchall()
        for row in docs:
            c.execute("UPDATE documents SET status = ? WHERE file_id = ?", (status_to, row['file_id']))
        return docs
        
    processing_docs = fetch_and_update('PROCESSING', 'FAILED_PROCESSING')
    approving_docs = fetch_and_update('APPROVING', 'PENDING_REVIEW')
    deleting_docs = fetch_and_update('DELETING', 'FAILED_DELETION')
        
    conn.commit()
    conn.close()
    
    # Add audit logs
    for row in processing_docs:
        add_audit_log(row['file_id'], row['version'], "SYSTEM", "SYSTEM", "FAILED_PROCESSING", "Interrupted during server restart")
    for row in approving_docs:
        add_audit_log(row['file_id'], row['version'], "SYSTEM", "SYSTEM", "REVERTED_APPROVAL", "Server restarted during approval. Reverted to PENDING_REVIEW.")
    for row in deleting_docs:
        add_audit_log(row['file_id'], row['version'], "SYSTEM", "SYSTEM", "FAILED_DELETION", "Interrupted during server restart")

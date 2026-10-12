import os

import fitz
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.app.config import settings
from backend.retrieval.index import get_indexer
from backend.app.deps import get_answerer, get_current_user

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "indexer": "ready"
    }


from backend.core import db
from pydantic import BaseModel
import jwt
from backend.app.config import settings

class DevTokenRequest(BaseModel):
    role: str
    name: str

@router.post("/dev-token")
@router.post("/system/dev-token")
def dev_token(req: DevTokenRequest):
    if not settings.use_stubs or not settings.enable_dev_auth:
        raise HTTPException(403, "Dev tokens are only available in development mode with ENABLE_DEV_AUTH=True")
    
    if not settings.dev_auth_secret:
        raise HTTPException(500, "DEV_AUTH_SECRET is not configured")
        
    payload = {
        "sub": "dev-user",
        "name": req.name,
        "role": req.role
    }
    token = jwt.encode(payload, settings.dev_auth_secret, algorithm="HS256")
    return {"access_token": token}

@router.get("/documents")
def documents(user: dict = Depends(get_current_user)):
    # Return document lifecycle list
    return db.list_documents()

@router.get("/documents/{file_id}/audit")
def document_audit(file_id: str, user: dict = Depends(get_current_user)):
    return db.get_audit_logs(file_id)

@router.get("/documents/{file_id}/staging")
def document_staging(file_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "L2":
        raise HTTPException(403, "Only L2 Manager can view staging chunks")
    return db.get_staging_chunks(file_id)

class ActionRequest(BaseModel):
    notes: str = ""

@router.post("/documents/{file_id}/submit")
def submit_document(file_id: str, req: ActionRequest, user: dict = Depends(get_current_user)):
    doc = db.get_document(file_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc["status"] not in ["DRAFT", "REJECTED"]:
        raise HTTPException(400, "Document must be in DRAFT or REJECTED state to submit")
    
    db.update_document_status(file_id, "PENDING_REVIEW", user["name"], user["role"], "SUBMITTED", req.notes)
    return {"status": "PENDING_REVIEW"}

@router.post("/documents/{file_id}/reject")
def reject_document(file_id: str, req: ActionRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "L2":
        raise HTTPException(403, "Only L2 Manager can reject documents")
    if not req.notes:
        raise HTTPException(400, "Rejection requires a reason in notes")
        
    doc = db.get_document(file_id)
    if not doc or doc["status"] != "PENDING_REVIEW":
        raise HTTPException(400, "Document must be PENDING_REVIEW")
        
    db.update_document_status(file_id, "REJECTED", user["name"], user["role"], "REJECTED", req.notes)
    return {"status": "REJECTED"}

@router.post("/documents/{file_id}/hold")
def hold_document(file_id: str, req: ActionRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "L2":
        raise HTTPException(403, "Only L2 Manager can hold documents")
    if not req.notes:
        raise HTTPException(400, "Hold requires a reason in notes")
        
    doc = db.get_document(file_id)
    if not doc or doc["status"] != "PENDING_REVIEW":
        raise HTTPException(400, "Document must be PENDING_REVIEW")
        
    db.update_document_status(file_id, "ON_HOLD", user["name"], user["role"], "PLACED_ON_HOLD", req.notes)
    return {"status": "ON_HOLD"}

from backend.core.schemas import EvidenceChunk

@router.post("/documents/{file_id}/approve")
def approve_document(file_id: str, req: ActionRequest, indexer=Depends(get_indexer), user: dict = Depends(get_current_user)):
    if user["role"] != "L2":
        raise HTTPException(403, "Only L2 Manager can approve documents")
        
    doc = db.get_document(file_id)
    if not doc or doc["status"] not in ["PENDING_REVIEW", "ON_HOLD"]:
        raise HTTPException(400, "Document must be PENDING_REVIEW or ON_HOLD")
        
    # Transition to APPROVING state to lock the document
    if not db.transition_document_status(file_id, ["PENDING_REVIEW", "ON_HOLD"], "APPROVING", user["name"], user["role"], "APPROVING"):
        raise HTTPException(409, "Document is currently being modified by another request.")
        
    staging_chunks_dicts = db.get_staging_chunks(file_id)
    if not staging_chunks_dicts:
        # Revert on failure
        db.update_document_status(file_id, doc["status"], user["name"], user["role"], "SYSTEM", "Missing staging chunks")
        raise HTTPException(500, "No staging chunks found for this document")
        
    # Rehydrate dicts to EvidenceChunk objects
    chunks = []
    for cd in staging_chunks_dicts:
        chunks.append(EvidenceChunk(**cd))
        
    # Push to production ChromaDB
    try:
        indexer.add(chunks)
        db.update_document_status(file_id, "APPROVED", user["name"], user["role"], "APPROVED", req.notes)
    except Exception as e:
        # Revert to PENDING_REVIEW if we failed to insert into ChromaDB or update DB
        db.update_document_status(file_id, "PENDING_REVIEW", user["name"], user["role"], "PUBLISH_FAILED", str(e))
        raise HTTPException(500, f"Failed to publish to Vector DB: {e}")
        
    # Cleanup old physical file if replacing
    old_active_id = doc.get("active_storage_id")
    if old_active_id and old_active_id != doc.get("staging_storage_id"):
        old_pdf_path = os.path.join(settings.upload_dir, old_active_id)
        if os.path.isfile(old_pdf_path):
            try:
                os.remove(old_pdf_path)
            except Exception as e:
                # Do not fail the approval if cleanup fails. Log for later recovery.
                db.add_audit_log(file_id, doc.get("version", 1), "SYSTEM", "SYSTEM", "CLEANUP_FAILED", f"Failed to delete old PDF {old_active_id}: {e}")
                
    return {"status": "APPROVED"}


@router.post("/documents/{file_id}/audit-ai")
def ai_audit_document(file_id: str, answerer=Depends(get_answerer), user: dict = Depends(get_current_user)):
    if user["role"] != "L2":
        raise HTTPException(403, "Only L2 Manager can run AI audit")
        
    doc = db.get_document(file_id)
    if not doc:
        raise HTTPException(404, "Document not found")
        
    staging_chunks_dicts = db.get_staging_chunks(file_id)
    if not staging_chunks_dicts:
        raise HTTPException(400, "No staging chunks to audit")
        
    chunks = [EvidenceChunk(**cd) for cd in staging_chunks_dicts]
    
    # We will use the Answerer as a generic LLM caller to audit the document.
    # The prompt will ask it to review the chunks for anomalies.
    
    audit_prompt = """
    You are an AI Auditor. Please review the provided extracted document chunks for any anomalies, missing data, or transcription errors. 
    Return a list of findings. If everything looks consistent, state that it is consistent. Keep it brief.
    """
    
    from backend.core.schemas import RetrievedChunk
    # We mock RetrievedChunk to pass to answerer
    evidence = [RetrievedChunk(chunk=c, dense_score=1.0, bm25_score=1.0, rerank_score=1.0) for c in chunks[:50]] # Limit to 50 chunks for context
    
    try:
        ans_text, _ = answerer.answer(audit_prompt, evidence)
        return {"findings": ans_text}
    except Exception as e:
        raise HTTPException(500, f"AI Audit failed: {e}")

@router.delete("/documents/{file_id}")
def delete_document(
    file_id: str,
    indexer=Depends(get_indexer),
    user: dict = Depends(get_current_user)
):
    """
    Delete a document and all of its associated data.

    Removes:
    - Vector index chunks
    - In-memory BM25 chunks
    - Uploaded PDF
    - Extracted image assets
    """

    doc = db.get_document(file_id)
    if not doc:
        raise HTTPException(404, "Document not found")
        
    db.update_document_status(file_id, "DELETING", user["name"], user["role"], "DELETING")
    
    # =========================================================
    # 1. Delete indexed chunks and SQLite DB records
    # =========================================================

    deleted_chunks = 0
    try:
        if hasattr(indexer, "delete_file"):
            deleted_chunks = indexer.delete_file(file_id)
        else:
            from backend.retrieval.index import get_indexer as real_get_indexer
            deleted_chunks = real_get_indexer().delete_file(file_id)
    except Exception:
        # If vector collection does not have the file (e.g. unapproved draft), proceed with DB deletion
        pass

    try:
        db.delete_document(file_id)
    except Exception as e:
        db.update_document_status(file_id, "FAILED_DELETION", user["name"], user["role"], "SYSTEM", str(e))
        raise HTTPException(500, f"Deletion failed midway: {e}")

    # =========================================================
    # 2. Delete uploaded PDF
    # =========================================================

    if doc:
        for storage_id in [doc.get("active_storage_id"), doc.get("staging_storage_id")]:
            if storage_id:
                pdf_path = os.path.join(settings.upload_dir, storage_id)
                if os.path.isfile(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except Exception:
                        pass

    # =========================================================
    # 3. Delete extracted image assets
    # =========================================================

    deleted_assets = 0

    if os.path.isdir(settings.asset_dir):

        prefix = f"{file_id}_"

        for filename in os.listdir(settings.asset_dir):

            if filename.startswith(prefix):

                asset_path = os.path.join(
                    settings.asset_dir,
                    filename
                )

                if os.path.isfile(asset_path):
                    os.remove(asset_path)
                    deleted_assets += 1

    # =========================================================
    # 4. Return deletion summary
    # =========================================================

    return {
        "message": "Document deleted successfully",
        "file_id": file_id,
        "deleted_chunks": deleted_chunks,
        "deleted_assets": deleted_assets
    }

@router.post("/system/cleanup-orphans")
def cleanup_orphans(dry_run: bool = True, indexer=Depends(get_indexer), user: dict = Depends(get_current_user)):
    if user["role"] != "L2":
        raise HTTPException(403, "Only L2 Manager can run cleanup")
        
    docs = db.list_documents()
    active_cache = {d["file_id"]: d for d in docs}
    
    return indexer.cleanup_orphans(active_cache, dry_run=dry_run)


@router.get("/documents/{file_id}/pages/{n}")
def document_page(file_id: str, n: int, staging: bool = False, user: dict = Depends(get_current_user)):
    """
    Render a PDF page as a PNG image.

    file_id is the uploaded filename.
    n is the 1-based page number.
    """
    
    doc = db.get_document(file_id)
    if not doc:
        physical_name = file_id
    else:
        if staging:
            physical_name = doc.get("staging_storage_id") or doc.get("active_storage_id")
        else:
            physical_name = doc.get("active_storage_id") or doc.get("staging_storage_id")

    candidate_paths = []
    if physical_name:
        candidate_paths.append(os.path.join(settings.upload_dir, physical_name))
    if doc:
        if doc.get("filename"):
            candidate_paths.append(os.path.join(settings.upload_dir, doc["filename"]))
        if doc.get("active_storage_id"):
            candidate_paths.append(os.path.join(settings.upload_dir, doc["active_storage_id"]))
        if doc.get("staging_storage_id"):
            candidate_paths.append(os.path.join(settings.upload_dir, doc["staging_storage_id"]))
    candidate_paths.append(os.path.join(settings.upload_dir, file_id))

    pdf_path = None
    for p in candidate_paths:
        if os.path.isfile(p):
            pdf_path = p
            break

    if not pdf_path and os.path.exists(settings.upload_dir):
        # Scan upload_dir for any matching filename
        target_fn = doc.get("filename") if doc else file_id
        for root, _, files in os.walk(settings.upload_dir):
            for f in files:
                if f == target_fn or (target_fn and f.endswith(target_fn)):
                    candidate = os.path.join(root, f)
                    if os.path.isfile(candidate):
                        pdf_path = candidate
                        break
            if pdf_path:
                break

    if not pdf_path or not os.path.isfile(pdf_path):
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    try:
        page_number = int(n) - 1

        with fitz.open(pdf_path) as doc:

            if page_number < 0 or page_number >= len(doc):
                raise HTTPException(
                    status_code=404,
                    detail="Page not found"
                )

            page = doc[page_number]

            # Render PDF page
            pixmap = page.get_pixmap(
                alpha=False
            )

            png_bytes = pixmap.tobytes("png")

        return Response(
            content=png_bytes,
            media_type="image/png"
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to render page: {str(e)}"
        )

from fastapi.responses import FileResponse

@router.get("/assets/{filename}")
def serve_asset(filename: str, user: dict = Depends(get_current_user)):
    """
    Serve an extracted image asset securely.
    Requires authentication.
    """
    # Prevent directory traversal
    safe_filename = os.path.basename(filename)
    asset_path = os.path.join(settings.asset_dir, safe_filename)
    
    if not os.path.isfile(asset_path):
        raise HTTPException(status_code=404, detail="Asset not found")
        
    return FileResponse(asset_path)
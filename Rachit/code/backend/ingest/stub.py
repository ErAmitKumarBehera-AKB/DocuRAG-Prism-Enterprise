import os
from typing import List

from backend.core.schemas import ContentType, EvidenceChunk


class StubIngestor:
    def ingest(
        self,
        path: str,
        original_filename: str = None,
        file_id: str = None,
        storage_id: str = None,
        processing_preference: str = "mixed",
        pii_mode: str = "STRICT",
        uploader_role: str = "L1",
        uploader_name: str = "L1_Analyst",
        content_hash: str = None,
        **kwargs
    ) -> List[EvidenceChunk]:
        if path and os.path.exists(path) and path.lower().endswith(".pdf"):
            try:
                from backend.ingest.pipeline import RealIngestor
                return RealIngestor().ingest(
                    path=path,
                    original_filename=original_filename,
                    file_id=file_id,
                    storage_id=storage_id,
                    processing_preference=processing_preference,
                    pii_mode=pii_mode,
                    uploader_role=uploader_role,
                    uploader_name=uploader_name,
                    content_hash=content_hash
                )
            except Exception as e:
                print(f"[StubIngestor] Real ingestion fallback failed: {e}, using stub")

        return [
            EvidenceChunk(
                chunk_id="stub_chunk_1",
                file_id=file_id or "stub_file",
                page=1,
                content_type=ContentType.text,
                region_id="r1",
                bbox=[0.0, 0.0, 100.0, 100.0],
                text="This is a stub chunk."
            )
        ]

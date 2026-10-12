# Rachit Patnaik — Source Code Ownership Manifest

This manifest documents all files included in Rachit's package, their original paths, and their component relationships.

---

## 1. Owned Source Files

| Original Project Path | Packaged Relative Path | Purpose | Key Classes & Functions |
|---|---|---|---|
| `backend/app/main.py` | `code/backend/app/main.py` | FastAPI application initialization & route mounting | `create_app()`, CORS middleware, startup events |
| `backend/app/config.py` | `code/backend/app/config.py` | Central configuration & environment settings | `Settings` (Pydantic BaseSettings) |
| `backend/app/cache.py` | `code/backend/app/cache.py` | In-memory caching utilities | Cache helpers |
| `backend/app/logging_utils.py`| `code/backend/app/logging_utils.py`| Structured logging utilities | Logger setup |
| `backend/app/routers/ingest.py`| `code/backend/app/routers/ingest.py`| Document upload and listing endpoints | `upload_document()`, `list_documents()`, `delete_document()` |
| `backend/app/routers/query.py` | `code/backend/app/routers/query.py` | Query execution and comparison endpoints | `query()`, `compare()` |
| `backend/app/routers/system.py`| `code/backend/app/routers/system.py`| Governance, page previews, and health endpoints | `approve_document()`, `reject_document()`, `document_page()` |
| `backend/core/db.py` | `code/backend/core/db.py` | SQLite database connection & schema management | `get_db()`, `init_db()`, `transition_document_status()` |
| `backend/core/schemas.py` | `code/backend/core/schemas.py` | Master Pydantic schemas and contracts | `QueryRequest`, `QueryResponse`, `DocumentOut` |
| `backend/core/interfaces.py`| `code/backend/core/interfaces.py`| Core Abstract Base Classes | `Ingestor`, `Retriever`, `Answerer` |
| `backend/ingest/pipeline.py` | `code/backend/ingest/pipeline.py` | End-to-end PDF ingestion pipeline | `RealIngestor.ingest_file()` |
| `backend/ingest/parser.py` | `code/backend/ingest/parser.py` | PyMuPDF text and block parser | `PDFParser.extract_pages()` |
| `backend/ingest/chunker.py`| `code/backend/ingest/chunker.py`| Structure-aware chunking engine | `StructureAwareChunker.chunk_document()` |
| `backend/ingest/extractors.py`| `code/backend/ingest/extractors.py`| Table & layout extractor | `VisionTableExtractor` |
| `backend/ingest/router.py` | `code/backend/ingest/router.py` | Ingestion dispatch router | Routing helpers |
| `backend/ingest/stub.py` | `code/backend/ingest/stub.py` | Test stubs for ingestion | `StubIngestor` |
| `backend/ingest/__init__.py` | `code/backend/ingest/__init__.py` | Module init | Exports |

---

## 2. Shared Interfaces & Dependencies

- **Retrieval Dependency:** Handled via `deps.py` dependency injection (`get_retriever()`), calling Ayush's `HybridRetriever`.
- **Generation Dependency:** Handled via `deps.py` dependency injection (`get_answerer()`), calling Amit's `RealAnswerer`.
- **Auth Dependency:** Injected into routes via `Depends(get_current_user)`, calling Amit's authentication validator.

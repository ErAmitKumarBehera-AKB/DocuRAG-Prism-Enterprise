# Role 3: Rachit Patnaik — Backend Core, Ingestion & Architecture Lead

Welcome Rachit. You are assigned **Role 3**: you own the **Core FastAPI Application, Document Ingestion Pipeline, SQLite Persistence, and API Routers**. In addition, you have a **Mandatory Authentication Study Requirement** to master and explain Amit's authentication and authorization implementation to interviewers.

---

## 1. Scope of Responsibility

- **Code Ownership:**
  - `backend/app/main.py` (FastAPI app factory, middleware, CORS)
  - `backend/app/config.py` (Settings, pydantic-settings)
  - `backend/app/routers/ingest.py` (Document upload, delete, listing)
  - `backend/app/routers/query.py` (Search & query endpoints)
  - `backend/app/routers/system.py` (Document governance, page rendering, health)
  - `backend/core/db.py` (SQLite WAL persistence, schema management)
  - `backend/core/schemas.py` & `interfaces.py` (Core data contracts)
  - `backend/ingest/` (PDF parser, extractors, chunker, pipeline)
- **Mandatory Authentication Study:**
  - Even though Amit owns the auth implementation code, you must master the complete L1/L2 authentication and authorization architecture to explain it in depth during presentations and technical vivas.

---

## 2. Directory Layout

```
Rachit/
├── README.md         # This role guide
├── MANIFEST.md       # Precise source file manifest and interface boundaries
├── STUDY_GUIDE.md    # Comprehensive backend guide + Mandatory Auth Study Guide (35+ Q&As)
└── code/             # Your owned codebase with original relative paths
    └── backend/
        ├── app/        # FastAPI main, config, routers (ingest, query, system)
        ├── core/       # SQLite db and data contracts
        └── ingest/     # Parsing, extraction, and chunking pipeline
```

---

## 3. Preparation Checklist

1. Review [`MANIFEST.md`](./MANIFEST.md) for owned files and boundaries.
2. Study [`STUDY_GUIDE.md`](./STUDY_GUIDE.md):
   - Review the FastAPI request lifecycle and document ingestion flow.
   - Master Section 10: **Amit's Authentication & Authorization Deep Dive**.
   - Rehearse the 25 backend viva questions and 10 auth viva questions.
   - Practice the 2-minute backend presentation pitch.

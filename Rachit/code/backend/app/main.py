from contextlib import asynccontextmanager

from backend.app.config import settings
from backend.app.routers import auth, eval, ingest, query, system
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.enable_dev_auth:
        if not settings.use_stubs and settings.oidc_domain:
            raise RuntimeError("CRITICAL SECURITY ERROR: ENABLE_DEV_AUTH is True but production OIDC is configured.")
        if not settings.dev_auth_secret or len(settings.dev_auth_secret) < 32:
            raise RuntimeError("CRITICAL SECURITY ERROR: ENABLE_DEV_AUTH is True but DEV_AUTH_SECRET is empty or too short (must be >= 32 chars).")
        if not settings.use_stubs:
            print("[Startup] Running in local demo auth mode with real LLM backend.")

            
    print("[Startup] Reconciling abandoned jobs...")
    from backend.core.db import reconcile_abandoned_jobs, reconcile_abandoned_documents
    reconcile_abandoned_jobs()
    print("[Startup] Reconciling transitional documents...")
    reconcile_abandoned_documents()
    if not settings.use_stubs:
        try:
            print("[Startup] Preloading embedding model...")
            from backend.retrieval.embeddings import get_embedding_model
            get_embedding_model()
            
            print("[Startup] Preloading cross-encoder model...")
            from backend.retrieval.reranker import preload as preload_reranker
            preload_reranker()
            
            print("[Startup] Models loaded successfully.")
        except Exception as e:
            print(f"[Startup] Warning: Failed to preload models: {e}. They will be lazy-loaded on first request.")
    else:
        print("[Startup] USE_STUBS=true. Real ML models will not be loaded.")
    yield

app = FastAPI(title="DocuRAG", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assets are now served via authenticated endpoints in system.py

app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(eval.router)
app.include_router(system.router)


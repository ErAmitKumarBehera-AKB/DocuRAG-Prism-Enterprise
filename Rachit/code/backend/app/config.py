import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    use_stubs: bool = False
    cache_db: str = "sqlite:///./data/cache.db"

    # ---------------------------------------------------------
    # Authentication
    # ---------------------------------------------------------
    
    oidc_domain: str = ""
    oidc_audience: str = ""
    oidc_algorithms: str = "RS256"
    
    enable_dev_auth: bool = False
    dev_auth_secret: str = ""

    # ---------------------------------------------------------
    # LLM Configuration
    # ---------------------------------------------------------

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: float = 15.0

    groq_api_key: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = 20.0

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    # ---------------------------------------------------------
    # Retrieval Configuration
    # ---------------------------------------------------------

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    chroma_path: str = "./data/chroma"

    # ---------------------------------------------------------
    # Storage
    # ---------------------------------------------------------

    upload_dir: str = "./data/uploads"
    asset_dir: str = "./data/assets"

    # ---------------------------------------------------------
    # Evaluation / Trust
    # ---------------------------------------------------------

    ocr_confidence_threshold: float = 0.80
    refusal_threshold: float = 0.40

    # ---------------------------------------------------------
    # General
    # ---------------------------------------------------------

    top_k: int = 5
    max_file_size_mb: int = 50

    class Config:
        env_file = ".env"


settings = Settings()

os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.asset_dir, exist_ok=True)
os.makedirs("./data", exist_ok=True)
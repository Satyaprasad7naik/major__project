# from pydantic_settings import BaseSettings
# from pydantic import model_validator
# from typing import Optional
# from dotenv import load_dotenv
# from urllib.parse import quote
# import os

# # Explicitly load .env file
# load_dotenv()

# # Default Redis URL (local); overridden by REDIS_URL or built from REDIS_* below
# _DEFAULT_REDIS_URL = "hack-deriv-realtime-6ur8gt.serverless.aps1.cache.amazonaws.com:6379"


# class Settings(BaseSettings):
#     PROJECT_NAME: str = "NL2SQL Pipeline"
#     API_V1_STR: str = "/api/v1"
    
#     # LLM Settings
#     GEMINI_API_KEY: Optional[str] = None
#     GEMINI_MODEL_NAME: str = "gemini-3-flash-preview"
#     OPENAI_API_KEY: Optional[str] = None
#     OPENAI_BASE_URL: Optional[str] = None
#     OPENAI_MODEL_NAME: str = "meta/llama-3.1-8b-instruct"
#     QUBRID_API_KEY: Optional[str] = None
#     QUBRID_BASE_URL: str = "https://platform.qubrid.com/api/v1/qubridai"
#     QUBRID_MODEL_NAME: str = "meta-llama/Llama-3.3-70B-Instruct"
    
#     # stage-specific models (auto-resolved based on provider)
#     INTENT_MODEL: str = os.getenv("INTENT_MODEL", "meta/llama-3.1-8b-instruct")
#     SQL_MODEL: str = os.getenv("SQL_MODEL", "meta/llama-3.1-8b-instruct")
#     CLARIFICATION_MODEL: str = os.getenv("CLARIFICATION_MODEL", "meta/llama-3.1-8b-instruct")
#     DISCOVERY_MODEL: str = os.getenv("DISCOVERY_MODEL", "meta/llama-3.1-8b-instruct")
#     EXTRACTION_MODEL: str = os.getenv("EXTRACTION_MODEL", "meta/llama-3.1-8b-instruct")
#     RETRIEVAL_MODEL: str = os.getenv("RETRIEVAL_MODEL", "meta/llama-3.1-8b-instruct")
    
#     # Database Settings (Target DB to query)
#     # DATABASE_URL: str = "sqlite:///./derivinsightnew.db"
#     import os
#     DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./derivinsightnew.db")
#     SCHEMA_PATH: str = "app/files/derivinsight_schema.sql"
#     MOCK_DATA_SCRIPT_PATH: str = "app/files/generate_mock_data.py"
    
#     # Cache / Redis (Valkey) Settings
#     REDIS_URL: str = _DEFAULT_REDIS_URL
#     REDIS_HOST: Optional[str] = "hack-deriv-realtime-6ur8gt.serverless.aps1.cache.amazonaws.com"
#     REDIS_PORT: int = 6379
#     REDIS_PASSWORD: Optional[str] = None
#     REDIS_USE_SSL: bool = True
#     REDIS_DB: int = 0

#     @model_validator(mode="after")
#     def build_redis_url_from_parts(self) -> "Settings":
#         if not self.REDIS_HOST:
#             return self
#         scheme = "rediss"
#         password = quote(self.REDIS_PASSWORD, safe="") if self.REDIS_PASSWORD else ""
#         auth = f":{password}@" if password else ""
#         self.REDIS_URL = f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
#         return self
    
#     # ECS worker tasks
#     ECS_CLUSTER: Optional[str] = os.getenv("ECS_CLUSTER", "HackathonDerivBackend")
#     ECS_TASK_DEFINITION: Optional[str] = os.getenv("ECS_TASK_DEFINITION", None)
#     ECS_ENGINE_TASK_DEFINITION: Optional[str] = os.getenv("ECS_ENGINE_TASK_DEFINITION", None)
#     ECS_GENERATOR_TASK_DEFINITION: Optional[str] = os.getenv("ECS_GENERATOR_TASK_DEFINITION", None)
#     ECS_ENGINE_WORKER_CONTAINER_NAME: str = "alerting-worker-container"
#     ECS_GENERATOR_WORKER_CONTAINER_NAME: str = "event-generator-worker-container"
    
#     ECS_SUBNETS: Optional[str] = os.getenv("ECS_SUBNETS", None)
#     ECS_SECURITY_GROUPS: Optional[str] = os.getenv("ECS_SECURITY_GROUPS", None)
#     ECS_LAUNCH_TYPE: str = "FARGATE"
    
#     # Sentinel v2 Feature Flags
#     DEEP_DIVE_ENABLED: bool = True
#     DEEP_DIVE_MAX_DEPTH: int = 2
#     CORRELATION_ENABLED: bool = True
#     ADAPTIVE_ENABLED: bool = True

#     # Slack Alerts
#     SLACK_WEBHOOK_URL: Optional[str] = None
#     SLACK_BOT_TOKEN: Optional[str] = os.getenv("SLACK_BOT_TOKEN", None)
#     SLACK_CHANNEL: str = "sentinnelanomalies"
#     SLACK_ALERT_MIN_SEVERITY: str = "HIGH"

#     # App Settings
#     LOG_LEVEL: str = "INFO"
    
#     class Config:
#         env_file = ".env"
#         extra = "ignore"

# settings = Settings()
from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional
from dotenv import load_dotenv
from urllib.parse import quote
import os

# Explicitly load .env file
load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "NL2SQL Pipeline"
    API_V1_STR: str = "/api/v1"
    
    # LLM Settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL_NAME: str = "gemini-3-flash-preview"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_MODEL_NAME: str = os.getenv("OPENAI_MODEL_NAME", "meta/llama-3.2-11b-vision-instruct")
    OPENAI_FAST_MODEL: str = os.getenv("OPENAI_FAST_MODEL", "meta/llama-3.2-11b-vision-instruct")
    QUBRID_API_KEY: Optional[str] = None
    QUBRID_BASE_URL: str = "https://platform.qubrid.com/api/v1/qubridai"
    QUBRID_MODEL_NAME: str = "meta/llama-3.2-11b-vision-instruct"
    
    # stage-specific models (auto-resolved based on provider)
    INTENT_MODEL: str = os.getenv("INTENT_MODEL", "meta/llama-3.2-11b-vision-instruct")
    SQL_MODEL: str = os.getenv("SQL_MODEL", "meta/llama-3.2-11b-vision-instruct")
    CLARIFICATION_MODEL: str = os.getenv("CLARIFICATION_MODEL", "meta/llama-3.2-11b-vision-instruct")
    DISCOVERY_MODEL: str = os.getenv("DISCOVERY_MODEL", "meta/llama-3.2-11b-vision-instruct")
    EXTRACTION_MODEL: str = os.getenv("EXTRACTION_MODEL", "meta/llama-3.2-11b-vision-instruct")
    RETRIEVAL_MODEL: str = os.getenv("RETRIEVAL_MODEL", "meta/llama-3.2-11b-vision-instruct")
    
    # Database Settings (Target DB to query)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./retail_clothing.db")
    SCHEMA_PATH: str = os.getenv("SCHEMA_PATH", "app/files/derivinsight_schema.sql")
    MOCK_DATA_SCRIPT_PATH: str = "app/files/generate_mock_data.py"

    # Custom AI Models Configuration
    USE_CUSTOM_MODELS: bool = os.getenv("USE_CUSTOM_MODELS", "True").lower() == "true"
    MODELS_DIR: str = os.getenv("MODELS_DIR", "models")
    
    # Cache / Redis (Valkey) Settings
    # SECURITY FIX: Defaults to None to prevent infrastructure leak via source code
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)
    REDIS_HOST: Optional[str] = os.getenv("REDIS_HOST", None)
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    REDIS_USE_SSL: bool = True
    REDIS_DB: int = 0

    @model_validator(mode="after")
    def build_redis_url_from_parts(self) -> "Settings":
        if not self.REDIS_HOST:
            return self
        scheme = "rediss" if self.REDIS_USE_SSL else "redis"
        password = quote(self.REDIS_PASSWORD, safe="") if self.REDIS_PASSWORD else ""
        auth = f":{password}@" if password else ""
        self.REDIS_URL = f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return self
    
    # ECS worker tasks
    ECS_CLUSTER: Optional[str] = os.getenv("ECS_CLUSTER", "HackathonDerivBackend")
    ECS_TASK_DEFINITION: Optional[str] = os.getenv("ECS_TASK_DEFINITION", None)
    ECS_ENGINE_TASK_DEFINITION: Optional[str] = os.getenv("ECS_ENGINE_TASK_DEFINITION", None)
    ECS_GENERATOR_TASK_DEFINITION: Optional[str] = os.getenv("ECS_GENERATOR_TASK_DEFINITION", None)
    ECS_ENGINE_WORKER_CONTAINER_NAME: str = "alerting-worker-container"
    ECS_GENERATOR_WORKER_CONTAINER_NAME: str = "event-generator-worker-container"
    
    ECS_SUBNETS: Optional[str] = os.getenv("ECS_SUBNETS", None)
    ECS_SECURITY_GROUPS: Optional[str] = os.getenv("ECS_SECURITY_GROUPS", None)
    ECS_LAUNCH_TYPE: str = "FARGATE"
    
    # Sentinel v2 Feature Flags
    DEEP_DIVE_ENABLED: bool = True
    DEEP_DIVE_MAX_DEPTH: int = 2
    CORRELATION_ENABLED: bool = True
    ADAPTIVE_ENABLED: bool = True

    # Slack Alerts
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = os.getenv("SLACK_BOT_TOKEN", None)
    SLACK_CHANNEL: str = "sentinnelanomalies"
    SLACK_ALERT_MIN_SEVERITY: str = "HIGH"

    # Email Alerts (SMTP)
    SMTP_SERVER: Optional[str] = os.getenv("SMTP_SERVER", os.getenv("SMTP_HOST", None))
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_EMAIL: Optional[str] = os.getenv("SMTP_EMAIL", os.getenv("SMTP_USER", None))
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD", None)
    NOTIFICATION_EMAIL: Optional[str] = os.getenv("NOTIFICATION_EMAIL", os.getenv("ALERT_EMAIL_RECIPIENTS", None))

    # App Settings
    LOG_LEVEL: str = "INFO"

    # InsightOS Scheduler Settings
    DEFAULT_DOMAIN: str = os.getenv("DEFAULT_DOMAIN", "retail_clothing")
    SCHEDULER_INTERVAL_MINUTES: int = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "60"))
    ENABLE_INSIGHTS_API: bool = os.getenv("ENABLE_INSIGHTS_API", "True").lower() == "true"

    # ── Advanced Automated Data Synchronization Settings ───────────────────────
    # 1. Tally ERP / TallyPrime
    TALLY_SYNC_ENABLED: bool = os.getenv("TALLY_SYNC_ENABLED", "True").lower() == "true"
    TALLY_AUTO_SYNC_ENABLED: bool = os.getenv("TALLY_AUTO_SYNC_ENABLED", "True").lower() == "true"
    TALLY_HOST: str = os.getenv("TALLY_HOST", "localhost")
    TALLY_PORT: int = int(os.getenv("TALLY_PORT", "9000"))
    TALLY_COMPANY: Optional[str] = os.getenv("TALLY_COMPANY", None)
    TALLY_EXPORT_FOLDER: Optional[str] = os.getenv("TALLY_EXPORT_FOLDER", None)
    TALLY_SYNC_INTERVAL_MINUTES: int = int(os.getenv("TALLY_SYNC_INTERVAL_MINUTES", "60"))
    LIVE_DATA_DIR: str = os.getenv("LIVE_DATA_DIR", "live_data")

    # 2. Google Sheets Live Sync
    GOOGLE_SHEETS_ENABLED: bool = os.getenv("GOOGLE_SHEETS_ENABLED", "False").lower() == "true"
    GOOGLE_SHEET_ID: Optional[str] = os.getenv("GOOGLE_SHEET_ID", None)
    GOOGLE_CREDENTIALS_FILE: Optional[str] = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES: int = int(os.getenv("GOOGLE_SYNC_INTERVAL_MINUTES", os.getenv("GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES", "15")))
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID", None)
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET", None)
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/api/v1/auth/google/callback")
    GOOGLE_OAUTH_TOKEN_FILE: str = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "google_user_token.json")

    # 3. Shared Network Folder Sync
    NETWORK_FOLDER_ENABLED: bool = os.getenv("NETWORK_FOLDER_ENABLED", "False").lower() == "true"
    NETWORK_FOLDER_PATH: Optional[str] = os.getenv("NETWORK_FOLDER_PATH", None)
    NETWORK_FOLDER_SYNC_INTERVAL_MINUTES: int = int(os.getenv("NETWORK_FOLDER_SYNC_INTERVAL_MINUTES", "5"))

    # ── JWT Authentication ─────────────────────────────────────────────────────
    # Generate a strong secret: python -c "import secrets; print(secrets.token_hex(32))"
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-generate-a-strong-random-secret")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins; use * ONLY for local dev
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080,http://localhost:8081")

    # ── Enterprise Module Paths ────────────────────────────────────────────────
    SUPPLY_CHAIN_SCHEMA_PATH: str = os.getenv("SUPPLY_CHAIN_SCHEMA_PATH", "app/files/supply_chain_schema.sql")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
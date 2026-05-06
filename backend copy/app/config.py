import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # SAP Integration Mode: "mock" (default) or "real"
    SAP_INTEGRATION_MODE: str = os.getenv("SAP_INTEGRATION_MODE", "mock")

    # SAP S/4HANA OData API Credentials
    SAP_URL: str = os.getenv("SAP_URL", "https://sandbox.api.sap.com/s4hanacloud")
    SAP_USERNAME: str = os.getenv("SAP_USERNAME", "API_USER")
    SAP_PASSWORD: str = os.getenv("SAP_PASSWORD", "secret")
    SAP_CLIENT: str = os.getenv("SAP_CLIENT", "100")
    
    # Internal switch for checking auth
    # For SAP API Hub testing, usually APIKey is used. 
    # For actual SAP S/4HANA, Basic Auth is used.
    SAP_API_KEY: str = os.getenv("SAP_API_KEY", "")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

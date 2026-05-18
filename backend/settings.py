from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    agenttrust_url: str = "http://localhost:8080"
    crm_mcp_url: str = "http://localhost:3001"
    jwt_secret: str = "salesforge-demo-secret-change-in-prod"
    llm_provider: str = "anthropic"          # "anthropic" | "openai"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    salesforge_agent_id: str = "salesforge-agent"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

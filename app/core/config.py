from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    port: int = 8000

    default_business_id: str | None = None

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    openai_api_key: str | None = None
    vapi_webhook_secret: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    notify_email_from: str | None = None
    notify_email_to: str | None = None

    calcom_api_key: str | None = None
    calcom_base_url: str = "https://api.cal.com"
    calcom_api_version: str = "2024-08-13"
    calcom_event_type_id: str | None = None

    dashboard_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

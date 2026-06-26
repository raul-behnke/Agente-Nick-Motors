from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI — modelos mais novos, uniformes (gpt-4.1), configurável por papel
    openai_api_key: str
    openai_model_updater: str = "gpt-4.1"
    openai_model_responder: str = "gpt-4.1"  # legacy — substituído por NICK (Team leader)
    openai_model_patricia: str = "gpt-4.1"  # Team leader (Agno) — NICK
    openai_model_inventory_expert: str = "gpt-4.1"  # Team member especialista em estoque (Agno)
    openai_model_inventory_extractor: str = "gpt-4.1-mini"  # legacy — substituído pelo EstoqueExpert
    openai_model_editor: str = "gpt-4.1"  # Editor — 2º passe de humanização (camada Veltron portada)
    openai_model_whisper: str = "whisper-1"

    # GHL
    ghl_pit_token: str
    ghl_location_id: str
    ghl_base_url: str = "https://services.leadconnectorhq.com"
    ghl_api_version: str = "2021-07-28"

    ghl_stock_custom_value_id: str
    ghl_faq_custom_value_id: str
    ghl_field_veiculo_interesse: str
    ghl_field_saudacao_prevendas: str
    ghl_calendar_id: str
    ghl_appointment_duration_min: int = 45  # calendar NICK MOTORS - VISITAS = slots de 45min
    ghl_handoff_workflow_id: str
    ghl_tag_agent_gate: str = "agente-ia"

    # Server
    webhook_secret: str
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_timezone: str = "America/Sao_Paulo"

    # Postgres
    database_url: str = "postgresql+asyncpg://nick:nick@localhost:5432/nick_agent"

    # Cache TTL
    faq_cache_ttl_seconds: int = 300
    stock_cache_ttl_seconds: int = 300

    # Limits
    conversation_history_limit: int = 100
    inventory_search_limit: int = 10
    responder_max_bubbles: int = 3
    photo_max_send: int = 6  # máximo de fotos enviadas por veículo (evita spam)
    responder_sleep_min: float = 0.6
    responder_sleep_max: float = 1.2
    human_request_threshold: int = 2
    ai_identity_admit_at: int = 2

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Metrics
    metrics_enabled: bool = True
    metrics_port: int = 9090

    # Telemetria / Performance Hub (envelope canônico v1)
    client: str = "nick-motors"  # slug do cliente na frota
    agent_name: str = "nick-motors"  # slug do agente
    telemetry_events_enabled: bool = True

    # Export HTTP p/ o coletor do Hub (transporte §5). Secret DEDICADO — NÃO é o
    # webhook_secret. Vazio => /export/events responde 401 (nunca aberto).
    zoi_export_secret: str = ""
    export_table: str = "agent_events"


settings = Settings()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import dashboard_router, dev_router, health_router, vapi_webhook_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="AI Receptionist Backend", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_origin_regex=r"https://.*\.vapi\.(ai|com)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, tags=["health"])
    app.include_router(dev_router, tags=["dev"])
    app.include_router(vapi_webhook_router, tags=["webhooks"])
    app.include_router(dashboard_router, tags=["dashboard"])

    @app.get("/")
    def root():
        return {"service": "ai-receptionist-backend", "env": settings.app_env}

    return app


app = create_app()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.limits import UploadConcurrencyLimit, UserRateLimiter
from app.config import Settings
from app.errors import AgentError
from app.logging_config import configure_logging
from app.routes import (
    application_error_handler,
    router,
    unexpected_error_handler,
)
from app.services import ApplicationServices
from app.observability import RequestMetrics, RequestMetricsMiddleware


configure_logging()


def create_app(
    settings: Settings | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    """Build the API with injectable settings and services for isolated tests."""
    app_settings = settings or Settings()
    application = FastAPI(
        title=app_settings.app_name,
        description=(
            "Upload PDF and TXT documents, retrieve relevant passages, and ask "
            "questions grounded in their contents."
        ),
        version="0.1.0",
    )
    application.state.settings = app_settings
    application.state.services = services
    application.state.upload_limiter = UploadConcurrencyLimit(
        app_settings.max_concurrent_uploads,
        app_settings.upload_wait_timeout_seconds,
    )
    application.state.rate_limiter = UserRateLimiter(
        app_settings.rate_limit_requests,
        app_settings.rate_limit_window_seconds,
    )
    application.state.request_metrics = RequestMetrics()
    application.add_middleware(RequestMetricsMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Filename"],
    )
    application.add_exception_handler(AgentError, application_error_handler)
    application.add_exception_handler(Exception, unexpected_error_handler)
    application.include_router(router)
    return application


app = create_app()

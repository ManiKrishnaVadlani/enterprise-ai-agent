"""Shared FastAPI dependencies for application services."""

from fastapi import Request

from app.services import ApplicationServices, build_services


def get_services(request: Request) -> ApplicationServices:
    """Create app services on first use so importing the app has no DB side effect."""
    services = request.app.state.services
    if services is None:
        services = build_services(request.app.state.settings)
        request.app.state.services = services
    return services

from fastapi import Header, HTTPException, Query

from app.core.config import settings


def require_dashboard_api_key(authorization: str | None = Header(default=None)) -> None:
    if not settings.dashboard_api_key:
        raise HTTPException(status_code=500, detail="Dashboard API key not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.dashboard_api_key:
        raise HTTPException(status_code=403, detail="Invalid authorization")


def get_business_id(businessId: str | None = Query(default=None)) -> str:
    bid = (businessId or settings.default_business_id or "").strip()
    if not bid:
        raise HTTPException(status_code=400, detail="Missing businessId")
    return bid


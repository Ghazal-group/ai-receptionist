from fastapi import APIRouter

from app.core.config import settings
from app.integrations.supabase_client import get_supabase_admin


router = APIRouter(prefix="/dev")


@router.post("/bootstrap")
def bootstrap():
    db = get_supabase_admin()

    resp = (
        db.table("businesses")
        .insert(
            {
                "name": "Ghazal Solutions (Demo)",
                "industry": "real_estate",
                "timezone": "Africa/Lagos",
            }
        )
        .execute()
    )

    business_id = None
    if getattr(resp, "data", None) and len(resp.data) > 0:
        business_id = resp.data[0].get("id")

    return {"businessId": business_id, "envDefaultBusinessId": settings.default_business_id}


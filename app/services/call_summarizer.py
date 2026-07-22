import json
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.supabase_client import get_supabase_admin


def _summary_prompt(transcript: str) -> str:
    return (
        "You are an AI assistant generating a post-call summary for a Nigerian real estate agency.\n"
        "Return STRICT JSON only (no markdown, no extra keys).\n\n"
        "Required JSON schema:\n"
        "{\n"
        '  "summary": string,\n'
        '  "lead": {\n'
        '    "fullName": string|null,\n'
        '    "phone": string|null,\n'
        '    "intent": "rent"|"buy"|null,\n'
        '    "propertyType": string|null,\n'
        '    "locationInterest": string|null,\n'
        '    "budgetText": string|null,\n'
        '    "timeframe": string|null\n'
        "  },\n"
        '  "nextSteps": [string]\n'
        "}\n\n"
        "Transcript:\n"
        f"{transcript}"
    )


async def summarize_and_update_call(business_id: str, call_id: str, transcript: str) -> None:
    if not settings.openai_api_key:
        db = get_supabase_admin()
        db.table("call_summaries").update(
            {
                "extracted_fields": {
                    "summaryStatus": "pending_openai_key",
                }
            }
        ).eq("business_id", business_id).eq("call_id", call_id).execute()
        return

    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "You generate accurate, concise call summaries."},
            {"role": "user", "content": _summary_prompt(transcript)},
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    content = (
        (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    ).strip()

    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None

    db = get_supabase_admin()
    if parsed and isinstance(parsed, dict):
        db.table("call_summaries").update(
            {
                "summary": parsed.get("summary"),
                "extracted_fields": {
                    "summaryStatus": "generated",
                    "lead": parsed.get("lead"),
                    "nextSteps": parsed.get("nextSteps"),
                },
            }
        ).eq("business_id", business_id).eq("call_id", call_id).execute()
        return

    db.table("call_summaries").update(
        {
            "extracted_fields": {
                "summaryStatus": "failed_parse",
                "rawModelOutput": content,
            }
        }
    ).eq("business_id", business_id).eq("call_id", call_id).execute()


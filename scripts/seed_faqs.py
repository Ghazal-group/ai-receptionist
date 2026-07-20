from pathlib import Path

from dotenv import dotenv_values
from supabase import create_client


def main() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    cfg = dotenv_values(env_path)

    url = cfg.get("SUPABASE_URL")
    key = cfg.get("SUPABASE_SERVICE_ROLE_KEY")
    business_id = cfg.get("DEFAULT_BUSINESS_ID")
    if not url or not key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in backend/.env")
    if not business_id:
        raise SystemExit("Missing DEFAULT_BUSINESS_ID in backend/.env (set it to a businesses.id)")

    client = create_client(url, key)

    faqs = [
        {
            "question": "Do you charge inspection fees?",
            "answer": "Inspections are free for serious buyers, but for some listings we require a small refundable commitment fee. If you tell me the estate or area, I'll confirm the exact policy.",
            "is_active": True,
        },
        {
            "question": "Which areas do you cover in Lagos?",
            "answer": "We cover Lekki, Ikoyi, Victoria Island, Ajah, Chevron, Sangotedo, Ikeja, and most key estates across Lagos. Tell me your preferred area and budget and I’ll shortlist options.",
            "is_active": True,
        },
        {
            "question": "Can I pay in instalments?",
            "answer": "Yes, for many developer projects instalment plans are available. The duration and deposit depend on the project. What location and budget range are you considering?",
            "is_active": True,
        },
        {
            "question": "What documents do I need to buy a property in Nigeria?",
            "answer": "Typically you’ll want a valid title (like C of O, Governor’s Consent, or a registered deed), a survey plan, and proper sale documentation. If you share the listing you’re interested in, our team can confirm the title status.",
            "is_active": True,
        },
        {
            "question": "How soon can I do an inspection?",
            "answer": "We can usually arrange inspections within 24–48 hours, depending on access and the seller. If you tell me the area and preferred day/time, I’ll book you in.",
            "is_active": True,
        },
        {
            "question": "Do you handle rentals too?",
            "answer": "Yes, we handle rentals and sales. Tell me if you want rent or buy, the location, and your budget, and I’ll help you immediately.",
            "is_active": True,
        },
    ]

    payload = [{"business_id": business_id, **row} for row in faqs]
    client.table("faqs").insert(payload).execute()
    print({"seeded": len(payload), "businessId": business_id})


if __name__ == "__main__":
    main()

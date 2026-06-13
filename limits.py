import os
from datetime import datetime
from db import DatabaseManager

_free = {"imports_per_month": 3, "ai_generations_per_day": 10, "saved_components": 50, "design_systems": 3}
_pro = {"imports_per_month": -1, "ai_generations_per_day": 500, "saved_components": -1, "design_systems": -1}

def check_limit(db: DatabaseManager, user_id: str, action: str) -> tuple[bool, str]:
    plan = db.get_plan(user_id)
    limits = _pro if plan == "pro" else _free
    now = datetime.now()

    if action == "import":
        limit = limits["imports_per_month"]
        if limit == -1:
            return True, ""
        usage = db.get_usage_stats(user_id)
        if usage["imports_this_month"] >= limit:
            return False, f"Free plan: {limit} imports/month. Upgrade to Pro for unlimited imports."
        return True, ""

    if action == "generate":
        limit = limits["ai_generations_per_day"]
        if limit == -1:
            return True, ""
        usage = db.get_usage_stats(user_id)
        if usage["generations_today"] >= limit:
            return False, f"Free plan: {limit} AI generations/day. Upgrade to Pro for more."
        return True, ""

    return True, ""

from datetime import date

READABLE = {
    "employee": {"all"},
    "manager": {"all", "managers"},
    "hr": {"all", "managers", "hr"},
}


def can_read(role: str, access_level: str) -> bool:
    return access_level in READABLE.get(role, {"all"})


def in_region(regions: list[str], region: str) -> bool:
    return "GLOBAL" in regions or region in regions


def is_eligible(doc: dict, role: str, region: str, reference: date) -> bool:
    return (
        can_read(role, doc["access_level"])
        and in_region(doc["regions"], region)
        and date.fromisoformat(doc["effective_date"]) <= reference
    )


def eligible_doc_ids(docs: list[dict], role: str, region: str, reference: date) -> set[str]:
    return {d["doc_id"] for d in docs if is_eligible(d, role, region, reference)}

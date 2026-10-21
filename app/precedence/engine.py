from dataclasses import dataclass
from datetime import date

HIGH_AUTHORITY = {"policy", "addendum", "memo", "handbook", "calendar"}


def authority_rank(doc_type: str) -> int:
    return 1 if doc_type in HIGH_AUTHORITY else 0


@dataclass
class Doc:
    doc_id: str
    doc_type: str
    regions: list[str]
    effective_date: date

    def scope_rank(self, region: str) -> int:
        return 0 if "GLOBAL" in self.regions and region not in self.regions else 1

    def rank_key(self, region: str) -> tuple:
        return (authority_rank(self.doc_type), self.scope_rank(region), self.effective_date)


def resolve(docs: list[Doc], region: str) -> tuple[list[Doc], bool]:
    """Order eligible docs by precedence (highest first). The second value is
    True when the top candidates are tied and the conflict is unresolved."""
    if not docs:
        return [], False
    ordered = sorted(docs, key=lambda d: d.rank_key(region), reverse=True)
    top = ordered[0].rank_key(region)
    tied = [d for d in ordered if d.rank_key(region) == top]
    return ordered, len(tied) > 1


def upcoming(docs: list[Doc], region: str, reference: date) -> list[Doc]:
    """Future-dated docs that would win on their effective date."""
    result = []
    for d in docs:
        if d.effective_date <= reference:
            continue
        current = [x for x in docs if x.effective_date <= d.effective_date]
        ordered, _ = resolve(current, region)
        if ordered and ordered[0].doc_id == d.doc_id:
            result.append(d)
    return result

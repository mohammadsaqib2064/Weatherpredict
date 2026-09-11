"""Region scoping for climate reads. Analysts are limited to ``region_focus``."""
from __future__ import annotations

from weatherpredict.auth import PermissionDenied, User


def allowed_regions(user: User | None) -> list[str] | None:
    """``None`` = unrestricted. Empty list = assigned no region, so no rows."""
    if user is None or user.is_administrator:
        return None
    focus = (user.region_focus or "").strip()
    return [focus] if focus else []


def constrain_region(user: User | None, requested: str | None = None) -> str | None:
    """Return the region the caller may actually query."""
    allowed = allowed_regions(user)
    if allowed is None:
        return requested or None
    if not allowed:
        raise PermissionDenied(
            "No region is assigned to this Analyst account. "
            "Ask an Administrator to set a region focus."
        )
    if requested and requested not in allowed:
        raise PermissionDenied(
            f"Analyst accounts are scoped to {allowed[0].replace('_', ' ')}; "
            f"'{requested}' is outside that assignment."
        )
    return requested or allowed[0]


def mongo_region_filter(user: User | None, requested: str | None = None) -> dict:
    """Mongo ``find`` clause enforcing the assignment."""
    region = constrain_region(user, requested)
    return {"region": region} if region else {}


def selectable_regions(user: User | None, catalog: list[str] | tuple[str, ...]) -> list[str]:
    """Regions a page may offer in a selectbox."""
    allowed = allowed_regions(user)
    if allowed is None:
        return list(catalog)
    return [r for r in catalog if r in allowed]

from __future__ import annotations


def kc_label(kc_id: str, kcs: dict[str, dict] | None = None) -> str:
    """User-facing KC label: 'kc_id（中文名）'. Falls back to bare kc_id."""
    kc = (kcs or {}).get(kc_id) or {}
    name = kc.get("name")
    if not name or name == kc_id:
        return kc_id
    return f"{kc_id}（{name}）"

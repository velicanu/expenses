"""Accounts: an institution plus whoever's it is. Venmo has more than one (yours, Viral's), so the unit everywhere (the
bao paths, the browser profile, the data file) is the account key: `venmo-viral`, `wealthfront-dragos`, or just `citi`
when there is no owner to tell apart. The existing data files already use these names.

Capital One is linked through Plaid in the expense app, not here.
"""

import re

INSTITUTIONS = {
    "venmo": "Venmo",
    "wealthfront": "Wealthfront",
    "fidelity": "Fidelity",
    "barclays": "Barclays credit card",
    "citi": "Citi credit card",
}

_OWNER = re.compile(r"^[a-z][a-z0-9]{0,19}$")

# What the existing data files show (cards/venmo-dragos, venmo-viral, wealthfront-dragos, barclays-viral, citi) plus
# Fidelity, which has none yet. Shown on first use and then kept in bao, where they can be added to or removed.
DEFAULT_ACCOUNTS = [
    ("venmo", "dragos"),
    ("venmo", "viral"),
    ("wealthfront", "dragos"),
    ("barclays", "viral"),
    ("citi", ""),
    ("fidelity", "dragos"),
]


class AccountError(ValueError):
    pass


def make_key(institution: str, owner: str = "") -> str:
    if institution not in INSTITUTIONS:
        raise AccountError(f"unknown institution {institution!r}")
    owner = (owner or "").strip().lower()
    if owner and not _OWNER.match(owner):
        raise AccountError(
            "the owner is a short lowercase name, letters and digits (for example dragos or viral)"
        )
    return f"{institution}-{owner}" if owner else institution


def label(institution: str, owner: str = "") -> str:
    base = INSTITUTIONS[institution]
    return f"{base} · {owner}" if owner else base


def entry(institution: str, owner: str = "") -> dict:
    owner = (owner or "").strip().lower()
    return {
        "key": make_key(institution, owner),
        "institution": institution,
        "owner": owner,
        "label": label(institution, owner),
    }


def defaults() -> list[dict]:
    return [entry(i, o) for i, o in DEFAULT_ACCOUNTS]


def clean(raw) -> list[dict]:
    """A stored list, re-derived from its institution and owner so a hand-edited or corrupt entry cannot name a path."""
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        try:
            e = entry(str(item.get("institution")), str(item.get("owner", "")))
        except (AccountError, AttributeError):
            continue
        if e["key"] not in seen:
            seen.add(e["key"])
            out.append(e)
    return out

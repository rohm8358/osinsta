"""Command registry shared by CLI and web UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .service import OsinstaService


@dataclass
class Param:
    name: str
    type: str = "string"  # string | integer
    default: Any = None
    description: str = ""
    choices: Optional[list] = None


@dataclass
class Command:
    name: str
    description: str
    needs_target: bool = True
    group: str = "Profile"
    params: list[Param] = field(default_factory=list)
    method: str = ""
    # private_ok = works on private; public_only = needs public feed/network; no_target = no profile
    access: str = "public_only"


COMMANDS: list[Command] = [
    Command("get_user_info", "Profile bio, counts, public contact, bio links", True, "Profile", [], "get_user_info"),
    Command("get_account_about", "About this account: country, join date, rename count", True, "Profile", [], "get_account_about"),
    Command("get_user_propic", "HD profile picture CDN URL", True, "Profile", [], "get_user_propic"),
    Command("get_suggested_profiles", "Accounts Instagram suggests as related", True, "Profile", [], "get_suggested_profiles"),
    Command(
        "get_followers",
        "List followers",
        True,
        "Network",
        [Param("limit", "integer", 200, "Max followers to return")],
        "get_followers",
    ),
    Command(
        "get_followings",
        "List accounts the target follows",
        True,
        "Network",
        [Param("limit", "integer", 200, "Max followings to return")],
        "get_followings",
    ),
    Command(
        "compare_with",
        "Mutual followers / followings with another account",
        True,
        "Network",
        [
            Param("other_username", "string", "", "Other public username"),
            Param("scope", "string", "both", "followers | followings | both", ["both", "followers", "followings"]),
            Param("limit", "integer", 500, "Max per side"),
        ],
        "compare_with",
    ),
    Command(
        "get_people_who_commented",
        "Accounts that commented, ranked by count",
        True,
        "Network",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_people_who_commented",
    ),
    Command(
        "get_people_who_tagged",
        "Accounts that tagged the target",
        True,
        "Network",
        [Param("limit", "integer", None, "Max tagged posts")],
        "get_people_who_tagged",
    ),
    Command(
        "get_people_tagged_by_user",
        "Accounts the target tagged",
        True,
        "Network",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_people_tagged_by_user",
    ),
    Command(
        "get_hashtags",
        "Hashtags used in captions, ranked",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_hashtags",
    ),
    Command(
        "get_captions",
        "Post captions",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_captions",
    ),
    Command(
        "get_addrs",
        "Geotagged locations from posts",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_addrs",
    ),
    Command(
        "get_total_likes",
        "Like totals and per-post stats",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_total_likes",
    ),
    Command(
        "get_total_comments",
        "Comment totals and per-post stats",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_total_comments",
    ),
    Command(
        "get_media_type",
        "Photo / video / carousel breakdown",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_media_type",
    ),
    Command(
        "get_posting_times",
        "Weekday × hour posting heatmap (UTC)",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_posting_times",
    ),
    Command(
        "get_photo_descriptions",
        "Author-written alt text on photos",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_photo_descriptions",
    ),
    Command(
        "get_comment_data",
        "All comments on scanned posts",
        True,
        "Content",
        [Param("limit_posts", "integer", None, "Max posts to scan")],
        "get_comment_data",
    ),
    Command(
        "get_user_photos",
        "Direct CDN URLs for photos",
        True,
        "Media",
        [Param("limit", "integer", None, "Max photos")],
        "get_user_photos",
    ),
    Command("get_user_stories", "Active stories CDN URLs", True, "Media", [], "get_user_stories"),
    Command("get_highlights", "Story highlights list", True, "Media", [], "get_highlights"),
    Command(
        "get_followers_email",
        "Public emails among followers",
        True,
        "Contacts",
        [
            Param("match_limit", "integer", 20, "Max matches"),
            Param("max_checks", "integer", 100, "Max profiles to check"),
        ],
        "get_followers_email",
    ),
    Command(
        "get_followings_email",
        "Public emails among followings",
        True,
        "Contacts",
        [
            Param("match_limit", "integer", 20, "Max matches"),
            Param("max_checks", "integer", 100, "Max profiles to check"),
        ],
        "get_followings_email",
    ),
    Command(
        "get_followers_phone",
        "Public phones among followers",
        True,
        "Contacts",
        [
            Param("match_limit", "integer", 20, "Max matches"),
            Param("max_checks", "integer", 100, "Max profiles to check"),
        ],
        "get_followers_phone",
    ),
    Command(
        "get_followings_phone",
        "Public phones among followings",
        True,
        "Contacts",
        [
            Param("match_limit", "integer", 20, "Max matches"),
            Param("max_checks", "integer", 100, "Max profiles to check"),
        ],
        "get_followings_phone",
    ),
    Command(
        "search_hashtag",
        "Posts for a hashtag (no target needed)",
        False,
        "Search",
        [
            Param("hashtag", "string", "", "Hashtag without or with #"),
            Param("sort", "string", "top", "top or recent", ["top", "recent"]),
            Param("limit", "integer", 30, "Max posts"),
        ],
        "search_hashtag",
    ),
    Command(
        "search_location",
        "Posts from a place (no target needed)",
        False,
        "Search",
        [
            Param("place", "string", "", "Place name"),
            Param("limit", "integer", 30, "Max posts"),
        ],
        "search_location",
    ),
    # ---- Osinsta advanced (beyond Osintgram) ----
    Command("get_contacts", "All public contact pivots in one pack", True, "Advanced", [], "get_contacts"),
    Command("private_recon", "Private-safe recon pack (info/about/pic/suggested/contacts)", True, "Advanced", [], "private_recon"),
    Command(
        "risk_score",
        "Authenticity / risk heuristic score",
        True,
        "Advanced",
        [Param("limit_posts", "integer", 30, "Posts to sample for cadence")],
        "risk_score",
    ),
    Command(
        "timeline_fusion",
        "Merged timeline of posts, stories, highlights",
        True,
        "Advanced",
        [Param("limit_posts", "integer", 40, "Max posts")],
        "timeline_fusion",
    ),
    Command(
        "geo_clusters",
        "Cluster historical geotags (not live location)",
        True,
        "Advanced",
        [Param("limit_posts", "integer", 50, "Max posts to scan")],
        "geo_clusters",
    ),
    Command(
        "caption_intel",
        "Caption NLP: hashtags, mentions, emails/phones/urls",
        True,
        "Advanced",
        [Param("limit_posts", "integer", 40, "Max posts")],
        "caption_intel",
    ),
    Command("expand_bio_links", "Unshorten bio / linktree / lynx URLs", True, "Advanced", [], "expand_bio_links"),
    Command(
        "comment_network",
        "Top commenter network ranking",
        True,
        "Advanced",
        [Param("limit_posts", "integer", 20, "Max posts")],
        "comment_network",
    ),
    Command(
        "graph_overlap",
        "Graph overlap edges with another account",
        True,
        "Advanced",
        [
            Param("other_username", "string", "", "Other username"),
            Param("limit", "integer", 300, "Max per side"),
        ],
        "graph_overlap",
    ),
    Command("watch_snapshot", "Save profile snapshot for change detection", True, "Advanced", [], "watch_snapshot"),
    Command("watch_diff", "Diff last two saved snapshots", True, "Advanced", [], "watch_diff"),
    Command("watch_check", "Snapshot now + diff vs previous", True, "Advanced", [], "watch_check"),
    Command(
        "export_report",
        "Export JSON+HTML evidence pack for key advanced lookups",
        True,
        "Advanced",
        [Param("title", "string", "Osinsta evidence", "Report title")],
        "export_report",
    ),
    Command(
        "estimate_cost",
        "Relative HikerAPI cost hint for a comma-separated command list",
        False,
        "Advanced",
        [Param("commands", "string", "get_user_info,private_recon,risk_score", "Comma-separated command names")],
        "estimate_cost",
    ),
]


# Access mode overrides (default on Command is public_only)
_ACCESS = {
    "get_user_info": "private_ok",
    "get_account_about": "private_ok",
    "get_user_propic": "private_ok",
    "get_suggested_profiles": "private_ok",
    "get_contacts": "private_ok",
    "private_recon": "private_ok",
    "risk_score": "private_ok",
    "expand_bio_links": "private_ok",
    "watch_snapshot": "private_ok",
    "watch_diff": "private_ok",
    "watch_check": "private_ok",
    "export_report": "private_ok",
    "estimate_cost": "no_target",
    "search_hashtag": "no_target",
    "search_location": "no_target",
}

# Human-readable titles for the UI
_LABELS = {
    "get_user_info": "Profile overview",
    "get_account_about": "Account history",
    "get_user_propic": "Profile photo",
    "get_suggested_profiles": "Related accounts",
    "get_followers": "Followers list",
    "get_followings": "Following list",
    "compare_with": "Compare two accounts",
    "get_people_who_commented": "Top commenters",
    "get_people_who_tagged": "Who tagged them",
    "get_people_tagged_by_user": "Who they tagged",
    "get_hashtags": "Hashtag usage",
    "get_captions": "Post captions",
    "get_addrs": "Tagged places",
    "get_total_likes": "Likes summary",
    "get_total_comments": "Comments summary",
    "get_media_type": "Media breakdown",
    "get_posting_times": "Posting schedule",
    "get_photo_descriptions": "Photo alt text",
    "get_comment_data": "All comments",
    "get_user_photos": "Photo links",
    "get_user_stories": "Active stories",
    "get_highlights": "Story highlights",
    "get_followers_email": "Emails in followers",
    "get_followings_email": "Emails in following",
    "get_followers_phone": "Phones in followers",
    "get_followings_phone": "Phones in following",
    "search_hashtag": "Search hashtag",
    "search_location": "Search place",
    "get_contacts": "Contact details",
    "private_recon": "Private-safe scan",
    "risk_score": "Trust / risk score",
    "timeline_fusion": "Activity timeline",
    "geo_clusters": "Location clusters",
    "caption_intel": "Caption insights",
    "expand_bio_links": "Expand bio links",
    "comment_network": "Comment network",
    "graph_overlap": "Network overlap",
    "watch_snapshot": "Save snapshot",
    "watch_diff": "Compare snapshots",
    "watch_check": "Check for changes",
    "export_report": "Export report",
    "estimate_cost": "Estimate API cost",
}

_GROUP_LABELS = {
    "Profile": "Profile",
    "Network": "Network",
    "Content": "Content",
    "Media": "Media",
    "Contacts": "Contacts",
    "Search": "Search",
    "Advanced": "Advanced tools",
}

for _c in COMMANDS:
    _c.access = _ACCESS.get(_c.name, "public_only" if _c.needs_target else "no_target")


def human_label(name: str) -> str:
    return _LABELS.get(name) or name.replace("_", " ").title()


def command_specs() -> list[dict]:
    return [
        {
            "name": c.name,
            "label": human_label(c.name),
            "description": c.description,
            "needs_target": c.needs_target,
            "group": c.group,
            "group_label": _GROUP_LABELS.get(c.group, c.group),
            "access": c.access,
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "default": p.default,
                    "description": p.description,
                    "choices": p.choices,
                }
                for p in c.params
            ],
        }
        for c in COMMANDS
    ]


def get_command(name: str) -> Command:
    for c in COMMANDS:
        if c.name == name:
            return c
    raise KeyError(f"Unknown command: {name}")


def _clean_params(cmd: Command, params: Optional[dict]) -> dict:
    cleaned: dict = {}
    params = params or {}
    for p in cmd.params:
        if p.name not in params or params[p.name] in ("", None):
            if p.default is not None:
                cleaned[p.name] = p.default
            continue
        val = params[p.name]
        if p.type == "integer":
            try:
                val = int(val)
            except (TypeError, ValueError):
                continue
        cleaned[p.name] = val
    return cleaned


def run_command(service: OsinstaService, name: str, params: Optional[dict] = None) -> Any:
    from . import advanced, export, watch

    cmd = get_command(name)
    cleaned = _clean_params(cmd, params)

    # Advanced dispatch (not methods on OsinstaService)
    if name == "get_contacts":
        return advanced.get_contacts(service)
    if name == "private_recon":
        return advanced.private_recon(service)
    if name == "risk_score":
        return advanced.risk_score(service, limit_posts=cleaned.get("limit_posts", 30))
    if name == "timeline_fusion":
        return advanced.timeline_fusion(service, limit_posts=cleaned.get("limit_posts", 40))
    if name == "geo_clusters":
        return advanced.geo_clusters(service, limit_posts=cleaned.get("limit_posts", 50))
    if name == "caption_intel":
        return advanced.caption_intel(service, limit_posts=cleaned.get("limit_posts", 40))
    if name == "expand_bio_links":
        return advanced.expand_bio_links(service)
    if name == "comment_network":
        return advanced.comment_network(service, limit_posts=cleaned.get("limit_posts", 20))
    if name == "graph_overlap":
        from .service import OsinstaError

        other = (cleaned.get("other_username") or "").strip()
        if not other:
            raise OsinstaError("other_username is required")
        return advanced.graph_overlap(service, other, limit=int(cleaned.get("limit") or 300))
    if name == "watch_snapshot":
        return watch.snapshot_profile(service)
    if name == "watch_diff":
        return watch.watch_diff(service.target or "")
    if name == "watch_check":
        return watch.watch_and_diff(service)
    if name == "export_report":
        sections = {
            "contacts": advanced.get_contacts(service),
            "private_recon": advanced.private_recon(service),
            "risk_score": advanced.risk_score(service),
        }
        return export.export_evidence(
            title=cleaned.get("title") or f"Osinsta @{service.target}",
            target=service.target,
            sections=sections,
        )
    if name == "estimate_cost":
        raw = cleaned.get("commands") or ""
        names = [x.strip() for x in str(raw).split(",") if x.strip()]
        return advanced.estimate_cost(names)

    fn: Callable = getattr(service, cmd.method)
    return fn(**cleaned)

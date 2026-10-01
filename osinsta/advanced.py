"""Advanced OSINT capabilities that differentiate Osinsta from Osintgram."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from .service import OsinstaService, normalize_payload

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\-().\s]{7,}\d)")
HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
MENTION_RE = re.compile(r"@([A-Za-z0-9._]+)")
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

# Rough credit weights for planning (relative, not billed invoices).
COMMAND_COST_HINTS = {
    "get_user_info": 1,
    "get_account_about": 1,
    "get_user_propic": 0,
    "get_suggested_profiles": 1,
    "get_followers": 3,
    "get_followings": 3,
    "get_hashtags": 2,
    "get_captions": 2,
    "get_addrs": 3,
    "get_total_likes": 2,
    "get_total_comments": 2,
    "get_media_type": 2,
    "get_posting_times": 2,
    "get_photo_descriptions": 2,
    "get_comment_data": 8,
    "get_people_who_commented": 8,
    "get_people_who_tagged": 3,
    "get_people_tagged_by_user": 2,
    "get_user_photos": 2,
    "get_user_stories": 1,
    "get_highlights": 1,
    "get_followers_email": 15,
    "get_followings_email": 15,
    "get_followers_phone": 15,
    "get_followings_phone": 15,
    "compare_with": 10,
    "search_hashtag": 2,
    "search_location": 3,
    "get_contacts": 1,
    "private_recon": 3,
    "risk_score": 2,
    "timeline_fusion": 3,
    "geo_clusters": 3,
    "caption_intel": 2,
    "expand_bio_links": 1,
}


def estimate_cost(command_names: list[str]) -> dict:
    items = []
    total = 0
    for name in command_names:
        c = COMMAND_COST_HINTS.get(name, 2)
        items.append({"command": name, "relative_cost": c})
        total += c
    return {
        "commands": items,
        "relative_total": total,
        "note": "Relative HikerAPI spend hint only — not an official invoice.",
    }


def _extract_from_text(text: str) -> dict:
    text = text or ""
    return {
        "emails": sorted(set(EMAIL_RE.findall(text))),
        "phones": sorted(set(p.strip() for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 8)),
        "hashtags": sorted(set(HASHTAG_RE.findall(text))),
        "mentions": sorted(set(MENTION_RE.findall(text))),
        "urls": sorted(set(URL_RE.findall(text))),
    }


def expand_url(url: str, timeout: float = 8.0) -> dict:
    """Follow redirects to reveal final destination (linktree/bitly/lynx, etc.)."""
    start = (url or "").strip()
    if not start:
        return {"error": "empty url"}
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.get(start, headers={"User-Agent": "Osinsta/1.0"})
        final = str(resp.url)
        return {
            "original": start,
            "final": final,
            "status_code": resp.status_code,
            "host": urlparse(final).netloc,
            "changed": final.rstrip("/") != start.rstrip("/"),
        }
    except Exception as e:
        return {"original": start, "error": str(e)}


def get_contacts(service: OsinstaService) -> dict:
    """Single-shot public contact pivot pack."""
    info = service.get_user_info()
    bio_bits = _extract_from_text(info.get("biography") or "")
    links = []
    for link in info.get("bio_links") or []:
        if isinstance(link, dict) and link.get("url"):
            links.append({"title": link.get("title"), "url": link["url"]})
    if info.get("external_url"):
        links.append({"title": "external_url", "url": info["external_url"]})

    contacts = {
        "username": service.target,
        "is_private": service.is_private,
        "public_email": info.get("public_email"),
        "contact_phone_number": info.get("contact_phone_number") or info.get("public_phone_number"),
        "whatsapp_number": info.get("whatsapp_number"),
        "business_address": {
            k: info.get(k)
            for k in ("address_street", "city_name", "zip", "latitude", "longitude")
            if info.get(k) not in (None, "", [])
        },
        "fbid_v2": info.get("fbid_v2"),
        "bio_links": links,
        "bio_extracted": bio_bits,
        "profile_pic_url_hd": info.get("profile_pic_url_hd"),
    }
    contacts.update(service._private_meta())
    return contacts


def expand_bio_links(service: OsinstaService) -> dict:
    contacts = get_contacts(service)
    expanded = []
    for link in contacts.get("bio_links") or []:
        expanded.append({**link, **expand_url(link.get("url") or "")})
    for url in (contacts.get("bio_extracted") or {}).get("urls") or []:
        expanded.append({"title": "from_bio_text", "url": url, **expand_url(url)})
    return {
        "username": service.target,
        "links": expanded,
        "count": len(expanded),
        **service._private_meta(),
    }


def private_recon(service: OsinstaService) -> dict:
    """Private-safe recon pack: only lookups that usually work without follow access."""
    out: dict[str, Any] = {
        "username": service.target,
        "is_private": service.is_private,
        "mode": "private_safe",
    }
    try:
        out["profile"] = service.get_user_info()
    except Exception as e:
        out["profile_error"] = str(e)
    try:
        out["about"] = service.get_account_about()
    except Exception as e:
        out["about_error"] = str(e)
    try:
        out["propic"] = service.get_user_propic()
    except Exception as e:
        out["propic_error"] = str(e)
    try:
        out["suggested"] = service.get_suggested_profiles()
    except Exception as e:
        out["suggested_error"] = str(e)
    try:
        out["contacts"] = get_contacts(service)
    except Exception as e:
        out["contacts_error"] = str(e)
    out["available_fields"] = [k for k in ("profile", "about", "propic", "suggested", "contacts") if k in out]
    out.update(service._private_meta())
    return out


def risk_score(service: OsinstaService, limit_posts: Optional[int] = 30) -> dict:
    """Heuristic authenticity / risk signals from public profile + optional feed."""
    info = service.get_user_info()
    about = {}
    try:
        about = service.get_account_about()
    except Exception:
        pass

    signals = []
    score = 50  # baseline

    followers = int(info.get("follower_count") or 0)
    following = int(info.get("following_count") or 0)
    media = int(info.get("media_count") or 0)

    if info.get("is_verified"):
        score += 15
        signals.append({"id": "verified", "effect": +15, "detail": "Verified badge"})
    if service.is_private:
        score -= 5
        signals.append({"id": "private", "effect": -5, "detail": "Private profile (less observable)"})

    if following > 0 and followers / max(following, 1) < 0.05 and following > 500:
        score -= 10
        signals.append({"id": "follow_ratio", "effect": -10, "detail": "Follows many, few followers"})
    if followers > 10000 and media < 3:
        score -= 12
        signals.append({"id": "thin_content", "effect": -12, "detail": "High followers, very few posts"})
    if media == 0:
        score -= 8
        signals.append({"id": "no_posts", "effect": -8, "detail": "Zero posts"})

    rename_count = about.get("former_usernames_count")
    if isinstance(rename_count, int) and rename_count >= 3:
        score -= 8
        signals.append({"id": "renames", "effect": -8, "detail": f"{rename_count} username changes"})
    if about.get("date_joined"):
        signals.append({"id": "joined", "effect": 0, "detail": f"Joined {about.get('date_joined')}"})
    if about.get("country"):
        signals.append({"id": "country", "effect": 0, "detail": f"About country: {about.get('country')}"})

    posting = None
    if not service.is_private:
        try:
            posting = service.get_posting_times(limit_posts=limit_posts)
            avg = posting.get("avg_days_between_posts")
            if avg is not None and avg > 60 and media > 5:
                score -= 5
                signals.append({"id": "sparse_posting", "effect": -5, "detail": f"Avg {avg} days between posts"})
            if posting.get("posts", 0) > 5:
                score += 5
                signals.append({"id": "active_poster", "effect": +5, "detail": "Recent posting activity observed"})
        except Exception as e:
            signals.append({"id": "feed_unavailable", "effect": 0, "detail": str(e)})

    score = max(0, min(100, score))
    band = "low" if score >= 70 else "medium" if score >= 40 else "high"
    return {
        "username": service.target,
        "score": score,
        "risk_band": band,  # high = more suspicious / thin / odd
        "interpretation": {
            "low": "Looks relatively consistent / established",
            "medium": "Mixed signals — review manually",
            "high": "Weak/odd pattern — treat with caution",
        }[band],
        "signals": signals,
        "profile_snapshot": {
            "followers": followers,
            "following": following,
            "media": media,
            "is_private": service.is_private,
            "is_verified": bool(info.get("is_verified")),
            "country": about.get("country"),
            "date_joined": about.get("date_joined"),
        },
        "posting_summary": posting,
        **service._private_meta(),
    }


def caption_intel(service: OsinstaService, limit_posts: Optional[int] = 40) -> dict:
    captions = []
    try:
        captions = service.get_captions(limit_posts=limit_posts)
    except Exception as e:
        return {"username": service.target, "error": str(e), "captions_scanned": 0, **service._private_meta()}

    joined = "\n".join(captions)
    extracted = _extract_from_text(joined)
    hashtag_counts = Counter()
    mention_counts = Counter()
    for cap in captions:
        hashtag_counts.update(HASHTAG_RE.findall(cap or ""))
        mention_counts.update(MENTION_RE.findall(cap or ""))

    # Very light language guess from character ranges
    def lang_guess(text: str) -> str:
        if re.search(r"[\u0900-\u097F]", text):
            return "hi-like"
        if re.search(r"[\u0600-\u06FF]", text):
            return "ar-like"
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh-like"
        if re.search(r"[A-Za-z]", text):
            return "latin-like"
        return "unknown"

    return {
        "username": service.target,
        "captions_scanned": len(captions),
        "language_guess": lang_guess(joined),
        "top_hashtags": [{"tag": t, "count": c} for t, c in hashtag_counts.most_common(25)],
        "top_mentions": [{"user": u, "count": c} for u, c in mention_counts.most_common(25)],
        "emails_in_captions": extracted["emails"],
        "phones_in_captions": extracted["phones"],
        "urls_in_captions": extracted["urls"],
        **service._private_meta(),
    }


def timeline_fusion(service: OsinstaService, limit_posts: Optional[int] = 40) -> dict:
    """Merge posts / stories / highlights into one chronological timeline."""
    events: list[dict] = []

    try:
        feed = service._get_feed(limit=limit_posts)
        for post in feed:
            ts = post.get("taken_at")
            events.append({
                "type": "post",
                "at": ts,
                "at_iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                "id": post.get("id"),
                "caption": ((post.get("caption") or {}).get("text") or "")[:180],
                "permalink": service._post_preview(post).get("permalink"),
                "location": (post.get("location") or {}).get("name"),
                "like_count": post.get("like_count"),
                "comment_count": post.get("comment_count"),
            })
    except Exception as e:
        events.append({"type": "error", "source": "feed", "detail": str(e)})

    try:
        for story in service.get_user_stories():
            events.append({"type": "story", "at": None, "media_type": story.get("media_type"), "url": story.get("url")})
    except Exception as e:
        events.append({"type": "error", "source": "stories", "detail": str(e)})

    try:
        for h in service.get_highlights():
            ts = h.get("last_updated") or h.get("created_at")
            events.append({
                "type": "highlight",
                "at": ts,
                "at_iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if isinstance(ts, (int, float)) else None,
                "title": h.get("title"),
                "media_count": h.get("media_count"),
                "id": h.get("id"),
            })
    except Exception as e:
        events.append({"type": "error", "source": "highlights", "detail": str(e)})

    dated = [e for e in events if isinstance(e.get("at"), (int, float))]
    undated = [e for e in events if not isinstance(e.get("at"), (int, float))]
    dated.sort(key=lambda e: e["at"], reverse=True)
    return {
        "username": service.target,
        "events": dated + undated,
        "counts": {
            "total": len(events),
            "posts": sum(1 for e in events if e.get("type") == "post"),
            "stories": sum(1 for e in events if e.get("type") == "story"),
            "highlights": sum(1 for e in events if e.get("type") == "highlight"),
        },
        **service._private_meta(),
    }


def geo_clusters(service: OsinstaService, limit_posts: Optional[int] = 50) -> dict:
    try:
        addrs = service.get_addrs(limit_posts=limit_posts)
    except Exception as e:
        return {"username": service.target, "error": str(e), "clusters": [], **service._private_meta()}

    buckets: dict[str, dict] = {}
    for item in addrs:
        # ~1km-ish grid
        lat, lng = item.get("lat"), item.get("lng")
        if lat is None or lng is None:
            continue
        key = f"{round(float(lat), 2)},{round(float(lng), 2)}"
        b = buckets.setdefault(key, {"lat": lat, "lng": lng, "names": Counter(), "count": 0, "times": []})
        b["count"] += 1
        if item.get("name"):
            b["names"][item["name"]] += 1
        if item.get("time"):
            b["times"].append(item["time"])

    clusters = []
    for key, b in buckets.items():
        top_name = b["names"].most_common(1)[0][0] if b["names"] else None
        clusters.append({
            "grid": key,
            "lat": b["lat"],
            "lng": b["lng"],
            "visits": b["count"],
            "top_place_name": top_name,
            "place_names": [{"name": n, "count": c} for n, c in b["names"].most_common(5)],
            "last_seen": max(b["times"]) if b["times"] else None,
        })
    clusters.sort(key=lambda c: c["visits"], reverse=True)
    return {
        "username": service.target,
        "clusters": clusters,
        "unique_areas": len(clusters),
        "note": "Historical geotags from posts only — not live location.",
        **service._private_meta(),
    }


def comment_network(service: OsinstaService, limit_posts: Optional[int] = 20) -> dict:
    try:
        people = service.get_people_who_commented(limit_posts=limit_posts)
    except Exception as e:
        return {"username": service.target, "error": str(e), **service._private_meta()}
    return {
        "username": service.target,
        "top_commenters": people[:50],
        "unique_commenters": len(people),
        **service._private_meta(),
    }


def graph_overlap(service_a: OsinstaService, other_username: str, limit: int = 300) -> dict:
    """Relationship overlap between two accounts (graph edge summary)."""
    cmp = service_a.compare_with(other_username, scope="both", limit=limit)
    common_followers = cmp.get("common_followers") or []
    common_followings = cmp.get("common_followings") or []
    return {
        "nodes": [
            {"id": service_a.target, "type": "target", "private": service_a.is_private},
            {"id": cmp.get("other") or other_username, "type": "other", "private": cmp.get("other_is_private")},
        ],
        "edges": {
            "common_followers_count": len(common_followers),
            "common_followings_count": len(common_followings),
        },
        "common_followers": common_followers[:100],
        "common_followings": common_followings[:100],
        "scanned": cmp.get("scanned"),
        "note": "Public-graph overlap only.",
        **{k: v for k, v in cmp.items() if k in ("profile_is_private", "note", "error")},
    }

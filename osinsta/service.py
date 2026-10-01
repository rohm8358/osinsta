"""HikerAPI-backed Instagram public OSINT service for Osinsta.

Only public / API-exposed profile and media data. Private DMs and chats of
other users are not available through HikerAPI and are intentionally unsupported.
"""

from __future__ import annotations

import itertools
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from hikerapi import Client as HikerClient

from .config import resolve_hiker_token

DEFAULT_CONTACT_MAX_CHECKS = int(os.getenv("HIKER_CONTACT_MAX_CHECKS", "100"))
_TYPED_KEY_PREFIX = re.compile(r"^1[a-z](?=[a-z_])")


class OsinstaError(Exception):
    """Base error."""


class TargetNotFoundError(OsinstaError):
    pass


class PrivateProfileError(OsinstaError):
    pass


class HikerAPIError(OsinstaError):
    pass


def normalize_payload(value: Any) -> Any:
    """Map HikerAPI GraphQL-shaped keys back to legacy field names."""
    if isinstance(value, list):
        return [normalize_payload(v) for v in value]
    if isinstance(value, dict):
        out: dict = {}
        for key, item in value.items():
            plain = _TYPED_KEY_PREFIX.sub("", key)
            item = normalize_payload(item)
            if plain in out and out[plain] is not None and item is None:
                continue
            out[plain] = item
        if "pk" not in out and "id" in out and "username" in out:
            out["pk"] = out["id"]
        return out
    return value


def make_client(token: Optional[str] = None) -> HikerClient:
    tok = (token or resolve_hiker_token() or "").strip()
    if not tok:
        raise HikerAPIError(
            "No HikerAPI token. Set HIKERAPI_TOKEN, paste it in the web UI, "
            "or put it in config/credentials.ini"
        )
    return HikerClient(token=tok)


def verify_token(token: str) -> dict:
    """Cheap check that the token works."""
    client = HikerClient(token=token.strip())
    # Any lightweight call — user lookup of a known public account
    data = client.user_by_username_v2("instagram")
    if isinstance(data, dict) and (data.get("error") or data.get("detail")):
        raise HikerAPIError(str(data.get("error") or data.get("detail")))
    return {"ok": True, "backend": "HikerAPI"}


class CountingProxy:
    def __init__(self, client):
        self._wrapped = client
        self.call_count = 0

    def __getattr__(self, name):
        attr = getattr(self._wrapped, name)
        if not callable(attr):
            return attr

        def _counted(*args, **kwargs):
            self.call_count += 1
            return attr(*args, **kwargs)

        return _counted


class OsinstaService:
    """Public Instagram OSINT capabilities over HikerAPI."""

    _EXTRA_PROFILE_FIELDS = (
        "external_url",
        "public_email",
        "contact_phone_number",
        "public_phone_country_code",
        "public_phone_number",
        "whatsapp_number",
        "business_contact_method",
        "address_street",
        "city_name",
        "zip",
        "latitude",
        "longitude",
        "instagram_location_id",
        "category",
        "category_name",
        "business_category_name",
        "account_type",
        "is_memorialized",
        "fbid_v2",
        "total_clips_count",
        "total_igtv_videos",
        "usertags_count",
        "highlight_reel_count",
    )

    _MEDIA_TYPE_NAMES = {1: "photo", 2: "video", 8: "carousel"}

    def __init__(self, target: Optional[str], api_client):
        self._backend = api_client
        self.api = CountingProxy(api_client)
        self.geolocator = Nominatim(user_agent="osinsta")
        self._reverse_geocode = RateLimiter(
            self.geolocator.reverse, min_delay_seconds=1, max_retries=2, swallow_exceptions=True
        )
        self.target = (target or "").strip().lstrip("@") or None
        self.user: dict = self._fetch_user(self.target) if self.target else {}
        self.target_id = self.user.get("pk")
        self.is_private = self._as_bool(self.user.get("is_private"))

    @property
    def api_call_count(self) -> int:
        return self.api.call_count

    @staticmethod
    def _as_bool(value) -> bool:
        """Coerce Instagram/HikerAPI truthy flags (bool / 0|1 / 'true'|'false')."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return False

    def _fetch_user(self, username: str) -> dict:
        try:
            data = self.api.user_by_username_v2(username)
        except Exception as e:
            raise HikerAPIError(str(e)) from e
        if isinstance(data, dict) and "error" in data:
            raise HikerAPIError(str(data["error"]))
        if isinstance(data, dict) and "detail" in data:
            raise TargetNotFoundError(f"@{username} not found: {data['detail']}")
        user = normalize_payload(data.get("user") if isinstance(data, dict) else {})
        if not user:
            raise TargetNotFoundError(f"@{username} not found")
        return user

    def _require_target(self) -> None:
        if not self.target_id:
            raise OsinstaError("This command needs a target username.")

    def _require_public(self) -> None:
        """Ensure a target is set.

        Private profiles are NOT hard-blocked. Profile metadata is always
        public-facing, and HikerAPI often still returns usable graph/media
        payloads for private accounts — same practical behaviour users expect
        from Osintgram + HikerAPI. If the backend refuses, we surface that
        empty/error result instead of failing before the request.
        """
        self._require_target()

    def _private_meta(self) -> dict:
        if not self.is_private:
            return {}
        return {
            "profile_is_private": True,
            "note": (
                f"@{self.target} is marked private. Returning whatever HikerAPI "
                "still exposes (profile fields always; lists/media when available)."
            ),
        }

    def _iter_items(self, api_method, results_key: str, cursor_param: str = "page_id", user_id=None):
        subject = self.target_id if user_id is None else user_id
        next_page_id = None
        while True:
            try:
                result = api_method(subject, **({cursor_param: next_page_id} if next_page_id else {}))
            except Exception:
                return
            if not isinstance(result, dict):
                return
            if result.get("error") or result.get("detail"):
                return
            payload = normalize_payload(result.get("response", {}) or {})
            yield from payload.get(results_key, [])
            next_page_id = result.get("next_page_id")
            if not next_page_id:
                return

    def _paginate(self, api_method, results_key: str, limit: Optional[int] = None,
                  cursor_param: str = "page_id", user_id=None) -> list:
        return list(itertools.islice(self._iter_items(api_method, results_key, cursor_param, user_id), limit))

    def _get_feed(self, limit: Optional[int] = None) -> list:
        return self._paginate(self.api.user_medias_g2, "items", limit=limit, cursor_param="next_page_id")

    def _get_comments(self, media_id, limit: Optional[int] = None) -> list:
        data: list = []
        next_page_id = ""
        while True:
            try:
                result = self.api.media_comments_v2(media_id, page_id=next_page_id)
            except Exception as e:
                if "Entries not found" in str(e):
                    return data
                raise HikerAPIError(str(e)) from e
            data.extend(normalize_payload(result.get("response", {}).get("comments", [])))
            next_page_id = result.get("next_page_id")
            if limit is not None and len(data) >= limit:
                return data[:limit]
            if not next_page_id:
                break
        return data

    @staticmethod
    def _summarize_user(user: dict) -> dict:
        return {
            "id": user.get("pk") or user.get("id"),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "is_private": user.get("is_private"),
            "is_verified": user.get("is_verified"),
        }

    @classmethod
    def _media_files(cls, media: dict) -> dict:
        candidates = (media.get("image_versions2") or {}).get("candidates") or []
        sized = [c for c in candidates if (c.get("width") or 0) >= 320]
        thumbnail = min(sized, key=lambda c: c["width"]) if sized else (candidates[0] if candidates else {})
        largest = max(candidates, key=lambda c: c.get("width") or 0) if candidates else {}
        videos = media.get("video_versions") or []
        media_url = videos[0].get("url") if media.get("media_type") == 2 and videos else largest.get("url")
        return {
            "media_type": cls._MEDIA_TYPE_NAMES.get(media.get("media_type"), "other"),
            "thumbnail_url": thumbnail.get("url"),
            "media_url": media_url,
        }

    @staticmethod
    def _play_count(post: dict) -> Optional[int]:
        return post.get("play_count") or post.get("ig_play_count") or post.get("view_count")

    @staticmethod
    def _coauthors(post: dict) -> list:
        return [u.get("username") for u in post.get("coauthor_producers") or [] if u.get("username")]

    @staticmethod
    def _audio_label(post: dict) -> Optional[str]:
        for meta in (post.get("clips_metadata"), post.get("music_metadata")):
            if not meta:
                continue
            song = (meta.get("music_info") or {}).get("music_asset_info") or {}
            if song.get("title"):
                return " — ".join(filter(None, [song["title"], song.get("display_artist")]))
            sound = meta.get("original_sound_info") or {}
            if sound.get("original_audio_title"):
                artist = (sound.get("ig_artist") or {}).get("username")
                return " — ".join(filter(None, [sound["original_audio_title"], artist and f"@{artist}"]))
        return None

    @classmethod
    def _post_preview(cls, post: dict) -> dict:
        slides = [cls._media_files(s) for s in post.get("carousel_media") or []]
        files = cls._media_files(post)
        if slides and not files["thumbnail_url"]:
            files = {**slides[0], "media_type": files["media_type"]}
        code = post.get("code")
        path = "reel" if post.get("product_type") == "clips" else "p"
        caption = (post.get("caption") or {}).get("text") or ""
        return {
            "id": post.get("id"),
            **files,
            "slides": slides or None,
            "permalink": f"https://www.instagram.com/{path}/{code}/" if code else None,
            "like_count": post.get("like_count"),
            "comment_count": post.get("comment_count"),
            "play_count": cls._play_count(post),
            "taken_at": post.get("taken_at"),
            "caption": caption[:120],
            "coauthors": cls._coauthors(post),
            "paid_partnership": bool(post.get("is_paid_partnership")),
            "audio": cls._audio_label(post),
            "author": (post.get("user") or {}).get("username"),
        }

    @staticmethod
    def _v1_media_to_legacy(media: dict) -> dict:
        """Normalize chunked media objects into the shape _post_preview expects."""
        m = dict(media or {})
        if "caption" in m and isinstance(m["caption"], str):
            m["caption"] = {"text": m["caption"]}
        if "user" not in m and m.get("username"):
            m["user"] = {"username": m.get("username"), "pk": m.get("user_id") or m.get("pk")}
        return m

    @classmethod
    def _authors(cls, posts: list) -> list:
        seen: dict = {}
        for post in posts:
            user = post.get("user") or {}
            pk = user.get("pk") or user.get("id")
            if pk is None:
                continue
            if pk not in seen:
                seen[pk] = {**cls._summarize_user(user), "posts": 0}
            seen[pk]["posts"] += 1
        return sorted(seen.values(), key=lambda u: u["posts"], reverse=True)

    # ---- capabilities ----

    def get_user_info(self) -> dict:
        self._require_target()
        data = self.user
        info = {
            "id": data.get("pk"),
            "username": self.target,
            "full_name": data.get("full_name"),
            "biography": data.get("biography"),
            "follower_count": data.get("follower_count"),
            "following_count": data.get("following_count"),
            "media_count": data.get("media_count"),
            "is_private": self.is_private,
            "is_business": self._as_bool(data.get("is_business")),
            "is_verified": self._as_bool(data.get("is_verified")),
            "profile_pic_url_hd": (data.get("hd_profile_pic_url_info") or {}).get("url"),
        }
        info.update(self._private_meta())
        for key in self._EXTRA_PROFILE_FIELDS:
            if data.get(key) not in (None, "", [], {}):
                info[key] = data[key]
        links = [
            {"title": link.get("title") or None, "url": link.get("url") or link.get("lynx_url")}
            for link in (data.get("bio_links") or [])
            if isinstance(link, dict) and (link.get("url") or link.get("lynx_url"))
        ]
        if links:
            info["bio_links"] = links
        pronouns = [p for p in (data.get("pronouns") or []) if p]
        if pronouns:
            info["pronouns"] = "/".join(pronouns)
        return info

    def get_account_about(self) -> dict:
        self._require_target()
        data = normalize_payload(self.api.user_about_gql(str(self.target_id)))
        if not isinstance(data, dict) or not data:
            return {"username": self.target, "error": 'No "About this account" data available.'}
        info = {
            "username": data.get("username") or self.target,
            "is_verified": data.get("is_verified"),
            "country": data.get("country") or None,
            "date_joined": data.get("date") or None,
        }
        former = str(data.get("former_usernames") or "").strip()
        if former.isdigit():
            info["former_usernames_count"] = int(former)
        elif former:
            names = [u.strip() for u in re.split(r"[,\n]", former) if u.strip()]
            info["former_usernames_count"] = len(names)
            info["former_usernames"] = names
        else:
            info["former_usernames_count"] = 0
        return info

    def get_followers(self, limit: Optional[int] = 200) -> dict:
        self._require_public()
        try:
            users = [self._summarize_user(u) for u in self._paginate(self.api.user_followers_g2, "users", limit=limit)]
        except Exception as e:
            return {**self._private_meta(), "error": str(e), "followers": [], "count": 0}
        return {**self._private_meta(), "count": len(users), "followers": users}

    def get_followings(self, limit: Optional[int] = 200) -> dict:
        self._require_public()
        try:
            users = [self._summarize_user(u) for u in self._paginate(self.api.user_following_g2, "users", limit=limit)]
        except Exception as e:
            return {**self._private_meta(), "error": str(e), "followings": [], "count": 0}
        return {**self._private_meta(), "count": len(users), "followings": users}

    def get_hashtags(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        counter: dict = {}
        for post in self._get_feed(limit=limit_posts):
            caption = post.get("caption") or {}
            for word in (caption.get("text") or "").split():
                if word.startswith("#"):
                    counter[word] = counter.get(word, 0) + 1
        return [{"hashtag": h, "count": c} for h, c in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)]

    def get_addrs(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        locations: dict = {}
        for post in self._get_feed(limit=limit_posts):
            location = post.get("location")
            if location and location.get("lat") is not None and location.get("lng") is not None:
                lat, lng = location["lat"], location["lng"]
                key = f"{lat}, {lng}"
                taken_at = post.get("taken_at")
                prev = locations.get(key)
                if prev is None or (taken_at or 0) > (prev[1] or 0):
                    locations[key] = (lat, lng, taken_at, location.get("name"))
        addresses = []
        failed = 0
        for coords, (lat, lng, taken_at, name) in locations.items():
            details = self._reverse_geocode(coords)
            if details is None:
                failed += 1
                addresses.append({
                    "address": None,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                    "time": datetime.fromtimestamp(taken_at).strftime("%Y-%m-%d %H:%M:%S") if taken_at else None,
                })
                continue
            addresses.append({
                "address": details.address,
                "name": name,
                "lat": lat,
                "lng": lng,
                "time": datetime.fromtimestamp(taken_at).strftime("%Y-%m-%d %H:%M:%S") if taken_at else None,
            })
        return sorted(addresses, key=lambda a: a["time"] or "", reverse=True)

    def get_captions(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        return [
            (item.get("caption") or {}).get("text")
            for item in self._get_feed(limit=limit_posts)
            if (item.get("caption") or {}).get("text")
        ]

    def get_total_comments(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        counts = [int(p.get("comment_count", 0) or 0) for p in data]
        if not counts:
            return {"comment_counter": 0, "posts": 0, "min": 0, "max": 0, "avg": 0, "previews": []}
        total = sum(counts)
        return {
            "comment_counter": total,
            "posts": len(counts),
            "min": min(counts),
            "max": max(counts),
            "avg": total // len(counts),
            "previews": [self._post_preview(p) for p in data],
        }

    def get_total_likes(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        counts = [int(p.get("like_count", 0) or 0) for p in data]
        if not counts:
            return {"like_counter": 0, "posts": 0, "min": 0, "max": 0, "avg": 0, "previews": []}
        total = sum(counts)
        return {
            "like_counter": total,
            "posts": len(counts),
            "min": min(counts),
            "max": max(counts),
            "avg": total // len(counts),
            "previews": [self._post_preview(p) for p in data],
        }

    def get_media_type(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        data = self._get_feed(limit=limit_posts)
        photos = sum(1 for p in data if p.get("media_type") == 1)
        videos = sum(1 for p in data if p.get("media_type") == 2)
        carousels = sum(1 for p in data if p.get("media_type") == 8)
        plays = [n for n in (self._play_count(p) for p in data if p.get("media_type") == 2) if n]
        return {
            "photos": photos,
            "videos": videos,
            "carousels": carousels,
            "total": len(data),
            "video_plays_total": sum(plays),
            "video_plays_avg": sum(plays) // len(plays) if plays else 0,
            "collaborations": sum(1 for p in data if self._coauthors(p)),
            "paid_partnerships": sum(1 for p in data if p.get("is_paid_partnership")),
            "previews": [self._post_preview(p) for p in data],
        }

    def get_posting_times(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        times = sorted(p["taken_at"] for p in self._get_feed(limit=limit_posts) if p.get("taken_at"))
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        by_weekday = dict.fromkeys(weekdays, 0)
        by_hour = {f"{h:02d}": 0 for h in range(24)}
        for t in times:
            when = datetime.fromtimestamp(t, tz=timezone.utc)
            by_weekday[weekdays[when.weekday()]] += 1
            by_hour[f"{when.hour:02d}"] += 1
        if not times:
            return {"posts": 0, "timezone": "UTC", "by_weekday": by_weekday, "by_hour": by_hour}
        busiest_hour = int(max(by_hour, key=by_hour.get))
        gaps = [(b - a) / 86400 for a, b in zip(times, times[1:])]
        return {
            "posts": len(times),
            "timezone": "UTC",
            "most_active_day": max(by_weekday, key=by_weekday.get),
            "most_active_hour": f"{busiest_hour:02d}:00-{(busiest_hour + 1) % 24:02d}:00",
            "first_post": datetime.fromtimestamp(times[0], tz=timezone.utc).strftime("%Y-%m-%d"),
            "last_post": datetime.fromtimestamp(times[-1], tz=timezone.utc).strftime("%Y-%m-%d"),
            "avg_days_between_posts": round(sum(gaps) / len(gaps), 1) if gaps else None,
            "by_weekday": by_weekday,
            "by_hour": by_hour,
        }

    def get_photo_descriptions(self, limit_posts: Optional[int] = None) -> dict:
        self._require_public()
        photos = [
            (media, post)
            for post in self._get_feed(limit=limit_posts)
            for media in post.get("carousel_media") or [post]
            if media.get("media_type") == 1
        ]
        descriptions = [
            {
                "description": media["accessibility_caption"],
                "taken_at": media.get("taken_at") or post.get("taken_at"),
                **self._media_files(media),
            }
            for media, post in photos
            if media.get("accessibility_caption")
        ]
        return {"photos_scanned": len(photos), "with_alt_text": len(descriptions), "descriptions": descriptions}

    def get_comment_data(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        comments = []
        for post in self._get_feed(limit=limit_posts):
            post_id = post.get("id")
            for comment in self._get_comments(post_id):
                comments.append({
                    "post_id": post_id,
                    "user_id": comment.get("user_id"),
                    "username": (comment.get("user") or {}).get("username"),
                    "comment": comment.get("text"),
                })
        return comments

    def get_people_who_commented(self, limit_posts: Optional[int] = None) -> list:
        self._require_public()
        users: dict = {}
        for post in self._get_feed(limit=limit_posts):
            for comment in self._get_comments(post.get("id")):
                user = comment.get("user") or {}
                pk = user.get("pk")
                if pk is None:
                    continue
                if pk in users:
                    users[pk]["counter"] += 1
                else:
                    users[pk] = {
                        "id": pk,
                        "username": user.get("username"),
                        "full_name": user.get("full_name"),
                        "counter": 1,
                    }
        return sorted(users.values(), key=lambda u: u["counter"], reverse=True)

    def get_people_who_tagged(self, limit: Optional[int] = None) -> list:
        self._require_public()
        users: dict = {}
        for post in self._paginate(self.api.user_tag_medias_v2, "items", limit=limit):
            tag = post.get("user") or {}
            pk = tag.get("pk")
            if pk is None:
                continue
            if pk in users:
                users[pk]["counter"] += 1
            else:
                users[pk] = {
                    "id": pk,
                    "username": tag.get("username"),
                    "full_name": tag.get("full_name"),
                    "counter": 1,
                }
        return sorted(users.values(), key=lambda u: u["counter"], reverse=True)

    def get_people_tagged_by_user(self, limit_posts: Optional[int] = None) -> list:
        self._require_target()
        tagged: dict = {}
        for post in self._get_feed(limit=limit_posts):
            usertags = post.get("usertags") or []
            if isinstance(usertags, dict):
                usertags = usertags.get("in") or []
            for tag in usertags:
                user = tag.get("user") or {}
                pk = user.get("pk")
                if pk is None:
                    continue
                if pk in tagged:
                    tagged[pk]["posts"] += 1
                else:
                    tagged[pk] = {
                        "id": pk,
                        "username": user.get("username"),
                        "full_name": user.get("full_name"),
                        "posts": 1,
                    }
        return sorted(tagged.values(), key=lambda u: u["posts"], reverse=True)

    def get_user_photos(self, limit: Optional[int] = None) -> list:
        self._require_public()
        photos = []
        for item in self._iter_items(self.api.user_medias_g2, "items", cursor_param="next_page_id"):
            candidates = (item.get("carousel_media") or []) if item.get("media_type") == 8 else [item]
            for media in candidates:
                if media.get("media_type") != 1:
                    continue
                if limit is not None and len(photos) >= limit:
                    return photos
                versions = (media.get("image_versions2") or {}).get("candidates", [])
                if versions:
                    photos.append({"id": media.get("id"), "url": versions[0]["url"]})
        return photos

    def get_user_propic(self) -> dict:
        self._require_target()
        info = self.user.get("hd_profile_pic_url_info")
        if info and info.get("url"):
            return {"url": info["url"]}
        versions = self.user.get("hd_profile_pic_versions") or []
        if versions:
            return {"url": versions[-1]["url"]}
        raise HikerAPIError("No profile picture available")

    def get_user_stories(self) -> list:
        self._require_public()
        data = self.api.user_stories_v2(self.target_id)
        reel = data.get("reel") if isinstance(data, dict) else None
        if not reel:
            return []
        stories = []
        for item in reel.get("items", []):
            image_candidates = (item.get("image_versions2") or {}).get("candidates") or []
            image_url = image_candidates[0].get("url") if image_candidates else None
            if item.get("media_type") == 1 and image_url:
                stories.append({"id": item.get("id"), "media_type": "photo", "url": image_url})
            elif item.get("media_type") == 2 and item.get("video_versions"):
                story = {"id": item.get("id"), "media_type": "video", "url": item["video_versions"][0]["url"]}
                if image_url:
                    story["thumbnail_url"] = image_url
                stories.append(story)
        return stories

    def get_highlights(self) -> list:
        self._require_public()
        data = self.api.user_highlights_v2(self.target_id)
        tray = (data.get("response") or {}).get("tray") or []
        highlights = []
        for item in tray:
            cover = item.get("cover_media") or {}
            image = cover.get("cropped_image_version") or cover.get("full_image_version") or {}
            highlights.append({
                "id": (item.get("id") or "").split(":")[-1] or None,
                "title": item.get("title"),
                "media_count": item.get("media_count"),
                "thumbnail_url": image.get("url"),
                "created_at": item.get("created_at"),
                "last_updated": item.get("latest_reel_media"),
            })
        return highlights

    def get_suggested_profiles(self) -> list:
        self._require_target()
        data = self.api.user_suggested_profiles_v2(self.target_id)
        suggestions = []
        for user in normalize_payload(data.get("users") or []):
            entry = self._summarize_user(user)
            context = user.get("social_context")
            if context and context != user.get("full_name"):
                entry["context"] = context
            suggestions.append(entry)
        return suggestions

    def search_hashtag(self, hashtag: str, sort: str = "top", limit: Optional[int] = 30) -> dict:
        name = (hashtag or "").strip().lstrip("#")
        if not name:
            raise OsinstaError("Specify a hashtag to search for.")
        if sort not in ("top", "recent"):
            raise OsinstaError(f"invalid sort: {sort!r} (use top or recent)")
        method = self.api.hashtag_medias_top_v2 if sort == "top" else self.api.hashtag_medias_recent_v2
        posts: list = []
        page_id = None
        while limit is None or len(posts) < limit:
            result = method(name, **({"page_id": page_id} if page_id else {}))
            response = normalize_payload(result.get("response") or {})
            for section in response.get("sections") or []:
                for entry in (section.get("layout_content") or {}).get("medias") or []:
                    if entry.get("media"):
                        posts.append(entry["media"])
            posts.extend(self._v1_media_to_legacy(m) for m in response.get("items") or [])
            page_id = result.get("next_page_id")
            if not page_id:
                break
        posts = posts[:limit] if limit is not None else posts
        return {
            "hashtag": f"#{name}",
            "sort": sort,
            "posts": len(posts),
            "authors": self._authors(posts),
            "previews": [self._post_preview(p) for p in posts],
        }

    def search_location(self, place: str, limit: Optional[int] = 30) -> dict:
        query = (place or "").strip()
        if not query:
            raise OsinstaError("Specify a place to search for.")
        found = normalize_payload(self.api.fbsearch_places_v2(query))
        places = [item.get("location") or {} for item in found.get("items") or []]
        places = [p for p in places if p.get("pk")]
        if not places:
            raise OsinstaError(f"No place found for {query!r}.")
        matched = places[0]
        posts: list = []
        max_id = None
        while limit is None or len(posts) < limit:
            chunk = self.api.location_medias_recent_chunk_v1(
                int(matched["pk"]), **({"max_id": max_id} if max_id else {})
            )
            medias, max_id = (chunk + [None, None])[:2] if isinstance(chunk, list) else ([], None)
            posts.extend(self._v1_media_to_legacy(m) for m in normalize_payload(medias or []))
            if not max_id or not medias:
                break
        posts = posts[:limit] if limit is not None else posts
        return {
            "place": {
                "name": matched.get("name"),
                "address": matched.get("address"),
                "city": matched.get("city"),
                "lat": matched.get("lat"),
                "lng": matched.get("lng"),
            },
            "alternatives": [p.get("name") for p in places[1:6]],
            "posts": len(posts),
            "authors": self._authors(posts),
            "previews": [self._post_preview(p) for p in posts],
        }

    def compare_with(self, other_username: str, scope: str = "both", limit: Optional[int] = 500) -> dict:
        scope = (scope or "both").lower()
        if scope not in ("followers", "followings", "both"):
            raise OsinstaError(f"invalid scope: {scope!r}")
        self._require_public()
        other = self._fetch_user(other_username.strip().lstrip("@"))
        other_id = other["pk"]
        other_private = self._as_bool(other.get("is_private"))

        def common(mine, theirs):
            by_pk = {u["pk"]: u for u in mine}
            return [self._summarize_user(by_pk[u["pk"]]) for u in theirs if u["pk"] in by_pk]

        result = {
            "target": self.target,
            "other": other.get("username") or other_username,
            "scope": scope,
            "other_is_private": other_private,
            **self._private_meta(),
        }
        scanned = {}
        try:
            if scope in ("followers", "both"):
                mine = self._paginate(self.api.user_followers_g2, "users", limit=limit)
                theirs = self._paginate(self.api.user_followers_g2, "users", limit=limit, user_id=other_id)
                result["common_followers"] = common(mine, theirs)
                scanned["target_followers"] = len(mine)
                scanned["other_followers"] = len(theirs)
            if scope in ("followings", "both"):
                mine = self._paginate(self.api.user_following_g2, "users", limit=limit)
                theirs = self._paginate(self.api.user_following_g2, "users", limit=limit, user_id=other_id)
                result["common_followings"] = common(mine, theirs)
                scanned["target_followings"] = len(mine)
                scanned["other_followings"] = len(theirs)
        except Exception as e:
            result["error"] = str(e)
        result["scanned"] = scanned
        return result

    def _contact_info(self, api_method, from_key: str, to_key: str,
                      match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        self._require_public()
        candidates = self._paginate(api_method, "users", limit=max_checks)
        results = []
        checked = 0
        for user in candidates:
            if (match_limit is not None and len(results) >= match_limit) or (
                max_checks is not None and checked >= max_checks
            ):
                break
            checked += 1
            detail = normalize_payload(self.api.user_by_id_v2(user["pk"]))
            value = (detail.get("user") or {}).get(from_key)
            if value:
                results.append({
                    "id": user["pk"],
                    "username": user.get("username"),
                    "full_name": user.get("full_name"),
                    to_key: value,
                })
        return results

    def get_followers_email(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(self.api.user_followers_g2, "public_email", "email", match_limit, max_checks)

    def get_followings_email(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(self.api.user_following_g2, "public_email", "email", match_limit, max_checks)

    def get_followers_phone(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(
            self.api.user_followers_g2, "contact_phone_number", "contact_phone_number", match_limit, max_checks
        )

    def get_followings_phone(self, match_limit: int = 20, max_checks: int = DEFAULT_CONTACT_MAX_CHECKS) -> list:
        return self._contact_info(
            self.api.user_following_g2, "contact_phone_number", "contact_phone_number", match_limit, max_checks
        )


def build_service(target: Optional[str], token: Optional[str] = None) -> OsinstaService:
    return OsinstaService(target, make_client(token))

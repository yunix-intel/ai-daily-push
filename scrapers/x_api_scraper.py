#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional official X API v2 client with deterministic RSS-compatible output.

The client is deliberately opt-in: without ``X_BEARER_TOKEN`` callers should
continue using the existing RSSHub fallback.  API responses are normalized to
the fields consumed by the finance dashboard and malformed/failed responses
return a structured unavailable result rather than leaking exceptions.
"""
import os
from datetime import datetime
from typing import Dict, List, Optional

import requests


class XApiScraper:
    """Fetch public X posts from the official API v2."""

    BASE_URL = "https://api.x.com/2"

    def __init__(self, bearer_token: Optional[str] = None, timeout: Optional[float] = None):
        self.bearer_token = bearer_token or os.getenv("X_BEARER_TOKEN", "")
        self.timeout = timeout if timeout is not None else float(os.getenv("X_API_TIMEOUT", "10"))
        self.base_url = os.getenv("X_API_BASE_URL", self.BASE_URL).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.bearer_token)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer_token}", "User-Agent": "ai-daily-push/4"}

    def _get(self, path: str, params: Dict) -> Dict:
        response = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(), params=params, timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("X API response must be an object")
        return payload

    @staticmethod
    def _failure_state(exc) -> str:
        """Map transport failures to public provenance states."""
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if status in (401, 403):
            return "auth_failed"
        if status == 429:
            return "quota_limited"
        return "source_failed"

    @staticmethod
    def _unavailable(error: str, state: str, **extra) -> Dict:
        return {
            "tweets": [], "available": False, "error": error,
            "source": "official_x_api", "provenance": state,
            "attempted_sources": ["official_x_api"], **extra,
        }

    @staticmethod
    def _normalize(post: Dict, users: Dict[str, Dict]) -> Dict:
        author_id = str(post.get("author_id", ""))
        author = users.get(author_id, {})
        created = post.get("created_at")
        pub_date = None
        if created:
            try:
                pub_date = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                pass
        username = author.get("username", author_id)
        return {
            "title": str(post.get("text", "")).split("\n", 1)[0][:200],
            "content": str(post.get("text", "")),
            "link": f"https://x.com/{username}/status/{post.get('id', '')}",
            "pub_date": pub_date,
            "username": username,
            "author_id": author_id,
            "id": str(post.get("id", "")),
            "conversation_id": str(post.get("conversation_id", "")),
            "in_reply_to_user_id": str(post.get("in_reply_to_user_id", "")),
            "public_metrics": post.get("public_metrics", {}),
            "source": "official_x_api",
        }

    def _result(self, posts: List[Dict], users: Dict[str, Dict], **extra) -> Dict:
        state = "official_x_api" if posts else "no_content"
        return {
            "tweets": [self._normalize(p, users) for p in posts],
            "available": bool(posts), "provenance": state,
            "attempted_sources": ["official_x_api"], **extra,
        }

    def lookup_user(self, username: str) -> Dict:
        """Resolve a public username to its X user id."""
        if not self.configured:
            return self._unavailable("X_BEARER_TOKEN 未配置", "not_configured")
        if not str(username).strip():
            return {"available": False, "error": "username 不能为空"}
        try:
            payload = self._get(f"users/by/username/{str(username).strip()}", {
                "user.fields": "username,name,verified",
            })
            user = payload.get("data")
            if not isinstance(user, dict) or not user.get("id"):
                raise ValueError("X API user data missing")
            return {"available": True, "user": user, "source": "official_x_api"}
        except Exception as exc:
            return self._unavailable(repr(exc), self._failure_state(exc))

    def fetch_username_tweets(self, username: str, limit: int = 10) -> Dict:
        """Resolve a username and fetch its timeline."""
        lookup = self.lookup_user(username)
        if not lookup.get("available"):
            return self._unavailable(
                lookup.get("error", "用户解析失败"),
                lookup.get("provenance", "source_failed"),
            )
        return self.fetch_user_tweets(str(lookup["user"]["id"]), limit=limit)

    def fetch_user_tweets(self, user_id: str, limit: int = 10,
                          pagination_token: Optional[str] = None) -> Dict:
        """Fetch one user's posts, including public metrics and author data."""
        if not self.configured:
            return self._unavailable("X_BEARER_TOKEN 未配置", "not_configured")
        try:
            params = {
                "max_results": max(5, min(100, int(limit))),
                "tweet.fields": "created_at,public_metrics,author_id,conversation_id,lang",
                "expansions": "author_id",
                "user.fields": "username,name,verified",
            }
            if pagination_token:
                params["pagination_token"] = pagination_token
            payload = self._get(f"users/{user_id}/tweets", params)
            includes = payload.get("includes") or {}
            users = {str(u.get("id")): u for u in includes.get("users", []) if isinstance(u, dict)}
            posts = payload.get("data") or []
            if not isinstance(posts, list):
                raise ValueError("X API data must be a list")
            return self._result(posts[:limit], users,
                                next_token=(payload.get("meta") or {}).get("next_token", ""),
                                source="official_x_api")
        except Exception as exc:
            return self._unavailable(repr(exc), self._failure_state(exc))

    def search_recent(self, query: str, limit: int = 10,
                      next_token: Optional[str] = None) -> Dict:
        """Search recent public posts for cashtags, news terms, or comments."""
        if not self.configured:
            return self._unavailable("X_BEARER_TOKEN 未配置", "not_configured")
        if not str(query).strip():
            return self._unavailable("query 不能为空", "source_failed")
        try:
            params = {
                "query": str(query).strip(),
                "max_results": max(10, min(100, int(limit))),
                "tweet.fields": "created_at,public_metrics,author_id,conversation_id,lang,in_reply_to_user_id",
                "expansions": "author_id",
                "user.fields": "username,name,verified",
            }
            if next_token:
                params["next_token"] = next_token
            payload = self._get("tweets/search/recent", params)
            includes = payload.get("includes") or {}
            users = {str(u.get("id")): u for u in includes.get("users", []) if isinstance(u, dict)}
            posts = payload.get("data") or []
            if not isinstance(posts, list):
                raise ValueError("X API data must be a list")
            return self._result(posts[:limit], users,
                                next_token=(payload.get("meta") or {}).get("next_token", ""),
                                source="official_x_api", query=query)
        except Exception as exc:
            return self._unavailable(repr(exc), self._failure_state(exc), query=query)

    def fetch_finance_comments(self, terms: List[str], limit: int = 20) -> Dict:
        """Search finance discussion while excluding retweets and quote noise."""
        clean_terms = [str(term).strip() for term in terms if str(term).strip()]
        if not clean_terms:
            return self._unavailable("terms 不能为空", "source_failed")
        query = " OR ".join(clean_terms) + " lang:en -is:retweet"
        result = self.search_recent(query, limit=limit)
        for tweet in result.get("tweets", []):
            tweet["category"] = "comments"
            tweet["verification"] = "unverified"
        return result

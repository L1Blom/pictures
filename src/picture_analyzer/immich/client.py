"""Thin REST client for the Immich server API.

Only what the album-publishing workflow needs:
    ping, list libraries, trigger a scan, search assets by original path,
    create/get/update albums, add/remove assets from albums.

The client talks to the local Immich instance (config: ``immich.url``)
with an API key (config: ``immich.api_key``).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class ImmichError(Exception):
    """Raised when the Immich API returns an error or is unreachable."""


class ImmichClient:
    """Minimal Immich API client (requests-based, no external SDK)."""

    def __init__(self, url: str, api_key: str, timeout: int = 30) -> None:
        self.base_url = url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"x-api-key": api_key})

    # ── low-level ────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ImmichError(f"Cannot reach Immich at {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            raise ImmichError(
                f"Immich API {method} {path} failed: {resp.status_code} {resp.text[:300]}"
            )
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def _get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json: dict | None = None) -> Any:
        return self._request("POST", path, json=json)

    def _put(self, path: str, json: dict | None = None) -> Any:
        return self._request("PUT", path, json=json)

    # ── server ───────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Return True when the server responds to /api/server/ping."""
        try:
            self._get("/api/server/ping")
            return True
        except ImmichError:
            return False

    # ── libraries ────────────────────────────────────────────────────

    def list_libraries(self) -> list[dict]:
        """Return all libraries (id, name, importPaths, ...)."""
        return self._get("/api/libraries") or []

    def find_library_by_path(self, path: str) -> Optional[dict]:
        """Return the library whose importPaths match *path*.

        The library's import path is the CONTAINER path (e.g. /import/picks)
        while *path* may be the HOST path (e.g. .../NieuwVolume/picks) —
        they share no prefix. Match on the final path segment (the library
        directory name), which must be unique among libraries.
        """
        def _last(p: str) -> str:
            segments = [s for s in str(p).strip("/").split("/") if s]
            return segments[-1] if segments else ""

        want = _last(path)
        if not want:
            return None
        for lib in self.list_libraries():
            for imp in lib.get("importPaths", []):
                if _last(imp) == want:
                    return lib
        return None

    def scan_library(self, library_id: str) -> None:
        """Trigger an (async) scan of a library — watches for new/changed files."""
        self._post(f"/api/libraries/{library_id}/scan")

    # ── assets ───────────────────────────────────────────────────────

    def search_assets_by_paths(self, paths: list[str]) -> list[dict]:
        """Search assets by originalPath (metadata search).

        Returns the raw asset list (id, originalPath, ...). Immich matches
        paths case-sensitively; pass absolute paths as Immich sees them
        (container paths for Docker setups). The API takes ONE path per
        query, so this issues one request per path (cached server-side,
        fast enough for album-sized batches).
        """
        found: list[dict] = []
        for path in paths:
            try:
                results = self._post("/api/search/metadata", json={
                    "originalPath": path,
                    "size": 100,
                })
            except ImmichError:
                continue
            assets = ((results or {}).get("assets") or {}).get("items") or []
            found.extend(a for a in assets if a.get("originalPath") == path)
        return found

    def get_asset_by_path(self, path: str) -> Optional[dict]:
        """Return the single asset whose originalPath equals *path*, or None."""
        for asset in self.search_assets_by_paths([path]):
            if asset.get("originalPath") == path:
                return asset
        return None

    # ── albums ───────────────────────────────────────────────────────

    def list_albums(self) -> list[dict]:
        """Return all albums (id, albumName, assetCount, ...)."""
        return self._get("/api/albums") or []

    def get_album_by_name(self, name: str) -> Optional[dict]:
        """Return the first album with *name* (album names are not unique)."""
        for album in self.list_albums():
            if album.get("albumName") == name:
                return album
        return None

    def create_album(self, name: str, description: str = "", order: str = "asc") -> dict:
        """Create a new album and return it.

        ``order``: "asc" = oldest first (old→new), "desc" = newest first
        (Immich's default).
        """
        return self._post("/api/albums", json={
            "albumName": name,
            "description": description,
            "order": order,
        })

    def update_album(self, album_id: str, **fields) -> dict:
        """Update album fields (albumName, description, order, ...)."""
        return self._request("PATCH", f"/api/albums/{album_id}", json=fields)

    def add_assets(self, album_id: str, asset_ids: list[str]) -> int:
        """Add assets to an album; returns how many were actually added."""
        if not asset_ids:
            return 0
        resp = self._put(f"/api/albums/{album_id}/assets", json={"ids": asset_ids})
        # resp: list of {id, success, error} per asset
        return sum(1 for r in resp or [] if r.get("success"))

    def remove_assets(self, album_id: str, asset_ids: list[str]) -> int:
        """Remove assets from an album; returns how many were actually removed."""
        if not asset_ids:
            return 0
        resp = self._request("DELETE", f"/api/albums/{album_id}/assets", json={"ids": asset_ids})
        return sum(1 for r in resp or [] if r.get("success"))

    def get_album_assets(self, album_id: str) -> list[dict]:
        """Return the assets currently in an album.

        Immich v3.x no longer embeds assets in the album object — query
        them via the metadata search with ``albumIds``.
        """
        results = self._post("/api/search/metadata", json={
            "albumIds": [album_id],
            "size": 1000,
        })
        return ((results or {}).get("assets") or {}).get("items") or []

    def delete_album(self, album_id: str) -> None:
        """Delete an album (assets themselves are untouched)."""
        self._request("DELETE", f"/api/albums/{album_id}")

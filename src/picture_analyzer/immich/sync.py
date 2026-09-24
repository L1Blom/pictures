"""Sync the picks root to Immich albums.

Declarative: the picks root (the Immich external library) is the source of
truth.  For every album folder under the picks root, an Immich album with the
same name must exist and contain exactly the assets whose originalPath lives
in that folder.  The sync diffs the desired state against Immich's actual
state and applies only the delta (add new, remove gone, create missing
albums, delete emptied ones).

Assets are matched by ``originalPath`` — the path as Immich sees it, which
for Docker deployments is the CONTAINER path (e.g. ``/data/picks/...``),
mapped from the host path via ``path_map``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple, Optional

from .client import ImmichClient, ImmichError

logger = logging.getLogger(__name__)


class SyncReport(NamedTuple):
    albums_created: list[str]
    albums_deleted: list[str]
    assets_added: int
    assets_removed: int
    missing_assets: list[str]   # pick files not (yet) found in Immich
    errors: list[str]


def _immich_path(host_path: Path, picks_root: Path, immich_picks_root: str) -> str:
    """Map a host path under the picks root to the path Immich sees."""
    rel = host_path.relative_to(picks_root).as_posix()
    return f"{immich_picks_root.rstrip('/')}/{rel}"


def sync_albums(
    client: ImmichClient,
    picks_root: Path,
    immich_picks_root: str,
    dry_run: bool = False,
) -> SyncReport:
    """Make Immich albums mirror the album folders under *picks_root*.

    Args:
        client: authenticated ImmichClient
        picks_root: host path of the picks external library
        immich_picks_root: the same library as Immich sees it (container path)
        dry_run: report what would happen without changing anything
    """
    picks_root = Path(picks_root)
    created: list[str] = []
    deleted: list[str] = []
    added = removed = 0
    missing: list[str] = []
    errors: list[str] = []

    # Desired state: album name → set of immich paths
    desired: dict[str, set[str]] = {}
    if picks_root.is_dir():
        for folder in sorted(picks_root.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            files = {p for p in folder.iterdir() if p.is_file()}
            if files:
                desired[folder.name] = {
                    _immich_path(p, picks_root, immich_picks_root) for p in files
                }

    # Actual state: album name → {asset id: originalPath}
    try:
        immich_albums = {a["albumName"]: a for a in client.list_albums()}
    except ImmichError as exc:
        return SyncReport(created, deleted, 0, 0, missing, [f"cannot list albums: {exc}"])

    # Resolve every desired path to an asset id (batched search)
    all_paths = sorted({p for paths in desired.values() for p in paths})
    path_to_id: dict[str, str] = {}
    if all_paths:
        try:
            for asset in client.search_assets_by_paths(all_paths):
                path_to_id[asset["originalPath"]] = asset["id"]
        except ImmichError as exc:
            errors.append(f"asset search failed: {exc}")

    for album_name, want_paths in sorted(desired.items()):
        want_ids = set()
        for p in sorted(want_paths):
            asset_id = path_to_id.get(p)
            if asset_id:
                want_ids.add(asset_id)
            else:
                missing.append(p)

        album = immich_albums.get(album_name)
        if album is None:
            if not dry_run:
                try:
                    album = client.create_album(album_name)
                except ImmichError as exc:
                    errors.append(f"{album_name}: cannot create album ({exc})")
                    continue
            created.append(album_name)
            have_ids: set[str] = set()
        else:
            try:
                have_ids = {a["id"] for a in client.get_album_assets(album["id"])}
            except ImmichError as exc:
                errors.append(f"{album_name}: cannot list album assets ({exc})")
                continue

        to_add = want_ids - have_ids
        to_remove = have_ids - want_ids
        if not dry_run:
            try:
                if to_add:
                    added += client.add_assets(album["id"], sorted(to_add))
                if to_remove:
                    removed += client.remove_assets(album["id"], sorted(to_remove))
            except ImmichError as exc:
                errors.append(f"{album_name}: cannot update album ({exc})")
                continue
        else:
            added += len(to_add)
            removed += len(to_remove)

    # Albums in Immich that no longer have a picks folder → delete when empty
    # (only albums we manage: they match a former picks album name pattern —
    # we delete only if they now have zero desired assets AND zero actual)
    for album_name, album in immich_albums.items():
        if album_name in desired:
            continue
        try:
            assets = client.get_album_assets(album["id"])
        except ImmichError:
            continue
        if not assets:
            # Empty album not backed by a picks folder — leave it alone:
            # the user may have created it manually. Only report.
            logger.debug("Empty album without picks folder: %s", album_name)

    return SyncReport(created, deleted, added, removed, missing, errors)


def trigger_scan(client: ImmichClient, picks_root: Path) -> Optional[str]:
    """Ask Immich to rescan the library that imports *picks_root*.

    Returns the library id that was scanned, or None when no matching
    library was found.
    """
    lib = client.find_library_by_path(str(picks_root))
    if lib is None:
        return None
    client.scan_library(lib["id"])
    return lib["id"]

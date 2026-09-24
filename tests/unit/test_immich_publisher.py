"""Tests for the Immich picks publisher."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from picture_analyzer.immich.publisher import publish_folder, publish_all


@pytest.fixture
def setup(tmp_path: Path) -> dict:
    """Build a mini project: photos root, enhanced root, picks root."""
    photos = tmp_path / "photos"
    enhanced = tmp_path / "enhanced"
    picks = tmp_path / "picks"

    # Album folder with description.txt (Albumnaam routing)
    folder = photos / "1984 Goes"
    folder.mkdir(parents=True)
    (folder / "description.txt").write_text(
        "Albumnaam: 1984-06 Goes\nLocatie: Goes\nDatum: Juni 1984\n", encoding="utf-8"
    )

    # Output folder follows Albumnaam
    out = enhanced / "1984-06 Goes"
    out.mkdir(parents=True)

    # Two source images
    for stem in ("img1", "img2"):
        src = folder / f"{stem}.jpg"
        src.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

    # img1: picked enhanced variant; img2: no pick
    (out / "img1_analyzed.jpg").write_bytes(b"\xff\xd8\xff\xe0analyzed")
    (out / "img1_enhanced.jpg").write_bytes(b"\xff\xd8\xff\xe0enhanced")
    (out / "img2_analyzed.jpg").write_bytes(b"\xff\xd8\xff\xe0analyzed")
    (out / "img2_enhanced.jpg").write_bytes(b"\xff\xd8\xff\xe0enhanced")

    (out / "img1_analyzed.json").write_text(json.dumps({
        "preferred_variant": "enhanced",
        "preferred_path": str(out / "img1_enhanced.jpg"),
    }), encoding="utf-8")
    (out / "img2_analyzed.json").write_text(json.dumps({}), encoding="utf-8")

    return {"photos": photos, "enhanced": enhanced, "picks": picks,
            "folder": folder, "out": out}


class TestPublishFolder:

    def test_publishes_picked_variant_with_stable_name(self, setup):
        r = publish_folder(setup["folder"], setup["enhanced"], setup["picks"])
        assert len(r.published) == 1
        assert len(r.skipped) == 1  # img2 has no pick
        assert not r.errors

        # Published under the ALBUM name (Albumnaam routing), stem only
        pick = setup["picks"] / "1984-06 Goes" / "img1.jpg"
        assert pick.is_file()
        assert pick.read_bytes() == b"\xff\xd8\xff\xe0enhanced"

    def test_repick_replaces_same_path(self, setup):
        publish_folder(setup["folder"], setup["enhanced"], setup["picks"])

        # Re-pick: now the analyzed variant is preferred
        jf = setup["out"] / "img1_analyzed.json"
        data = json.loads(jf.read_text())
        data["preferred_variant"] = "analyzed"
        data["preferred_path"] = str(setup["out"] / "img1_analyzed.jpg")
        jf.write_text(json.dumps(data))

        r = publish_folder(setup["folder"], setup["enhanced"], setup["picks"])
        assert len(r.published) == 1
        pick = setup["picks"] / "1984-06 Goes" / "img1.jpg"
        assert pick.read_bytes() == b"\xff\xd8\xff\xe0analyzed"
        # Still exactly one file — no duplicate
        assert len(list((setup["picks"] / "1984-06 Goes").iterdir())) == 1

    def test_cleared_pick_removes_published_file(self, setup):
        publish_folder(setup["folder"], setup["enhanced"], setup["picks"])
        pick = setup["picks"] / "1984-06 Goes" / "img1.jpg"
        assert pick.is_file()

        # Clear the pick
        (setup["out"] / "img1_analyzed.json").write_text(json.dumps({}))
        r = publish_folder(setup["folder"], setup["enhanced"], setup["picks"])
        assert len(r.removed) == 1
        assert not pick.exists()

    def test_dry_run_writes_nothing(self, setup):
        r = publish_folder(setup["folder"], setup["enhanced"], setup["picks"], dry_run=True)
        assert len(r.published) == 1
        assert not setup["picks"].exists()

    def test_missing_preferred_file_is_skipped(self, setup):
        # Point the pick at a file that does not exist
        jf = setup["out"] / "img1_analyzed.json"
        data = json.loads(jf.read_text())
        data["preferred_path"] = str(setup["out"] / "img1_gone.jpg")
        jf.write_text(json.dumps(data))

        r = publish_folder(setup["folder"], setup["enhanced"], setup["picks"])
        assert len(r.published) == 0
        assert len(r.skipped) == 2

    def test_hardlink_not_copy(self, setup):
        """The pick must be a hardlink — same inode as the picked variant."""
        publish_folder(setup["folder"], setup["enhanced"], setup["picks"])
        pick = setup["picks"] / "1984-06 Goes" / "img1.jpg"
        source = setup["out"] / "img1_enhanced.jpg"
        assert pick.stat().st_ino == source.stat().st_ino


class TestPublishAll:

    def test_publish_all_walks_folders(self, setup):
        results = publish_all(setup["photos"], setup["enhanced"], setup["picks"])
        assert "1984 Goes" in results
        assert (setup["picks"] / "1984-06 Goes" / "img1.jpg").is_file()

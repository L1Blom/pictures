# Backup & Restore Guide

This document describes what is backed up where, and how to recover from
various failure scenarios.

## What is backed up, and where

| Data | Backup | Schedule | Location |
|---|---|---|---|
| Source photos (`~/fotos` → `NieuwVolume/media/Foto's`) | `backup-to-onedrive.sh` (rclone mirror) | daily 03:00 | OneDrive `fotos/` |
| Enhanced variants + analysis JSONs (`~/enhanced` → `NieuwVolume/enhanced`) | `backup-to-onedrive.sh` (rclone mirror) | daily 03:00 | OneDrive `enhanced/` |
| Immich database (albums, users, sharing links, edits) | Immich built-in DB backup | daily 02:00 | `~/projects/immich-app/library/backups/immich-db-backup-*.sql.gz` (14 dumps kept) |
| Immich uploads + thumbnails + encoded video | **NOT backed up** | — | `~/projects/immich-app/library/` |

Notes:

- `~/fotos` and `~/enhanced` are symlinks to `/home/leen/bigfoot/NieuwVolume/...`;
  the backup script uses `rclone sync -L` to follow them.
- The **picks** tree (`NieuwVolume/picks`) is NOT backed up directly — it is
  hardlinks into `enhanced/` plus a derived structure. It can be fully
  regenerated from the analysis JSONs (see below).
- The Immich DB dumps are plain `pg_dump` output, gzipped, one per day,
  named `immich-db-backup-YYYYMMDDT020000-vX.Y.Z-pgV.R.sql.gz`.
- The pictures project itself is on GitHub (`git clone` to restore).

## Scenario 1 — Immich database lost (albums gone, files intact)

Symptoms: albums/partners/sharing links missing after a DB crash or bad
upgrade, but all photos still show (external libraries rescan fine).

```bash
cd ~/projects/immich-app

# 1. Stop the server (keep postgres running)
docker compose stop immich-server

# 2. Pick the newest dump
DUMP=$(ls -t library/backups/immich-db-backup-*.sql.gz | head -1)
echo "restoring $DUMP"

# 3. Restore into a FRESH database (drop + recreate is safest)
docker compose exec -T postgres psql -U postgres -c "DROP DATABASE immich;"
docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE immich;"

# 4. Load the dump
gunzip -c "$DUMP" | docker compose exec -T postgres psql -U postgres -d immich

# 5. Restart
docker compose up -d immich-server
```

Albums, users, partner shares and public links come back exactly as they
were at 02:00 that night.

## Scenario 2 — Whole NieuwVolume disk lost

Symptoms: photos, enhanced variants, picks all gone. Immich library data
(`~/projects/immich-app/library`) may also be gone if it was on the same
volume — check `UPLOAD_LOCATION=./library` in `.env` for where that really
lives.

### Step 1 — restore the data from OneDrive

```bash
# Recreate the directory structure
mkdir -p /home/leen/bigfoot/NieuwVolume/media
mkdir -p /home/leen/bigfoot/NieuwVolume/enhanced

# Restore (rclone is resumable; a full restore takes days at ~1 MB/s)
rclone sync -L onedrive:fotos    /home/leen/bigfoot/NieuwVolume/media/Foto's
rclone sync -L onedrive:enhanced /home/leen/bigfoot/NieuwVolume/enhanced

# Recreate the symlinks the tooling expects
ln -sfn /home/leen/bigfoot/NieuwVolume/media/Foto's ~/fotos
ln -sfn /home/leen/bigfoot/NieuwVolume/enhanced      ~/enhanced
```

### Step 2 — restore the Immich database

Same as Scenario 1. If the DB dumps were on the lost volume too, they are
gone — but albums can be rebuilt from picks (Step 4).

### Step 3 — restore the pictures project

```bash
cd ~/projects
git clone https://github.com/L1Blom/pictures.git
cd pictures
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.yaml.example config.yaml   # then edit: enhanced_root, immich section
```

### Step 4 — regenerate the picks tree

The picks are derived data: every `*_analyzed.json` in `enhanced/` carries
`preferred_variant` + `preferred_path`. Rebuild with:

```bash
cd ~/projects/pictures
.venv/bin/python - <<'EOF'
from pathlib import Path
import sys; sys.path.insert(0, "src")
from picture_analyzer.immich.publisher import publish_all
results = publish_all(
    Path.home() / "fotos",
    Path("/home/leen/bigfoot/NieuwVolume/enhanced"),
    Path("/home/leen/bigfoot/NieuwVolume/picks"),
)
total = sum(len(r.published) for r in results.values())
print(f"republished {total} picks across {len(results)} folders")
EOF
```

### Step 5 — rebuild Immich albums

If the DB was restored: just let Immich scan the picks library
(Administration → Libraries → Picks → Scan). Albums reappear from the DB.

If the DB was NOT restored: recreate albums from the picks tree:

```bash
cd ~/projects/pictures
.venv/bin/python -m picture_analyzer sync-immich --scan
```

This creates one album per picks folder with the right assets.

## Scenario 3 — single photo accidentally deleted from enhanced/

The OneDrive mirror is a plain sync (no versioning): a deleted file is
removed from the remote on the next run. Restore BEFORE the next 03:00
backup run:

```bash
rclone copy onedrive:enhanced/<album>/<stem>_enhanced.jpg \
         /home/leen/bigfoot/NieuwVolume/enhanced/<album>/
```

If the nightly run already propagated the deletion, the file is gone from
OneDrive too — the original scan still exists in `fotos/` (and on OneDrive
`fotos/`), and can be re-processed through the pipeline.

## Scenario 4 — a pick was changed by mistake

Picks are just fields in the analysis JSON. Re-pick in the admin UI
(pictures.l1blom.com/admin), then:

```bash
.venv/bin/python -m picture_analyzer publish-immich "<folder>"
.venv/bin/python -m picture_analyzer sync-immich --scan
```

## Verification checklist (after any restore)

```bash
# 1. Picks tree matches the JSON picks
cd ~/projects/pictures
.venv/bin/python -m picture_analyzer publish-immich ~/fotos/<some-folder> --dry-run
# → "published: N" should equal the number of picked images in that folder

# 2. Immich albums match the picks folders
.venv/bin/python -m picture_analyzer sync-immich --dry-run
# → assets added/removed should be 0

# 3. Spot-check an album in the Immich web UI
```

## Known gaps

- **No versioning on OneDrive**: `rclone sync` mirrors deletions. A file
  deleted on disk disappears from the backup after the next nightly run.
- **Immich uploads library not backed up**: anything uploaded through the
  Immich app itself (phone uploads via the app, not the external
  libraries) lives in `~/projects/immich-app/library/upload` and is NOT
  covered. The icloudpd container's data (`/import/icloud`) is also not in
  the OneDrive script.
- **DB dumps live on the same volume as the Immich library data** —
  consider adding `library/backups/` to the OneDrive script (small, ~1 GB
  per dump) for off-site DB copies.

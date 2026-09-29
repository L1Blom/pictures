# Setup Guide

A complete, step-by-step walkthrough for getting this project running from a fresh `git clone` — CLI analysis, the admin web UI, and (optionally) Immich publishing and a persistent systemd service.

## 1. Prerequisites

- **Python 3.10+**
- **One vision-model provider:**
  - [Ollama](https://ollama.com) (recommended — local, free, works offline) — install it, then pull a vision model:
    ```bash
    ollama pull llama3.2-vision:11b     # or: ministral-3:3b, llava, ...
    ```
  - or an **OpenAI** API key (cloud, `gpt-4o-mini` by default)
- No other system packages are required — all EXIF/XMP metadata writing is pure Python (`piexif`/Pillow), no `exiftool`/`ffmpeg` needed.
- Optional: a running [Immich](https://immich.app/) instance, if you want to publish picked photos into albums.

## 2. Clone and install

```bash
git clone <repository-url>
cd pictures

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## 3. Configure

### 3a. `config.yaml` (non-secret settings)

```bash
cp config.yaml.example config.yaml
```

Edit it — at minimum, set your provider:

```yaml
analyzer_provider: "ollama"   # or "openai"

ollama:
  model: "llama3.2-vision:11b"
  host: "http://127.0.0.1:11434"

metadata:
  language: "en"              # en, nl, de, fr, es, ...
```

If you'll use the **admin web UI**, also tell it where your photos live and where analysis output should go (both default to `~/fotos` and `~/enhanced` if omitted — set these if that's not where you keep things):

```yaml
photos_root: "/path/to/your/photos"
output:
  enhanced_root: "/path/to/your/enhanced"
```

See [`config.yaml.example`](config.yaml.example) for every available option (geocoding, enhancement thresholds, slide-restoration profiles, report/gallery formatting, per-pipeline-step model overrides, etc.), or the [Configuration Reference](README.md#configuration-reference) in the README for a summary table.

### 3b. `.env` (secrets — never committed to git)

Only needed if you're using OpenAI and/or Immich:

```bash
# .env
OPENAI_APIKEY=sk-...              # only if analyzer_provider: openai
PA_IMMICH__API_KEY=your-key       # only if publishing to Immich (see step 6)
```

`.env` is already in `.gitignore` — keep secrets here, not in `config.yaml`.

## 4. First run — CLI

Verify everything works before touching the web UI:

```bash
# See your fully-resolved configuration
picture-analyzer config

# Analyze one image
picture-analyzer analyze path/to/photo.jpg

# Analyze a whole folder, with enhancement and slide restoration
picture-analyzer analyze path/to/folder --batch --enhance --restore-slide auto
```

By default this writes `<image>_analyzed.jpg` + `.json` next to your image (or into `output/` — see `--output`). Add a `description.txt` in the source folder first (see the README's [Context-Aware Analysis](README.md#context-aware-analysis-with-descriptiontxt) section) to give the AI ground-truth date/location and avoid hallucinated metadata.

## 5. Admin web UI

```bash
python api.py --port 7000
```

Open `http://127.0.0.1:7000/admin` in a browser. You should see your `photos_root` folders in the sidebar. From here you can:
- Click a folder to see its images
- Click an image to compare variants and pick the best one (★)
- Run "▶ Process folder" to analyze/enhance/restore an entire folder with live progress
- Edit `description.txt` per folder (📝 button)

If the folder list is empty or a folder shows "not found", double-check `photos_root`/`output.enhanced_root` in `config.yaml` (step 3a).

## 6. Immich integration setup (optional)

Skip this section if you don't use Immich.

1. In Immich, create a **new external library** pointing at a fresh, empty directory on the host — this becomes your "picks" library (keep it separate from any library that holds your full photo archive, so Immich only shows your picked bests, not every enhanced/restored variant).
2. In Immich, go to **Account Settings → API Keys** and create a key.
3. Add to `.env`:
   ```bash
   PA_IMMICH__API_KEY=the-key-you-just-created
   ```
4. Add to `config.yaml`:
   ```yaml
   immich:
     url: "http://127.0.0.1:2283"                 # your Immich server
     picks_root: "/path/to/the/picks/directory"    # host path, same as step 1
     immich_picks_root: "/import/picks"            # same path AS IMMICH SEES IT (container path if Immich runs in Docker)
   ```
5. Pick some images in the admin UI, then either:
   - Click **📤 Immich publish** then **🔄 Immich sync** for a folder in the admin UI, or
   - Run from the CLI:
     ```bash
     picture-analyzer publish-immich path/to/folder
     picture-analyzer sync-immich --scan
     ```
6. Check Immich — a new album (named after the folder's `Albumnaam`, oldest-first) should appear with your picks.

The **🔄 Immich sync** button in the admin UI is disabled until the selected folder has actually been published (publishing is per-folder; sync itself always reconciles the whole picks library in one pass).

## 7. Running as a systemd service (optional)

For a persistent, boot-surviving deployment of the admin UI:

```bash
sudo cp picture-analyzer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now picture-analyzer
```

Edit `/etc/systemd/system/picture-analyzer.service` first if your username, project path, or port differ from the defaults (`User=leen`, `/home/leen/projects/pictures`, port 7000). Check status/logs with:

```bash
systemctl status picture-analyzer
journalctl -u picture-analyzer -f
```

Restart after any code change or config edit:

```bash
sudo systemctl restart picture-analyzer
```

## Troubleshooting

- **`analyzer_provider: ollama` but analysis hangs/fails** — confirm Ollama is running (`ollama list`) and reachable at `ollama.host`, and that the model in `config.yaml` is actually pulled (`ollama pull <model>`).
- **Admin folder list is empty or slow** — check `photos_root`/`output.enhanced_root`; on slow/networked storage the folder list loads image counts progressively in the background (a `counting: true` flag while it catches up) rather than blocking the page.
- **Immich publish/sync errors "api_key not configured"** — the key must be in `.env` as `PA_IMMICH__API_KEY`, not in `config.yaml`.
- **GPS/location not appearing** — check `geo.confidence_threshold` in `config.yaml`; lower it if too few detections meet the bar, or add a `Locatie:`/`Location:` line to `description.txt` for guaranteed ground truth.
- **Re-running analysis moved my manually-reordered photos** — this is fixed: both single-image and full-folder reprocessing now reuse each image's own previously-set `date_taken` rather than resetting it. If you're on an older version, update.

## Next steps

- [README.md](README.md) — full feature overview, CLI reference, configuration reference
- [SLIDE_RESTORATION_GUIDE.md](SLIDE_RESTORATION_GUIDE.md) — restoration profile details
- [BACKUP_RESTORE.md](BACKUP_RESTORE.md) — backing up photos, enhanced output, and the Immich database

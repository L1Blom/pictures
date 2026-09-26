#!/usr/bin/env python3
"""
REST API for picture-analyzer

Mirrors the CLI commands as HTTP endpoints.

Long-running operations (analyze, process, batch) return a job_id immediately;
poll GET /api/jobs/<job_id> for status and results.

Fast operations (report, gallery, enhance, restore-slide) run synchronously.

Usage:
    python api.py                      # default: 0.0.0.0:5000
    python api.py --host 127.0.0.1
    python api.py --port 8080
    FLASK_DEBUG=1 python api.py
"""

import argparse
import json
import os
import queue
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

import click
from flask import Flask, jsonify, request, send_file

# New src-based CLI functions (support pipeline_mode, skip_existing)
sys.path.insert(0, str(Path(__file__).parent / "src"))
from picture_analyzer.cli.app import (
    _batch_analyze as _src_batch_analyze,
    _single_analyze as _src_single_analyze,
)

# Legacy CLI functions (enhance, restore-slide, report, gallery, process)
from cli_commands import (
    cmd_enhance,
    cmd_gallery,
    cmd_process,
    cmd_report,
    cmd_restore_slide,
)
from config import SUPPORTED_FORMATS

app = Flask(__name__)
static_dir = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Serial job queue — Ollama cannot handle concurrent inference.
# One worker thread drains the queue; jobs run one at a time.
# ---------------------------------------------------------------------------
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_job_queue: queue.Queue = queue.Queue()


def _worker() -> None:
    """Single background worker — processes jobs one at a time."""
    while True:
        job_id, fn, args_ns = _job_queue.get()
        with _jobs_lock:
            _jobs[job_id]["status"] = "running"
        try:
            result = fn(args_ns)
            with _jobs_lock:
                _jobs[job_id]["status"] = "completed"
                _jobs[job_id]["result"] = result if result is not None else 0
        except click.ClickException as exc:
            with _jobs_lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = exc.format_message()
        except Exception:
            with _jobs_lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = traceback.format_exc()
        finally:
            _job_queue.task_done()


# Start the single worker thread at import time.
_worker_thread = threading.Thread(target=_worker, daemon=True, name="job-worker")
_worker_thread.start()


def _start_job(fn, args_ns: SimpleNamespace) -> str:
    """Enqueue a job and return its id immediately."""
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "result": None, "error": None}
    _job_queue.put((job_id, fn, args_ns))
    return job_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _err(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


def _require_fields(body: dict, *fields: str):
    missing = [f for f in fields if f not in body or body[f] is None]
    return missing


# ---------------------------------------------------------------------------
# Job polling
# ---------------------------------------------------------------------------

@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    """
    Poll the status of a long-running job.

    Response:
        {
            "job_id": "...",
            "status": "queued" | "running" | "completed" | "failed",
            "result": <exit-code int or null>,
            "error": <traceback string or null>
        }
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return _err("Job not found", 404)
    return jsonify({"job_id": job_id, **job})


@app.get("/api/jobs")
def list_jobs():
    """Return all tracked jobs (id + status) and current queue depth."""
    with _jobs_lock:
        summary = [
            {"job_id": jid, "status": info["status"]}
            for jid, info in _jobs.items()
        ]
    return jsonify({"queue_depth": _job_queue.qsize(), "jobs": summary})


# ---------------------------------------------------------------------------
# POST /api/analyze  —  single image (async)
# ---------------------------------------------------------------------------

def _run_single_analyze(args: SimpleNamespace) -> None:
    """Adapter: call the new src _single_analyze with a SimpleNamespace."""
    _src_single_analyze(
        image_path=Path(args.image),
        output=args.output,
        do_enhance=args.enhance,
        restore_slide=args.restore_slide,
        no_json=args.no_json,
        provider=getattr(args, "provider", None),
        pipeline_mode=args.pipeline_mode,
    )


def _run_batch_analyze(args: SimpleNamespace) -> None:
    """Adapter: call the new src _batch_analyze with a SimpleNamespace."""
    _src_batch_analyze(
        directory=Path(args.directory),
        output=args.output,
        do_enhance=args.enhance,
        restore_slide=args.restore_slide,
        provider=getattr(args, "provider", None),
        pipeline_mode=args.pipeline_mode,
        skip_existing=args.skip_existing,
    )


@app.post("/api/analyze")
def analyze():
    """
    Analyze a single image.

    Request body (JSON):
        image          string  required  Absolute path to the image file
        output         string  optional  Output directory (default: config output dir)
        enhance        bool    optional  Also enhance the image (default: false)
        restore_slide  string  optional  Slide profile or "auto" (default: null)
        no_json        bool    optional  Skip saving JSON analysis (default: false)
        pipeline_mode  string  optional  "single" or "stepped" (default: config value)
        provider       string  optional  "openai" or "ollama" (default: config value)

    Response:
        {"job_id": "...", "status": "queued"}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "image")
    if missing:
        return _err(f"Missing required fields: {missing}")

    pipeline_mode = body.get("pipeline_mode")
    if pipeline_mode and pipeline_mode not in ("single", "stepped"):
        return _err("pipeline_mode must be 'single' or 'stepped'")

    args = SimpleNamespace(
        image=body["image"],
        output=body.get("output"),
        enhance=bool(body.get("enhance", False)),
        restore_slide=body.get("restore_slide"),
        no_json=bool(body.get("no_json", False)),
        pipeline_mode=pipeline_mode,
        provider=body.get("provider"),
    )

    if not Path(args.image).is_file():
        return _err(f"Image not found: {args.image}")

    job_id = _start_job(_run_single_analyze, args)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


# ---------------------------------------------------------------------------
# POST /api/analyze/batch  —  directory batch (async)
# ---------------------------------------------------------------------------

@app.post("/api/analyze/batch")
def analyze_batch():
    """
    Analyze all images in a directory.

    Request body (JSON):
        directory      string  required  Absolute path to directory containing images
        output         string  optional  Output directory (default: derived from description.txt or "output")
        enhance        bool    optional  Also enhance images (default: false)
        restore_slide  string  optional  Slide profile or "auto" (default: null)
        pipeline_mode  string  optional  "single" or "stepped" (default: config value)
        provider       string  optional  "openai" or "ollama" (default: config value)
        skip_existing  bool    optional  Skip images that already have a completed JSON (default: false)

    Response:
        {"job_id": "...", "status": "queued"}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "directory")
    if missing:
        return _err(f"Missing required fields: {missing}")

    pipeline_mode = body.get("pipeline_mode")
    if pipeline_mode and pipeline_mode not in ("single", "stepped"):
        return _err("pipeline_mode must be 'single' or 'stepped'")

    args = SimpleNamespace(
        directory=body["directory"],
        output=body.get("output"),
        enhance=bool(body.get("enhance", False)),
        restore_slide=body.get("restore_slide"),
        pipeline_mode=pipeline_mode,
        provider=body.get("provider"),
        skip_existing=bool(body.get("skip_existing", False)),
    )

    if not Path(args.directory).is_dir():
        return _err(f"Directory not found: {args.directory}")

    job_id = _start_job(_run_batch_analyze, args)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


# ---------------------------------------------------------------------------
# POST /api/process  —  analyze + enhance + optional restore (async)
# ---------------------------------------------------------------------------

@app.post("/api/process")
def process():
    """
    Analyze, enhance, and optionally restore a single image in one step.

    Request body (JSON):
        image         string  required  Absolute path to the image file
        output        string  optional  Output directory (default: "output")
        restore_slide string  optional  Slide profile or "auto" (default: null)

    Response:
        {"job_id": "...", "status": "queued"}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "image")
    if missing:
        return _err(f"Missing required fields: {missing}")

    # Default output: the album folder in the enhanced root, derived from the
    # image's directory description.txt (Albumnaam) — same as batch analyze.
    output = body.get("output")
    if not output:
        src = Path(body["image"])
        _, enhanced_root = _admin_roots()
        album = src.parent.name
        desc = src.parent / "description.txt"
        if desc.exists():
            import re
            m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
            if m and m.group(1).strip():
                album = m.group(1).strip()
        output = str(enhanced_root / album)

    args = SimpleNamespace(
        image=body["image"],
        output=output,
        restore_slide=body.get("restore_slide"),
    )

    if not Path(args.image).is_file():
        return _err(f"Image not found: {args.image}")

    job_id = _start_job(cmd_process, args)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


# ---------------------------------------------------------------------------
# POST /api/report  —  generate markdown report (sync, fast)
# ---------------------------------------------------------------------------

@app.post("/api/report")
def report():
    """
    Generate a markdown analysis report from an output directory.

    Request body (JSON):
        directory  string  required  Path to directory containing analyzed images/JSON
        output     string  optional  Output path for the .md file

    Response:
        {"status": "ok", "report_path": "..."}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "directory")
    if missing:
        return _err(f"Missing required fields: {missing}")

    args = SimpleNamespace(
        directory=body["directory"],
        output=body.get("output"),
    )

    if not Path(args.directory).is_dir():
        return _err(f"Directory not found: {args.directory}")

    rc = cmd_report(args)
    report_path = args.output or str(Path(args.directory) / "analysis_report.md")
    if rc != 0:
        return _err("Report generation failed", 500)
    return jsonify({"status": "ok", "report_path": report_path})


# ---------------------------------------------------------------------------
# POST /api/gallery  —  generate gallery report (sync, fast)
# ---------------------------------------------------------------------------

@app.post("/api/gallery")
def gallery():
    """
    Generate a gallery markdown report from an output directory.

    Request body (JSON):
        directory  string  required  Path to directory containing analyzed images
        output     string  optional  Output path for the gallery .md file

    Response:
        {"status": "ok", "report_path": "..."}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "directory")
    if missing:
        return _err(f"Missing required fields: {missing}")

    args = SimpleNamespace(
        directory=body["directory"],
        output=body.get("output"),
    )

    if not Path(args.directory).is_dir():
        return _err(f"Directory not found: {args.directory}")

    rc = cmd_gallery(args)
    report_path = args.output or str(Path(args.directory) / "gallery.md")
    if rc != 0:
        return _err("Gallery generation failed", 500)
    return jsonify({"status": "ok", "report_path": report_path})


# ---------------------------------------------------------------------------
# POST /api/enhance  —  enhance from analysis JSON (sync)
# ---------------------------------------------------------------------------

@app.post("/api/enhance")
def enhance():
    """
    Enhance an image using an existing analysis JSON file.

    Request body (JSON):
        image     string  required  Absolute path to the image file
        analysis  string  optional  Path to the JSON analysis file
                                    (auto-detected: next to the image, or in the
                                    output folder derived from description.txt)
        output    string  optional  Output path for enhanced image

    Response:
        {"status": "ok", "output": "..."}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "image")
    if missing:
        return _err(f"Missing required fields: {missing}")

    image = body["image"]
    analysis = body.get("analysis")

    # Auto-locate the analysis JSON if not provided: the pipeline stores it in
    # <enhanced_root>/<Albumnaam>/<stem>_analyzed.json, not next to the source.
    if not analysis:
        src = Path(image)
        candidates = []
        # 1. next to the source image (legacy layout)
        candidates.append(src.parent / f"{src.stem}_analyzed.json")
        # 2. output folder derived from description.txt Albumnaam
        _, enhanced_root = _admin_roots()
        album = src.parent.name
        desc = src.parent / "description.txt"
        if desc.exists():
            import re
            m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
            if m and m.group(1).strip():
                album = m.group(1).strip()
        candidates.append(enhanced_root / album / f"{src.stem}_analyzed.json")
        analysis = next((str(c) for c in candidates if c.is_file()), None)
        if not analysis:
            return _err(
                "Analysis file not found. Run 'analyze' first, or pass 'analysis' path. "
                f"Looked for: {', '.join(str(c) for c in candidates)}"
            )

    args = SimpleNamespace(
        image=image,
        analysis=analysis,
        output=body.get("output"),
    )

    if not Path(args.image).is_file():
        return _err(f"Image not found: {args.image}")

    # Default output: next to the analysis JSON in the output folder (keeps
    # enhanced images with their album), not next to the source image.
    if not args.output:
        args.output = str(Path(analysis).parent / f"{Path(args.image).stem}_enhanced.jpg")

    rc = cmd_enhance(args)
    if rc != 0:
        return _err("Enhancement failed", 500)

    output_path = args.output
    return jsonify({"status": "ok", "output": output_path})


# ---------------------------------------------------------------------------
# POST /api/restore-slide  —  restore old slide (sync)
# ---------------------------------------------------------------------------

@app.post("/api/restore-slide")
def restore_slide():
    """
    Restore a scanned old slide/dia positive.

    Request body (JSON):
        image        string  required  Absolute path to the scanned slide image
        profile      string  optional  faded|color_cast|red_cast|yellow_cast|
                                       aged|well_preserved|auto  (default: "auto")
        analysis     string  optional  Path to JSON analysis file (needed for auto)
        output       string  optional  Output path for restored image
        no_denoise   bool    optional  Skip noise reduction (default: false)
        no_despeckle bool    optional  Skip dust/speckle removal (default: false)

    Response:
        {"status": "ok", "output": "..."}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "image")
    if missing:
        return _err(f"Missing required fields: {missing}")

    valid_profiles = {"faded", "color_cast", "red_cast", "yellow_cast", "aged", "well_preserved", "auto"}
    profile = body.get("profile", "auto")
    if profile not in valid_profiles:
        return _err(f"Invalid profile '{profile}'. Valid values: {sorted(valid_profiles)}")

    args = SimpleNamespace(
        image=body["image"],
        profile=profile,
        analysis=body.get("analysis"),
        output=body.get("output"),
        no_denoise=bool(body.get("no_denoise", False)),
        no_despeckle=bool(body.get("no_despeckle", False)),
    )

    if not Path(args.image).is_file():
        return _err(f"Image not found: {args.image}")

    rc = cmd_restore_slide(args)
    if rc != 0:
        return _err("Slide restoration failed", 500)

    output_path = args.output or str(
        Path(args.image).parent / f"{Path(args.image).stem}_restored.jpg"
    )
    return jsonify({"status": "ok", "output": output_path})


# ---------------------------------------------------------------------------
# GET /api/formats  —  supported image formats (informational)
# ---------------------------------------------------------------------------

@app.get("/api/formats")
def formats():
    """Return the list of supported image formats."""
    return jsonify({"formats": sorted(SUPPORTED_FORMATS)})


# ---------------------------------------------------------------------------
# Admin page + processing-support endpoints
# ---------------------------------------------------------------------------

# Root that the admin page browses: source photos (~/fotos by default).
# Derived the same way the description editor does it.
def _admin_roots() -> tuple[Path, Path]:
    """Return (photos_root, enhanced_root) used by the admin page."""
    # enhanced root: prefer the configured output.enhanced_root (absolute),
    # fall back to ~/enhanced
    enhanced_root = None
    try:
        import yaml
        cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))
        enhanced_root = (cfg.get("output") or {}).get("enhanced_root")
    except Exception:
        pass
    if not enhanced_root or not Path(enhanced_root).is_dir():
        enhanced_root = Path.home() / "enhanced"
    enhanced_root = Path(enhanced_root)

    photos_root = Path.home() / "fotos"
    if not photos_root.is_dir():
        photos_root = enhanced_root.parent / "fotos"
    return photos_root, enhanced_root


@app.get("/admin")
def admin_page():
    """Serve the admin single-page app (never cached — always latest)."""
    resp = send_file(static_dir / "admin.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/admin/roots")
def admin_roots():
    """Return the photos and enhanced root directories the admin page uses."""
    photos_root, enhanced_root = _admin_roots()
    return jsonify({
        "photos_root": str(photos_root),
        "enhanced_root": str(enhanced_root),
    })


@app.get("/api/admin/folders")
def admin_folders():
    """List album folders in the photos root — progressive loading.

    Folder names come from a single bare `os.listdir()` (one readdir syscall,
    no per-entry stat — essentially free even over slow/network storage).
    Everything that needs a stat() or file read per folder (is_dir, image
    counts, description.txt, Albumnaam, pick counts) is expensive here — this
    volume's storage takes ~20ms PER STAT CALL, so 500+ synchronous stats
    made this endpoint take 10-180+ seconds. All of that is now done by
    background threads that fill in results folder by folder; this endpoint
    always returns immediately with whatever is known so far plus a
    `counting` flag while those scans are still running.
    """
    photos_root, _ = _admin_roots()
    if not photos_root.is_dir():
        return _err(f"Photos root not found: {photos_root}", 500)

    names_cache = getattr(admin_folders, "_names_cache", None)
    root_mtime = photos_root.stat().st_mtime
    if not (names_cache and names_cache[0] == root_mtime):
        names = sorted(n for n in os.listdir(photos_root) if not n.startswith("."))
        admin_folders._names_cache = (root_mtime, names)
    else:
        names = names_cache[1]

    _ensure_folder_count_thread(photos_root, root_mtime)
    picks_done = _ensure_picks_cache_thread()
    counts_done = getattr(_ensure_folder_count_thread, "_done_mtime", None) == root_mtime
    image_counts = getattr(_ensure_folder_count_thread, "_cache", {}) or {}
    picks = getattr(_ensure_picks_cache_thread, "_cache", {}) or {}

    folders = []
    for name in names:
        info = image_counts.get(name)
        n_images = info["images"] if info else None
        if n_images == 0:
            continue  # known-empty folder, hide it (unknown yet = keep visible)
        folders.append({
            "name": name,
            "path": str(photos_root / name),
            "images": n_images,
            "has_description": info["has_description"] if info else None,
            "picked": picks.get(info["album"] if info else name, 0),
        })
    return jsonify({"folders": folders, "counting": not (counts_done and picks_done)})


def _scan_folder_counts(photos_root: Path, root_mtime: float) -> None:
    """Background job: count images per folder, one folder at a time.

    Updates the shared cache after each folder so partial results are usable
    immediately rather than only once the whole 70k-file scan completes.
    """
    counts: dict[str, dict] = {}
    for sub in sorted(photos_root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        n_images = sum(
            1 for f in sub.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
        )
        counts[sub.name] = {
            "images": n_images,
            "has_description": (sub / "description.txt").exists(),
            "album": _album_name_for_folder(sub),
        }
        _ensure_folder_count_thread._cache = dict(counts)
    _ensure_folder_count_thread._done_mtime = root_mtime


def _ensure_folder_count_thread(photos_root: Path, root_mtime: float) -> None:
    """Kick off a folder image-count scan in the background if needed."""
    if getattr(_ensure_folder_count_thread, "_done_mtime", None) == root_mtime:
        return
    running = getattr(_ensure_folder_count_thread, "_thread", None)
    if running and running.is_alive():
        return
    t = threading.Thread(
        target=_scan_folder_counts, args=(photos_root, root_mtime),
        daemon=True, name="folder-count-scan",
    )
    _ensure_folder_count_thread._thread = t
    t.start()


def _album_name_for_folder(folder: Path) -> str:
    """Resolve a photos-root folder to its Albumnaam (or the folder name)."""
    desc = folder / "description.txt"
    if desc.exists():
        import re
        m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            return m.group(1).strip()
    return folder.name


def _refresh_picks_cache() -> None:
    """Background job: count preferred picks per album by scanning analysis JSONs.

    Runs in its own thread so it never blocks HTTP requests — this scan reads
    16k+ small files and can take minutes on the enhanced root's storage.
    """
    _, enhanced_root = _admin_roots()
    if not enhanced_root.is_dir():
        return
    counts: dict[str, int] = {}
    for out_dir in enhanced_root.iterdir():
        if not out_dir.is_dir():
            continue
        n_picked = 0
        for jf in out_dir.glob("*_analyzed.json"):
            try:
                # Substring check avoids a full json.loads() per file — the
                # field is only ever written when a pick is set (see
                # admin_set_preferred, which pop()s it when cleared).
                if b'"preferred_variant"' in jf.read_bytes():
                    n_picked += 1
            except OSError:
                continue
        counts[out_dir.name] = n_picked
        _ensure_picks_cache_thread._cache = dict(counts)
    _ensure_picks_cache_thread._done = True


def _ensure_picks_cache_thread() -> bool:
    """Kick off a picks-cache refresh in the background if one isn't already running.

    Returns True once at least one full scan has completed.
    """
    running = getattr(_ensure_picks_cache_thread, "_thread", None)
    if running and running.is_alive():
        return False
    if not getattr(_ensure_picks_cache_thread, "_done", False):
        t = threading.Thread(target=_refresh_picks_cache, daemon=True, name="picks-cache-refresh")
        _ensure_picks_cache_thread._thread = t
        t.start()
        return False
    return True


@app.get("/api/admin/dir")
def admin_dir():
    """List images in a photos-root folder, with variant badges from the output folder.

    Query params:
        dir  string  required  Folder name (or relative path) under the photos root
    """
    rel = request.args.get("dir")
    if not rel:
        return _err("Missing required query param: dir")
    photos_root, enhanced_root = _admin_roots()
    folder = (photos_root / rel).resolve()
    try:
        folder.relative_to(photos_root.resolve())
    except ValueError:
        return _err("Invalid folder path", 403)
    if not folder.is_dir():
        return _err(f"Folder not found: {rel}", 404)

    # Output folder: Albumnaam from description.txt, else folder name
    album = folder.name
    desc = folder / "description.txt"
    if desc.exists():
        import re
        m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            album = m.group(1).strip()
    out_dir = enhanced_root / album

    images = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in SUPPORTED_FORMATS:
            continue
        has_enhanced = (out_dir / f"{f.stem}_enhanced.jpg").is_file()
        restored_count = len(list(out_dir.glob(f"{glob_escape(f.stem)}_restored_*.jpg"))) if out_dir.is_dir() else 0
        # Latest generation timestamp across all output variants
        latest = None
        if out_dir.is_dir():
            for out_f in out_dir.glob(f"{glob_escape(f.stem)}_*.jpg"):
                try:
                    ts = out_f.stat().st_mtime
                    if latest is None or ts > latest:
                        latest = ts
                except OSError:
                    continue
        # Preferred variant (if marked in the analysis JSON)
        preferred = None
        preferred_path = None
        jf = out_dir / f"{f.stem}_analyzed.json"
        if jf.is_file():
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                preferred = data.get("preferred_variant")
                preferred_path = data.get("preferred_path")
            except (json.JSONDecodeError, OSError):
                pass
        # The grid thumbnail shows the PICKED variant when there is one
        # (the original is just the unprocessed scan); fall back to the
        # original when nothing is picked or the pick is missing on disk.
        thumb_src = str(f)
        if preferred_path and Path(preferred_path).is_file():
            thumb_src = preferred_path
        images.append({
            "name": f.name,
            "path": str(f),
            "thumb_src": thumb_src,
            "has_enhanced": has_enhanced,
            "restored_count": restored_count,
            "latest_generated": latest,  # unix timestamp or null
            "preferred_variant": preferred,
        })
    return jsonify({"folder": rel, "album": album, "output_dir": str(out_dir), "images": images})


@app.get("/api/admin/variants")
def admin_variants():
    """List all output variants for one source image.

    Query params:
        image  string  required  Absolute path to the SOURCE image (in photos root)

    Returns the analyzed copy, enhanced version, restored variants and the
    analysis JSON path — all discovered in the output folder derived from the
    image's directory description.txt (Albumnaam), falling back to the folder name.
    """
    image = request.args.get("image")
    if not image:
        return _err("Missing required query param: image")
    src = Path(image)
    if not src.is_file():
        return _err(f"Image not found: {image}")

    # Determine output folder: <enhanced_root>/<Albumnaam or folder name>
    _, enhanced_root = _admin_roots()
    album = src.parent.name
    desc = src.parent / "description.txt"
    if desc.exists():
        import re
        m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            album = m.group(1).strip()
    out_dir = enhanced_root / album
    stem = src.stem

    def _find(pattern: str) -> list[Path]:
        return sorted(out_dir.glob(pattern)) if out_dir.is_dir() else []

    analyzed = out_dir / f"{stem}_analyzed.jpg"
    enhanced = out_dir / f"{stem}_enhanced.jpg"
    analysis_json = out_dir / f"{stem}_analyzed.json"
    restored = [
        {
            "profile": p.name[len(stem) + len("_restored_"):-len(".jpg")],
            "path": str(p),
            "generated": p.stat().st_mtime,
        }
        for p in _find(f"{glob_escape(stem)}_restored_*.jpg")
    ]

    def _ts(p: Path):
        return p.stat().st_mtime if p.exists() else None

    # Current preferred variant (if any) — read from the analysis JSON
    preferred_variant = None
    if analysis_json.exists():
        try:
            data = json.loads(analysis_json.read_text(encoding="utf-8"))
            preferred_variant = data.get("preferred_variant")
        except (json.JSONDecodeError, OSError):
            pass

    return jsonify({
        "source": str(src),
        "output_dir": str(out_dir),
        "analyzed": str(analyzed) if analyzed.exists() else None,
        "analyzed_generated": _ts(analyzed),
        "enhanced": str(enhanced) if enhanced.exists() else None,
        "enhanced_generated": _ts(enhanced),
        "analysis_json": str(analysis_json) if analysis_json.exists() else None,
        "restored": restored,
        "preferred_variant": preferred_variant,
    })


@app.get("/api/admin/file")
def admin_file():
    """Serve any file under the photos or enhanced roots (for image viewing).

    Query params:
        path  string  required  Absolute path to the file
    """
    path = request.args.get("path")
    if not path:
        return _err("Missing required query param: path")
    full = Path(path).resolve()
    photos_root, enhanced_root = _admin_roots()
    allowed = False
    for root in (photos_root, enhanced_root):
        try:
            full.relative_to(root.resolve())
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        return _err("Path is outside the allowed roots", 403)
    if not full.is_file():
        return _err(f"File not found: {path}", 404)
    return send_file(full)


# ---------------------------------------------------------------------------
# Thumbnails — the grid used to load full-size originals (3.5MB each, 100+MB
# per folder) into 110px cells, which made folder clicks take 10-20 seconds.
# This endpoint serves a small cached thumbnail instead.
# ---------------------------------------------------------------------------

_THUMB_DIR = Path("/tmp/picture_analyzer_thumbs")
_THUMB_SIZE = 300  # pixels on the long side
_THUMB_CACHE_TTL = 60 * 60 * 24 * 7  # regenerate after a week (catches re-processed images)


def _thumbnail_response(path: str):
    """Serve a cached thumbnail for *path* (any image under the allowed roots)."""
    if not path:
        return _err("Missing required query param: path")
    full = Path(path).resolve()
    photos_root, enhanced_root = _admin_roots()
    allowed = False
    for root in (photos_root, enhanced_root):
        try:
            full.relative_to(root.resolve())
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        return _err("Path is outside the allowed roots", 403)
    if not full.is_file():
        return _err(f"File not found: {path}", 404)

    # Cache key: hash of the full path + mtime (regenerates when re-processed)
    import hashlib
    try:
        mtime = full.stat().st_mtime
    except OSError:
        mtime = 0
    key = hashlib.sha256(f"{full}:{mtime}".encode()).hexdigest()[:24]
    thumb = _THUMB_DIR / f"{key}.jpg"
    _THUMB_DIR.mkdir(parents=True, exist_ok=True)

    if not thumb.is_file() or (time.time() - thumb.stat().st_mtime) > _THUMB_CACHE_TTL:
        try:
            from PIL import Image
            with Image.open(full) as img:
                img = img.convert("RGB")
                img.thumbnail((_THUMB_SIZE, _THUMB_SIZE))
                img.save(thumb, "JPEG", quality=80)
        except Exception as e:
            # Fall back to the original file (better slow than broken)
            return send_file(full)

    resp = send_file(thumb, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.get("/api/admin/thumb")
def admin_thumb():
    """Serve a small cached thumbnail for grid display.

    Query params:
        path  string  required  Absolute path to the image
    """
    return _thumbnail_response(request.args.get("path"))


@app.get("/api/admin/analysis")
def admin_analysis():
    """Return the analysis JSON for a source image (parsed)."""
    image = request.args.get("image")
    if not image:
        return _err("Missing required query param: image")
    src = Path(image)
    if not src.is_file():
        return _err(f"Image not found: {image}")

    _, enhanced_root = _admin_roots()
    album = src.parent.name
    desc = src.parent / "description.txt"
    if desc.exists():
        import re
        m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            album = m.group(1).strip()
    jf = enhanced_root / album / f"{src.stem}_analyzed.json"
    if not jf.is_file():
        return _err(f"No analysis JSON found at {jf}", 404)
    return send_file(jf, mimetype="application/json")


@app.get("/api/admin/description")
def admin_get_description():
    """Read a folder's description.txt.

    Query params:
        dir  string  required  Folder name (or relative path) under the photos root
    """
    rel = request.args.get("dir")
    if not rel:
        return _err("Missing required query param: dir")
    photos_root, _ = _admin_roots()
    folder = (photos_root / rel).resolve()
    try:
        folder.relative_to(photos_root.resolve())
    except ValueError:
        return _err("Invalid folder path", 403)
    if not folder.is_dir():
        return _err(f"Folder not found: {rel}", 404)
    desc = folder / "description.txt"
    if desc.exists():
        return jsonify({"dir": rel, "exists": True, "description": desc.read_text(encoding="utf-8")})
    # New file: offer the standard template
    return jsonify({
        "dir": rel, "exists": False,
        "description": "Albumnaam: \nLocatie: \nDatum: \nPersonen: \nActiviteit: \nWeer: \nOpmerkingen: \nStemming: ",
    })


@app.post("/api/admin/description")
def admin_save_description():
    """Write a folder's description.txt.

    Request body (JSON):
        dir          string  required  Folder name under the photos root
        description  string  required  Full description.txt content
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "dir", "description")
    if missing:
        return _err(f"Missing required fields: {missing}")
    photos_root, _ = _admin_roots()
    folder = (photos_root / body["dir"]).resolve()
    try:
        folder.relative_to(photos_root.resolve())
    except ValueError:
        return _err("Invalid folder path", 403)
    if not folder.is_dir():
        return _err(f"Folder not found: {body['dir']}", 404)
    try:
        (folder / "description.txt").write_text(
            str(body["description"]).strip() + "\n", encoding="utf-8"
        )
    except OSError as e:
        return _err(f"Could not write description.txt: {e}", 500)
    return jsonify({"status": "ok"})


def glob_escape(s: str) -> str:
    """Escape glob special characters in a filename stem."""
    return s.replace("[", "[[]").replace("*", "[*]").replace("?", "[?]")


# ---------------------------------------------------------------------------
# Immich publishing — expose the CLI commands to the admin page
# ---------------------------------------------------------------------------

def _immich_cfg():
    """Load and validate the Immich config section."""
    try:
        import yaml
        cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"cannot read config.yaml: {e}")
    immich = (cfg or {}).get("immich") or {}
    if not immich.get("api_key"):
        raise ValueError("immich.api_key not configured in config.yaml")
    if not immich.get("picks_root"):
        raise ValueError("immich.picks_root not configured in config.yaml")
    return immich


@app.post("/api/admin/immich/publish")
def admin_immich_publish():
    """Publish the picks of one folder into the picks root (sync, fast).

    Request body (JSON):
        dir  string  required  Folder name (or relative path) under the photos root
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "dir")
    if missing:
        return _err(f"Missing required fields: {missing}")
    photos_root, _ = _admin_roots()
    folder = (photos_root / body["dir"]).resolve()
    try:
        folder.relative_to(photos_root.resolve())
    except ValueError:
        return _err("Invalid folder path", 403)
    if not folder.is_dir():
        return _err(f"Folder not found: {body['dir']}", 404)

    try:
        immich = _immich_cfg()
    except ValueError as e:
        return _err(str(e), 500)

    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from picture_analyzer.immich.publisher import publish_folder, _album_for_folder

    # enhanced root: same resolution as _admin_roots
    enhanced_root = None
    try:
        cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))
        enhanced_root = (cfg.get("output") or {}).get("enhanced_root")
    except Exception:
        pass
    if not enhanced_root or not Path(enhanced_root).is_dir():
        enhanced_root = Path.home() / "enhanced"

    result = publish_folder(folder, Path(enhanced_root), Path(immich["picks_root"]))
    return jsonify({
        "status": "ok",
        "album": _album_for_folder(folder),
        "published": len(result.published),
        "removed": len(result.removed),
        "skipped": len(result.skipped),
        "errors": result.errors,
    })


@app.post("/api/admin/immich/sync")
def admin_immich_sync():
    """Sync Immich albums to mirror the picks root (async job).

    Request body (JSON):
        scan  bool  optional  Trigger an Immich library scan first (default false)
    """
    body = request.get_json(silent=True) or {}
    try:
        immich = _immich_cfg()
    except ValueError as e:
        return _err(str(e), 500)

    args = SimpleNamespace(
        url=immich["url"],
        api_key=immich["api_key"],
        picks_root=immich["picks_root"],
        immich_picks_root=immich.get("immich_picks_root") or immich["picks_root"],
        scan=bool(body.get("scan", False)),
    )
    job_id = _start_job(_run_immich_sync, args)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


def _run_immich_sync(args: SimpleNamespace) -> None:
    """Job worker: scan library (optional) + sync albums."""
    import time as _time

    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from picture_analyzer.immich.client import ImmichClient, ImmichError
    from picture_analyzer.immich.sync import sync_albums, trigger_scan

    client = ImmichClient(args.url, args.api_key)
    if not client.ping():
        raise RuntimeError(f"Immich not reachable at {args.url}")

    if args.scan:
        lib_id = trigger_scan(client, Path(args.picks_root))
        if lib_id:
            _time.sleep(20)  # let Immich ingest new/changed files

    report = sync_albums(client, Path(args.picks_root), str(args.immich_picks_root))
    # Surface the result in the job's "result" field
    print(f"albums created: {len(report.albums_created)}; "
          f"assets added: {report.assets_added}; removed: {report.assets_removed}; "
          f"missing: {len(report.missing_assets)}; errors: {len(report.errors)}")
    for name in report.albums_created:
        print(f"  + album: {name}")
    for p in report.missing_assets[:10]:
        print(f"  ⚠ missing in Immich: {p}")
    for e in report.errors:
        print(f"  ✗ {e}")


# ---------------------------------------------------------------------------
# Preferred variant — Immich album preparation
# ---------------------------------------------------------------------------

def _resolve_album_json(src: Path) -> Path:
    """Return the analysis JSON path for a source image (Albumnaam routing)."""
    _, enhanced_root = _admin_roots()
    album = src.parent.name
    desc = src.parent / "description.txt"
    if desc.exists():
        import re
        m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            album = m.group(1).strip()
    return enhanced_root / album / f"{src.stem}_analyzed.json"


@app.post("/api/admin/preferred")
def admin_set_preferred():
    """Mark the preferred variant for a source image (stored in its analysis JSON).

    Request body (JSON):
        image     string  required  Absolute path to the SOURCE image (in photos root)
        variant   string  optional  Variant label: "original", "analyzed",
                                    "enhanced", "restored:<profile>".
                                    Null/omitted clears the preference.

    The label is stored in the JSON as ``preferred_variant``; the absolute
    path of the chosen file is stored as ``preferred_path``.
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "image")
    if missing:
        return _err(f"Missing required fields: {missing}")
    src = Path(body["image"])
    if not src.is_file():
        return _err(f"Image not found: {body['image']}", 404)

    jf = _resolve_album_json(src)
    if not jf.is_file():
        return _err(f"No analysis JSON found at {jf} — process the image first", 404)

    variant = body.get("variant")
    if variant is not None and not isinstance(variant, str):
        return _err("variant must be a string or null")

    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return _err(f"Could not read analysis JSON: {e}", 500)

    if variant:
        # Resolve the label to an actual file path (validates it exists)
        v = _variant_paths(src)
        path = v.get(variant)
        if not path:
            return _err(f"Unknown or missing variant '{variant}' for this image", 400)
        data["preferred_variant"] = variant
        data["preferred_path"] = str(path)
    else:
        data.pop("preferred_variant", None)
        data.pop("preferred_path", None)

    try:
        jf.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as e:
        return _err(f"Could not write analysis JSON: {e}", 500)
    return jsonify({"status": "ok", "preferred_variant": variant})


def _variant_paths(src: Path) -> dict[str, str]:
    """Map variant labels to file paths for a source image (Albumnaam routing).

    Note: the ORIGINAL source file is deliberately not offered — it carries
    no EXIF data (no date, GPS, or description), so it is not a valid
    candidate for the Immich album. Only processed variants are pickable.
    """
    _, enhanced_root = _admin_roots()
    album = src.parent.name
    desc = src.parent / "description.txt"
    if desc.exists():
        import re
        m = re.search(r"(?im)^albumnaam\s*:\s*(.+)$", desc.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            album = m.group(1).strip()
    out_dir = enhanced_root / album
    stem = src.stem
    paths: dict[str, str] = {
        "analyzed": str(out_dir / f"{stem}_analyzed.jpg"),
        "enhanced": str(out_dir / f"{stem}_enhanced.jpg"),
    }
    if out_dir.is_dir():
        for p in out_dir.glob(f"{glob_escape(stem)}_restored_*.jpg"):
            profile = p.name[len(stem) + len("_restored_"):-len(".jpg")]
            paths[f"restored:{profile}"] = str(p)
    return {k: v for k, v in paths.items() if Path(v).is_file()}


# ---------------------------------------------------------------------------
# Description editor UI (mounted at /) — replaces the standalone
# `picture-analyzer describe` service that used to run on port 7000.
# ---------------------------------------------------------------------------

def _create_editor_app() -> "Flask":
    """Build the description editor app pointed at the admin photos root."""
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from picture_analyzer.web.editor_app import create_app as _editor_create_app

    photos_root, _ = _admin_roots()
    return _editor_create_app(photos_dir=str(photos_root))


# Mount the editor's routes (/, /api/directories, /api/directory/...,
# /api/thumbnail*, /api/image*, /api/exif-enhanced) under this app.
# WSGI middleware dispatches: editor paths go to the editor app, the rest
# (our /api/* and /admin) to the main app.
class _EditorMount:
    """WSGI middleware routing editor paths to the editor Flask app."""

    # Paths owned by the editor app (its index page + its API namespace)
    _EDITOR_PREFIXES = (
        "/api/directories",
        "/api/directory/",
        "/api/thumbnail/",
        "/api/thumbnail-enhanced/",
        "/api/image/",
        "/api/image-enhanced/",
        "/api/exif-enhanced/",
    )

    def __init__(self, main_app: Flask, editor_app: Flask):
        # Capture the ORIGINAL wsgi callable — assigning app.wsgi_app below
        # would otherwise make self.main_app(environ) re-enter this mount.
        self.main_app = main_app.wsgi_app
        self.editor_app = editor_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == "/" or any(path.startswith(p) for p in self._EDITOR_PREFIXES):
            return self.editor_app(environ, start_response)
        return self.main_app(environ, start_response)


_editor_flask = _create_editor_app()
app.wsgi_app = _EditorMount(app, _editor_flask)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="picture-analyzer REST API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    # threaded=True: the dev server is single-threaded by default — one slow
    # request (folders rescan, thumbnail batch) would block the whole UI.
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)

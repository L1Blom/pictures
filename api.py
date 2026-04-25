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
import queue
import sys
import threading
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

import click
from flask import Flask, jsonify, request

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

    args = SimpleNamespace(
        image=body["image"],
        output=body.get("output"),
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
                                    (auto-detected from image location if omitted)
        output    string  optional  Output path for enhanced image

    Response:
        {"status": "ok", "output": "..."}
    """
    body = request.get_json(silent=True) or {}
    missing = _require_fields(body, "image")
    if missing:
        return _err(f"Missing required fields: {missing}")

    args = SimpleNamespace(
        image=body["image"],
        analysis=body.get("analysis"),
        output=body.get("output"),
    )

    if not Path(args.image).is_file():
        return _err(f"Image not found: {args.image}")

    rc = cmd_enhance(args)
    if rc != 0:
        return _err("Enhancement failed", 500)

    output_path = args.output or str(
        Path(args.image).parent / f"{Path(args.image).stem}_enhanced.jpg"
    )
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="picture-analyzer REST API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=args.debug)

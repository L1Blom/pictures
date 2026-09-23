"""Flask description editor web application.

Provides a lightweight REST API (+ single-page HTML) for editing
``description.txt`` files inside photo directories, so analysts can
annotate albums before running the full AI pipeline.

No hardcoded values — all configuration comes from ``config.Settings``
or from constructor arguments.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file

from ..config.defaults import (
    DEFAULT_DESCRIPTION_TEMPLATE,
    DEFAULT_WEB_THUMBNAIL_FORMAT,
    DEFAULT_WEB_THUMBNAIL_SIZE,
)

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic",
})

_DEFAULT_TEMPLATE = """\
Albumnaam: 
Locatie: 
Datum: 
Personen: 
Activiteit: 
Weer: 
Opmerkingen: 
Stemming: 
"""


# ── EXIF display helpers ──────────────────────────────────────────────────────

_SKIP_EXIF_TAGS = frozenset({
    "MakerNote", "PrintImageMatching", "FlashPixVersion", "ExifVersion",
    "ComponentsConfiguration", "SceneType", "CFAPattern", "InteroperabilityIndex",
    "InteroperabilityVersion", "SubjectArea", "Padding", "OffsetSchema",
    # IFD sub-block pointers — numeric offsets, not human-readable
    "ExifOffset", "GPSInfo", "InteropOffset",
})

_EXIF_PRIORITY = [
    "DateTimeOriginal", "DateTime", "Make", "Model",
    "ExposureTime", "FNumber", "ISOSpeedRatings", "FocalLength", "FocalLengthIn35mmFilm",
    "Flash", "WhiteBalance", "ExposureMode", "MeteringMode",
    "Software", "ImageDescription", "Artist",
    "PixelXDimension", "PixelYDimension", "Orientation", "GPS",
]


def _format_gps(lat_dms: tuple, lat_ref: str, lon_dms: tuple, lon_ref: str) -> str:
    """Convert DMS tuples to a decimal-degree string."""
    def dms_to_dd(dms: tuple) -> float:
        d, m, s = (float(v) for v in dms)
        return d + m / 60.0 + s / 3600.0

    lat = dms_to_dd(lat_dms)
    lon = dms_to_dd(lon_dms)
    if str(lat_ref).upper() == "S":
        lat = -lat
    if str(lon_ref).upper() == "W":
        lon = -lon
    return f"{lat:.6f}\u00b0, {lon:.6f}\u00b0"


def _format_exif_value(tag: str, value: object) -> str:
    """Convert a raw EXIF value to a human-readable string."""
    try:
        if tag == "ExposureTime":
            fval = float(value)  # type: ignore[arg-type]
            return f"1/{round(1 / fval)}" if fval < 1 else f"{fval:.1f}s"
        if tag == "FNumber":
            return f"f/{float(value):.1f}"  # type: ignore[arg-type]
        if tag in ("FocalLength", "FocalLengthIn35mmFilm"):
            return f"{float(value):.0f} mm"  # type: ignore[arg-type]
        if tag == "ISOSpeedRatings":
            return f"ISO {value}"
        if tag == "Flash":
            return "Fired" if (isinstance(value, int) and value & 0x1) else "Did not fire"
        if tag == "WhiteBalance":
            return {0: "Auto", 1: "Manual"}.get(int(value), str(value))  # type: ignore[arg-type]
        if tag == "ExposureMode":
            return {0: "Auto", 1: "Manual", 2: "Auto-bracket"}.get(  # type: ignore[arg-type]
                int(value), str(value))
        if tag == "MeteringMode":
            return {1: "Average", 2: "Centre-weighted", 3: "Spot", 5: "Pattern"}.get(
                int(value), str(value))  # type: ignore[arg-type]
        if tag == "Orientation":
            return {1: "Normal", 3: "180\u00b0", 6: "CW 90\u00b0", 8: "CCW 90\u00b0"}.get(
                int(value), str(value))  # type: ignore[arg-type]
    except Exception:
        pass
    if isinstance(value, bytes):
        return "<binary>"
    if isinstance(value, (list, tuple)):
        return " / ".join(str(v) for v in value)
    return str(value)


class DescriptionEditor:
    """Back-end logic for listing directories and managing ``description.txt`` files.

    This class contains no Flask-specific code so it can be tested without
    an application context.

    Args:
        photos_dir:           Root directory containing photo sub-directories.
        description_template: Default text written to a new ``description.txt``.
        thumbnail_size:       Thumbnail width in pixels.
        thumbnail_format:     PIL format string: ``"JPEG"``, ``"PNG"``, or ``"WEBP"``.
    """

    def __init__(
        self,
        photos_dir: Path,
        description_template: str = DEFAULT_DESCRIPTION_TEMPLATE or _DEFAULT_TEMPLATE,
        thumbnail_size: int = DEFAULT_WEB_THUMBNAIL_SIZE,
        thumbnail_format: str = DEFAULT_WEB_THUMBNAIL_FORMAT,
    ) -> None:
        self.photos_dir = Path(photos_dir).resolve()
        self.enhanced_base_dir = (Path(photos_dir).parent / "enhanced").resolve()
        self.description_template = description_template or _DEFAULT_TEMPLATE
        self.thumbnail_size = thumbnail_size
        self.thumbnail_format = thumbnail_format

    # ── Directory listing ────────────────────────────────────────────────────

    def get_directories(self) -> list[dict[str, Any]]:
        """Return metadata for every photo sub-directory in ``photos_dir``."""
        result: list[dict[str, Any]] = []
        if not self.photos_dir.is_dir():
            return result

        for sub in sorted(self.photos_dir.iterdir()):
            if not sub.is_dir():
                continue

            images = self._list_images(sub)
            desc_file = sub / "description.txt"
            description = (
                desc_file.read_text(encoding="utf-8").strip() if desc_file.exists() else ""
            )

            result.append({
                "name": sub.name,
                "path": sub.relative_to(self.photos_dir).as_posix(),
                "image_count": len(images),
                "has_description": desc_file.exists(),
                "description_preview": (
                    description[:100] + "\u2026" if len(description) > 100 else description
                ),
            })

        return result

    # ── Directory details ────────────────────────────────────────────────────

    def get_directory_details(self, dir_path: str) -> dict[str, Any]:
        """Return detailed information for a single directory.

        Raises:
            ValueError: If the directory does not exist.
        """
        full_path = self._resolve_path(dir_path)

        images = self._list_images(full_path)
        desc_file = full_path / "description.txt"
        description = (
            desc_file.read_text(encoding="utf-8").strip()
            if desc_file.exists()
            else self.description_template
        )

        album_name = self._parse_album_name(description)
        enhanced_images = self._list_enhanced_images(album_name)

        return {
            "directory": dir_path,
            "description": description,
            "album_name": album_name,
            "images": [
                {"name": img.name, "path": img.relative_to(self.photos_dir).as_posix()}
                for img in images
            ],
            "total_images": len(images),
            "enhanced_images": enhanced_images,
        }

    # ── Save description ─────────────────────────────────────────────────────

    def save_description(self, dir_path: str, description: str) -> bool:
        """Write ``description.txt`` for *dir_path*.

        Raises:
            ValueError: If *dir_path* is invalid or does not exist.

        Returns:
            ``True`` on success, ``False`` on write error.
        """
        full_path = self._resolve_path(dir_path)  # may raise ValueError
        try:
            (full_path / "description.txt").write_text(
                description.strip(), encoding="utf-8"
            )
            return True
        except Exception:
            logger.exception("Failed to write description.txt for %s", dir_path)
            return False

    # ── Thumbnail ────────────────────────────────────────────────────────────

    def get_thumbnail(self, image_path: str, size: int | None = None) -> bytes:
        """Return thumbnail bytes for the image at *image_path*.

        Args:
            image_path: Path relative to ``photos_dir``.
            size:        Override thumbnail width.  Falls back to ``self.thumbnail_size``.

        Raises:
            ValueError: If the image file does not exist.
        """
        full_path = self.photos_dir / image_path
        if not full_path.exists():
            raise ValueError(f"Image not found: {image_path}")
        return self._generate_thumbnail(full_path, size)

    def _generate_thumbnail(self, full_path: Path, size: int | None = None) -> bytes:
        """Generate thumbnail bytes for a resolved *full_path*."""
        from PIL import Image

        thumb_size = size if size is not None else self.thumbnail_size
        with Image.open(full_path) as img:
            img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            needs_png = img.mode == "RGBA" and self.thumbnail_format == "JPEG"
            save_fmt = "PNG" if needs_png else self.thumbnail_format
            if img.mode in ("RGBA", "P") and save_fmt == "JPEG":
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1])
                img = background
            img.save(buf, save_fmt)
            return buf.getvalue()

    # ── Enhanced images ───────────────────────────────────────────────────────

    def get_enhanced_thumbnail(self, image_path: str, size: int | None = None) -> bytes:
        """Return thumbnail bytes for an image inside the enhanced base directory.

        Args:
            image_path: Path relative to ``enhanced_base_dir``.
            size:        Override thumbnail width.

        Raises:
            ValueError: If the image file does not exist or path escapes the dir.
        """
        full_path = (self.enhanced_base_dir / image_path).resolve()
        try:
            full_path.relative_to(self.enhanced_base_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Invalid path: {image_path}") from exc
        if not full_path.is_file():
            raise ValueError(f"Image not found: {image_path}")
        # Re-use the same thumbnail logic via a temporary editor instance
        return self._generate_thumbnail(full_path, size)

    def _list_enhanced_images(self, album_name: str | None) -> list[dict[str, str]]:
        """Return image list from the enhanced sub-directory for *album_name*."""
        if not album_name:
            return []
        enhanced_dir = self.enhanced_base_dir / album_name
        if not enhanced_dir.is_dir():
            return []
        return [
            {"name": img.name, "path": img.relative_to(self.enhanced_base_dir).as_posix()}
            for img in self._list_images(enhanced_dir)
        ]

    def get_exif_data(self, image_path: str) -> dict[str, str]:
        """Return display-ready EXIF fields for an enhanced image.

        Args:
            image_path: Path relative to ``enhanced_base_dir``.

        Raises:
            ValueError: If the path is invalid or the file is not found.
        """
        full_path = (self.enhanced_base_dir / image_path).resolve()
        try:
            full_path.relative_to(self.enhanced_base_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Invalid path: {image_path}") from exc
        if not full_path.is_file():
            raise ValueError(f"Image not found: {image_path}")
        return self._read_exif(full_path)

    @staticmethod
    def _read_exif(full_path: Path) -> dict[str, str]:
        """Read EXIF tags from *full_path* and return a display-ready ordered dict."""
        from PIL import Image
        from PIL.ExifTags import TAGS

        result: dict[str, str] = {}
        try:
            with Image.open(full_path) as img:
                exif = img.getexif()
                if not exif:
                    return result

                def _add(tag_id: int, value: object) -> None:
                    tag = TAGS.get(tag_id, str(tag_id))
                    if tag in _SKIP_EXIF_TAGS or isinstance(value, bytes):
                        return
                    formatted = _format_exif_value(tag, value)
                    if formatted and formatted != "<binary>":
                        result[tag] = formatted

                for tag_id, value in exif.items():
                    _add(tag_id, value)
                for tag_id, value in exif.get_ifd(0x8769).items():  # Exif sub-IFD
                    _add(tag_id, value)

                gps = exif.get_ifd(0x8825)
                if gps:
                    try:
                        lat_dms = gps.get(2)
                        lat_ref = gps.get(1, "N")
                        lon_dms = gps.get(4)
                        lon_ref = gps.get(3, "E")
                        if lat_dms and lon_dms:
                            result["GPS"] = _format_gps(lat_dms, lat_ref, lon_dms, lon_ref)
                    except Exception:
                        pass
        except Exception:
            logger.debug("Could not read EXIF for %s", full_path)

        # Re-order: priority fields first, then the rest
        ordered: dict[str, str] = {}
        for key in _EXIF_PRIORITY:
            if key in result:
                ordered[key] = result[key]
        for key, val in result.items():
            if key not in ordered:
                ordered[key] = val
        return ordered

    @staticmethod
    def _parse_album_name(description: str) -> str | None:
        """Extract album name from the first matching key in *description*.

        Recognises both ``Albumnaam:`` (Dutch) and ``Album name:`` (English),
        case-insensitive.
        """
        for line in description.splitlines():
            lower = line.lower()
            for key in ("albumnaam:", "album name:"):
                if lower.startswith(key):
                    value = line[len(key):].strip()
                    return value if value else None
        return None

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _resolve_path(self, dir_path: str) -> Path:
        """Resolve and validate *dir_path* relative to ``photos_dir``."""
        # Prevent path traversal: resolve and ensure still inside photos_dir
        full = (self.photos_dir / dir_path).resolve()
        try:
            full.relative_to(self.photos_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Invalid path: {dir_path}") from exc
        if not full.is_dir():
            raise ValueError(f"Directory not found: {dir_path}")
        return full

    @staticmethod
    def _list_images(directory: Path) -> list[Path]:
        return sorted(
            p for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
        )


# ── Flask app factory ─────────────────────────────────────────────────────────


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Picture Analyzer — Description Editor</title>
<style>
  html { height: 100%; }
  body { font-family: system-ui, sans-serif; margin: 0; padding: 0; background: #f8f9fa;
         display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  h1 { color: #333; margin: .75rem 2rem .5rem; flex-shrink: 0; }
  #app { display: flex; gap: 1.5rem; flex: 1; overflow: hidden; padding: 0 2rem 1rem; }
  #sidebar { width: 280px; flex-shrink: 0; display: flex; flex-direction: column;
             overflow: hidden; }
  #sidebar h3 { margin: 0 0 .5rem; flex-shrink: 0; }
  #dir-list { overflow-y: auto; flex: 1; }
  #main { flex: 1; min-width: 0; overflow-y: auto; }
  .dir-item { padding: .5rem .75rem; cursor: pointer; border-radius: 6px; margin-bottom: .25rem;
               background: #fff; border: 1px solid #ddd; }
  .dir-item:hover, .dir-item.active { background: #0d6efd; color: #fff; }
  .dir-item .meta { font-size: .75rem; opacity: .7; }
  textarea { width: 100%; height: 220px; font-family: monospace; font-size: .875rem;
             border: 1px solid #ccc; border-radius: 6px; padding: .5rem; box-sizing: border-box; }
  .btn { padding: .4rem 1rem; border-radius: 5px; border: none; cursor: pointer; font-size: .9rem; }
  .btn-primary { background: #0d6efd; color: #fff; }
  .btn-primary:hover { background: #0b5ed7; }
  #status { margin-top: .5rem; font-size: .85rem; color: green; min-height: 1.2em; }
  #status.error { color: red; }
  .thumb-section { margin-top: 1rem; }
  .thumb-section { margin-top: 1rem; }
  .thumb-header { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
                  font-size: .9rem; font-weight: 600; color: #555;
                  padding-bottom: .3rem; border-bottom: 1px solid #ddd; margin-bottom: .4rem; }
  .thumb-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
               margin-bottom: .4rem; align-items: start; }
  .thumb-cell { display: flex; flex-wrap: wrap; gap: .3rem; align-content: flex-start; }
  .thumb-cell img { width: 120px; height: 90px; object-fit: cover;
                    border-radius: 4px; border: 1px solid #ccc; cursor: zoom-in; }
  /* Modal */
  #modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.82);
           z-index: 1000; align-items: center; justify-content: center; }
  #modal.open { display: flex; }
  #modal-inner { display: flex; flex-direction: column; align-items: center; gap: .6rem; }
  #modal img { max-width: 90vw; max-height: 85vh; object-fit: contain;
               border-radius: 6px; box-shadow: 0 4px 32px #000; cursor: zoom-out; }
  .modal-nav { position: absolute; top: 50%; transform: translateY(-50%);
               background: rgba(255,255,255,.15); border: none; color: #fff;
               font-size: 2.5rem; line-height: 1; padding: .1rem .5rem; cursor: pointer;
               border-radius: 6px; user-select: none; z-index: 1; }
  .modal-nav:hover { background: rgba(255,255,255,.3); }
  #modal-prev { left: 1rem; }
  #modal-next { right: 1rem; }
  #modal-caption { color: #fff; font-size: .9rem; background: rgba(0,0,0,.55);
                   padding: .2rem .7rem; border-radius: 4px; max-width: 90vw;
                   word-break: break-all; text-align: center; }
  #modal-counter { color: #aaa; font-size: .8rem; }
  /* EXIF hover popup */
  #exif-popup { display: none; position: fixed; z-index: 2000;
                background: rgba(16,16,26,.96); color: #e0e0e0;
                border-radius: 8px; padding: .55rem .85rem;
                font-size: .74rem; font-family: monospace;
                max-width: 340px; max-height: 60vh; overflow-y: auto;
                box-shadow: 0 4px 28px rgba(0,0,0,.65);
                border: 1px solid rgba(255,255,255,.13); }
  #exif-popup .exif-title { color: #7ec8e3; font-family: system-ui, sans-serif;
                             font-size: .77rem; font-weight: 600;
                             margin-bottom: .5rem; word-break: break-all; }
  #exif-popup .exif-grid { display: grid;
                            grid-template-columns: 1fr;
                            gap: .25rem 0; }
  #exif-popup .exif-field { display: flex; flex-direction: column; }
  #exif-popup .exif-label { color: #888; font-size: .67rem;
                             text-transform: uppercase; letter-spacing: .03em;
                             margin-bottom: .06rem; white-space: nowrap;
                             overflow: hidden; text-overflow: ellipsis; }
  #exif-popup .exif-value { color: #fff; word-break: break-word; }
</style>
</head>
<body>
<h1>📷 Description Editor &nbsp;<a href="/admin" style="font-size:.8rem;color:#0d6efd;text-decoration:none">admin →</a></h1>
<div id="exif-popup"></div>
<div id="modal" onclick="closeModal()">
  <button id="modal-prev" class="modal-nav"
    onclick="event.stopPropagation();navigate(-1)">&#8249;</button>
  <div id="modal-inner" onclick="event.stopPropagation()">
    <img id="modal-img" src="" alt="" onclick="closeModal()" />
    <div id="modal-caption"></div>
    <div id="modal-counter"></div>
  </div>
  <button id="modal-next" class="modal-nav"
    onclick="event.stopPropagation();navigate(1)">&#8250;</button>
</div>
<div id="app">
  <div id="sidebar">
    <h3>Directories</h3>
    <div id="dir-list">Loading\u2026</div>
  </div>
  <div id="main">
    <div id="editor" style="display:none">
      <h3 id="dir-title"></h3>
      <textarea id="desc-text" placeholder="Enter description\u2026"></textarea>
      <div style="margin-top:.5rem">
        <button class="btn btn-primary" onclick="saveDescription()">Save</button>
        <span id="status"></span>
      </div>
      <div class="thumb-section">
        <div class="thumb-header">
          <div>Original <span id="orig-count" style="font-weight:normal;color:#888"></span></div>
          <div>Enhanced <span id="enh-label" style="font-weight:normal;color:#888"></span></div>
        </div>
        <div id="thumb-pairs"></div>
      </div>
    </div>
    <p id="placeholder">Select a directory on the left.</p>
  </div>
</div>
<script>
let currentDir = null;

let modalList = [];
let modalIdx = 0;

function openModal(list, idx) {
  modalList = list;
  modalIdx = idx;
  showModalItem();
  document.getElementById('modal').classList.add('open');
}

function showModalItem() {
  const item = modalList[modalIdx];
  document.getElementById('modal-img').src = item.src;
  document.getElementById('modal-caption').textContent = item.title || '';
  const nav = modalList.length > 1;
  document.getElementById('modal-counter').textContent =
    nav ? `${modalIdx + 1} / ${modalList.length}` : '';
  document.getElementById('modal-prev').style.display = nav ? '' : 'none';
  document.getElementById('modal-next').style.display = nav ? '' : 'none';
}

function navigate(dir) {
  if (!modalList.length) return;
  modalIdx = (modalIdx + dir + modalList.length) % modalList.length;
  showModalItem();
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
  document.getElementById('modal-img').src = '';
  document.getElementById('modal-caption').textContent = '';
  document.getElementById('modal-counter').textContent = '';
  modalList = [];
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
  else if (e.key === 'ArrowRight') navigate(1);
  else if (e.key === 'ArrowLeft') navigate(-1);
});

// ── EXIF tooltip ─────────────────────────────────────────────────────────────
const _exifCache = new Map();

async function _fetchExif(imgPath) {
  if (_exifCache.has(imgPath)) return _exifCache.get(imgPath);
  try {
    const res = await fetch(`/api/exif-enhanced/${imgPath}`);
    const data = await res.json();
    const exif = data.exif || {};
    _exifCache.set(imgPath, exif);
    return exif;
  } catch { return {}; }
}

function _positionExifPopup(popup, x, y) {
  const margin = 14;
  const pw = popup.offsetWidth || 340;
  const ph = popup.offsetHeight || 0;
  const vw = window.innerWidth, vh = window.innerHeight;
  const left = (x + margin + pw > vw) ? x - pw - margin : x + margin;
  const top = Math.max(8, Math.min(y - 10, vh - ph - 8));
  popup.style.left = `${left}px`;
  popup.style.top = `${top}px`;
}

function _showExifPopup(exif, filename, x, y) {
  const popup = document.getElementById('exif-popup');
  const keys = Object.keys(exif);
  if (!keys.length) return;
  const fields = keys.map(k =>
    `<div class="exif-field"><span class="exif-label">${k}</span>` +
    `<span class="exif-value">${exif[k]}</span></div>`).join('');
  popup.innerHTML = `<div class="exif-title">&#128247; ${filename}</div>` +
    `<div class="exif-grid">${fields}</div>`;
  popup.style.display = 'block';
  _positionExifPopup(popup, x, y);
}

function _hideExifPopup() {
  document.getElementById('exif-popup').style.display = 'none';
}

function makeThumb(thumbSrc, fullSrc, title, list, exifPath, albumDate) {
  const item = { src: fullSrc, title };
  const idx = list.length;
  list.push(item);
  const el = document.createElement('img');
  el.src = thumbSrc;
  el.title = title;
  el.onclick = () => openModal(list, idx);
  if (exifPath) {
    const popup = document.getElementById('exif-popup');
    let _leaveTimer = null;
    const _cancelHide = () => {
      if (_leaveTimer) { clearTimeout(_leaveTimer); _leaveTimer = null; }
    };
    const _scheduleHide = () => { _leaveTimer = setTimeout(_hideExifPopup, 120); };
    el.addEventListener('mouseenter', async e => {
      const exif = await _fetchExif(exifPath);
      const display = albumDate ? {'Datum (beschrijving)': albumDate, ...exif} : exif;
      _showExifPopup(display, title, e.clientX, e.clientY);
    });
    el.addEventListener('mouseleave', _scheduleHide);
    popup.addEventListener('mouseenter', _cancelHide);
    popup.addEventListener('mouseleave', _scheduleHide);
  }
  return el;
}

async function loadDirs() {
  try {
    const res = await fetch('/api/directories');
    const data = await res.json();
    const list = document.getElementById('dir-list');
    list.innerHTML = '';
    data.directories.forEach(d => {
      const el = document.createElement('div');
      el.className = 'dir-item';
      const meta = `${d.image_count} images${d.has_description ? ' \u00b7 \u2713 desc' : ''}`;
      el.innerHTML = `<strong>${d.name}</strong><div class="meta">${meta}</div>`;
      el.onclick = () => selectDir(d.path, el);
      list.appendChild(el);
    });
  } catch (err) {
    document.getElementById('dir-list').textContent = `Error loading directories: ${err.message}`;
  }
}

async function selectDir(path, el) {
  document.querySelectorAll('.dir-item').forEach(e => e.classList.remove('active'));
  el.classList.add('active');
  currentDir = path;

  const res = await fetch(`/api/directory/${encodeURIComponent(path)}`);
  const data = await res.json();
  const dir = data.directory;

  document.getElementById('dir-title').textContent = dir.directory;
  document.getElementById('desc-text').value = dir.description;
  document.getElementById('editor').style.display = '';
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('status').textContent = '';

  // Parse Datum from description.txt for the EXIF popup
  const albumDate = (() => {
    for (const line of (dir.description || '').split('\\n')) {
      const lower = line.toLowerCase();
      for (const key of ['datum:', 'date:']) {
        if (lower.startsWith(key)) { const v = line.slice(key.length).trim(); return v || null; }
      }
    }
    return null;
  })();

  // Pair originals with enhanced by stem prefix
  const enhanced = dir.enhanced_images || [];
  document.getElementById('orig-count').textContent = `(${dir.images.length})`;
  const enhLabel = document.getElementById('enh-label');
  enhLabel.textContent = dir.album_name
    ? `\u00b7 ${dir.album_name} (${enhanced.length})` : (enhanced.length ? `(${enhanced.length})` : '');

  // Build stem\u2192enhanced matches (stem == orig stem, or starts with orig stem + '_')
  const stem = name => name.replace(/\\.[^.]+$/, '');
  const usedEnh = new Set();

  const pairs = document.getElementById('thumb-pairs');
  pairs.innerHTML = '';

  dir.images.forEach(orig => {
    const os = stem(orig.name);
    const matches = enhanced.filter(img => {
      const es = stem(img.name);
      return es === os || es.startsWith(os + '_');
    });
    matches.forEach(img => usedEnh.add(stem(img.name)));

    // All images in this row share one navigation list
    const rowList = [];
    const row = document.createElement('div');
    row.className = 'thumb-row';
    const left = document.createElement('div');
    left.className = 'thumb-cell';
    left.appendChild(makeThumb(
      `/api/thumbnail/${orig.path}`, `/api/image/${orig.path}`, orig.name, rowList));
    const right = document.createElement('div');
    right.className = 'thumb-cell';
    matches.forEach(img => right.appendChild(makeThumb(
      `/api/thumbnail-enhanced/${img.path}`,
      `/api/image-enhanced/${img.path}`, img.name, rowList, img.path, albumDate)));
    row.appendChild(left); row.appendChild(right);
    pairs.appendChild(row);
  });

  // Unmatched enhanced at bottom (each row has its own list)
  enhanced.filter(img => !usedEnh.has(stem(img.name))).forEach(img => {
    const rowList = [];
    const row = document.createElement('div');
    row.className = 'thumb-row';
    const left = document.createElement('div'); left.className = 'thumb-cell';
    const right = document.createElement('div'); right.className = 'thumb-cell';
    right.appendChild(makeThumb(
      `/api/thumbnail-enhanced/${img.path}`,
      `/api/image-enhanced/${img.path}`, img.name, rowList, img.path, albumDate));
    row.appendChild(left); row.appendChild(right);
    pairs.appendChild(row);
  });
}

async function saveDescription() {
  if (!currentDir) return;
  const desc = document.getElementById('desc-text').value;
  const status = document.getElementById('status');
  const res = await fetch(`/api/directory/${encodeURIComponent(currentDir)}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({description: desc}),
  });
  const data = await res.json();
  status.className = data.success ? '' : 'error';
  status.textContent = data.success ? 'Saved!' : 'Error saving.';
}

loadDirs();
</script>
</body>
</html>
"""


def create_app(
    photos_dir: str | Path = ".",
    thumbnail_size: int = DEFAULT_WEB_THUMBNAIL_SIZE,
    thumbnail_format: str = DEFAULT_WEB_THUMBNAIL_FORMAT,
    description_template: str = DEFAULT_DESCRIPTION_TEMPLATE or _DEFAULT_TEMPLATE,
) -> Flask:
    """Create and configure the Flask description editor application.

    Args:
        photos_dir:           Root directory containing photo sub-directories.
        thumbnail_size:       Default thumbnail width in pixels.
        thumbnail_format:     PIL image format for thumbnails.
        description_template: Template text for new ``description.txt`` files.

    Returns:
        Configured :class:`flask.Flask` instance.
    """
    app = Flask(__name__)
    editor = DescriptionEditor(
        photos_dir=Path(photos_dir),
        description_template=description_template,
        thumbnail_size=thumbnail_size,
        thumbnail_format=thumbnail_format,
    )

    @app.route("/")
    def index() -> Response:
        resp = Response(_INDEX_HTML, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/api/directories", methods=["GET"])
    def list_directories() -> Response:
        try:
            dirs = editor.get_directories()
            return jsonify({"success": True, "directories": dirs})
        except Exception:
            logger.exception("Error listing directories")
            return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.route("/api/directory/<path:dir_path>", methods=["GET"])
    def get_directory(dir_path: str) -> Response:
        try:
            details = editor.get_directory_details(dir_path)
            return jsonify({"success": True, "directory": details})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("Error getting directory %s", dir_path)
            return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.route("/api/directory/<path:dir_path>", methods=["POST"])
    def save_directory(dir_path: str) -> Response:
        try:
            data = request.get_json(force=True) or {}
            description = str(data.get("description", ""))
            success = editor.save_description(dir_path, description)
            return jsonify({"success": success})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("Error saving directory %s", dir_path)
            return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.route("/api/thumbnail/<path:image_path>", methods=["GET"])
    def thumbnail(image_path: str) -> Response:
        try:
            size = request.args.get("size", type=int)
            data = editor.get_thumbnail(image_path, size)
            mime = (
                "image/png" if thumbnail_format == "PNG"
                else "image/webp" if thumbnail_format == "WEBP"
                else "image/jpeg"
            )
            return send_file(io.BytesIO(data), mimetype=mime)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("Error generating thumbnail for %s", image_path)
            return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.route("/api/thumbnail-enhanced/<path:image_path>", methods=["GET"])
    def thumbnail_enhanced(image_path: str) -> Response:
        try:
            size = request.args.get("size", type=int)
            data = editor.get_enhanced_thumbnail(image_path, size)
            mime = (
                "image/png" if thumbnail_format == "PNG"
                else "image/webp" if thumbnail_format == "WEBP"
                else "image/jpeg"
            )
            return send_file(io.BytesIO(data), mimetype=mime)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("Error generating enhanced thumbnail for %s", image_path)
            return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.route("/api/image/<path:image_path>", methods=["GET"])
    def full_image(image_path: str) -> Response:
        try:
            full_path = (editor.photos_dir / image_path).resolve()
            full_path.relative_to(editor.photos_dir)
            if not full_path.is_file():
                return jsonify({"success": False, "error": "Not found"}), 404
            return send_file(full_path)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("Error serving image %s", image_path)
            return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.route("/api/image-enhanced/<path:image_path>", methods=["GET"])
    def full_image_enhanced(image_path: str) -> Response:
        try:
            full_path = (editor.enhanced_base_dir / image_path).resolve()
            full_path.relative_to(editor.enhanced_base_dir)
            return send_file(full_path)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("Error serving enhanced image %s", image_path)
            return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.route("/api/exif-enhanced/<path:image_path>", methods=["GET"])
    def exif_enhanced(image_path: str) -> Response:
        try:
            data = editor.get_exif_data(image_path)
            return jsonify({"success": True, "exif": data})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        except Exception:
            logger.exception("Error reading EXIF for %s", image_path)
            return jsonify({"success": False, "error": "Internal server error"}), 500

    return app

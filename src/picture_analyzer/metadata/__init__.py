"""Metadata reading and writing: EXIF, XMP, GPS."""
from .exif_writer import ExifWriter
from .xmp_writer import XmpWriter

__all__ = ["ExifWriter", "XmpWriter"]

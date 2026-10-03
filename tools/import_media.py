#!/usr/bin/env python3
"""Bring field photos and video clips from a phone folder into the site, safely.

    python tools/import_media.py

Edit IMPORTS below: each entry names a source file, the name to save it as and, for
video, the segment to keep. The script

- re-encodes every photo into a fresh JPEG master in assets/field/ (at most 2400 px),
  which drops all metadata, including the GPS position phones record;
- cuts each video segment, scales it to 720 px wide, removes the sound track and all
  metadata (phones store location in videos too), and writes an H.264 MP4 plus a WebP
  poster frame to static/media/.

Then run tools/media.py to make the web sizes of the photos. Needs Pillow, pillow-heif
(for iPhone HEIC photos) and imageio-ffmpeg (bundles ffmpeg).
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(r"C:\Users\LENOVO\Documents\EM\Consult\Images\Oil palm")
MASTERS = ROOT / "assets" / "field"
MEDIA = ROOT / "static" / "media"

# (source file, saved name) for photos; (source file, saved name, start s, end s, poster s) for clips
PHOTOS = [
    ("IMG_5876.HEIC", "palm-drone-pad"),
    ("IMG_5883.HEIC", "palm-estate-road"),
    ("IMG_5884.HEIC", "palm-gnss"),
    ("IMG_5878.HEIC", "palm-crown"),
    ("IMG_5942.HEIC", "palm-pilot"),
]
CLIPS = [
    ("IMG_5953.MP4", "palm-takeoff", 18.0, 32.0, 6.0),
]


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def import_photo(src, name):
    import pillow_heif
    pillow_heif.register_heif_opener()
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im.thumbnail((2400, 2400), Image.LANCZOS)
    clean = Image.new("RGB", im.size)
    clean.paste(im)  # a fresh image carries no EXIF, GPS or maker notes
    out = MASTERS / f"{name}.jpg"
    clean.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def import_clip(src, name, start, end, poster_at):
    ff = ffmpeg()
    out = MEDIA / f"{name}.mp4"
    subprocess.run([
        ff, "-y", "-loglevel", "error", "-ss", str(start), "-to", str(end), "-i", str(src),
        "-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", "scale=720:-2:flags=lanczos:out_range=tv,fps=30,format=yuv420p", "-color_range", "tv", "-c:v", "libx264", "-profile:v", "high",
        "-preset", "slow", "-crf", "27", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
    ], check=True)
    frame = MEDIA / f"{name}-poster.png"
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(poster_at), "-i", str(out), "-frames:v", "1", str(frame)], check=True)
    poster = Image.open(frame).convert("RGB")
    poster.save(MEDIA / f"{name}-poster.webp", "WEBP", quality=78, method=6)
    frame.unlink()
    return out, poster.size


def main():
    MASTERS.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    for src, name in PHOTOS:
        out = import_photo(SOURCE / src, name)
        print(f"photo {src} -> {out.relative_to(ROOT)} ({out.stat().st_size / 1024:.0f} KB)")
    for src, name, start, end, poster_at in CLIPS:
        out, size = import_clip(SOURCE / src, name, start, end, poster_at)
        print(f"clip  {src} {start}-{end}s -> {out.relative_to(ROOT)} {size[0]}x{size[1]} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

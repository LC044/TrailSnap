"""Shared Pillow policy for high-resolution camera photos and worker processes."""

from PIL import Image

# 200 MP camera photos exceed Pillow's default hard limit (~179 MP).
# Keep a finite guard: warn above 250 MP and reject above 500 MP.
# Set once on import, never temporarily toggle this process-wide setting.
Image.MAX_IMAGE_PIXELS = 250_000_000

# Above this size, thumbnail generation uses its own JPEG decoder so draft()
# can reduce memory without changing the image reused for EXIF and dimensions.
LARGE_IMAGE_PIXELS = 89_478_485

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff', '.heic', '.heif')
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.webm')

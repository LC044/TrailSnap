"""Shared Pillow policy for high-resolution camera photos and worker processes."""

from PIL import Image

# 200 MP camera photos exceed Pillow's default hard limit (~179 MP).
# Keep a finite guard: warn above 250 MP and reject above 500 MP.
# Set once on import, never temporarily toggle this process-wide setting.
Image.MAX_IMAGE_PIXELS = 250_000_000

# Above this size, thumbnail generation uses its own JPEG decoder so draft()
# can reduce memory without changing the image reused for EXIF and dimensions.
LARGE_IMAGE_PIXELS = 89_478_485

RAW_EXTENSIONS = ('.raf', '.nef', '.nrw', '.dng', '.cr2', '.cr3', '.crw', '.arw', '.sr2', '.srf', '.orf', '.rw2', '.raw', '.pef', '.rwl', '.srw', '.3fr', '.fff', '.iiq', '.kdc', '.dcr', '.mrw', '.x3f')

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff', '.heic', '.heif') + RAW_EXTENSIONS
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.webm')


def open_image(source, filename=None, *, full_resolution=False):
    """Open ordinary images lazily; adapt camera RAW to the same Pillow contract.

    The caller owns the returned image and the input stream. RAW previews are
    detached from their decoder, so metadata and thumbnail jobs can reuse them.
    """
    import os
    name = filename or (source if isinstance(source, (str, os.PathLike)) else getattr(source, 'name', ''))
    if os.path.splitext(str(name))[1].lower() not in RAW_EXTENSIONS:
        return Image.open(source)
    import io
    import rawpy

    with rawpy.RawPy() as raw:
        if isinstance(source, (str, os.PathLike)):
            raw.open_file(str(source))
        else:
            source.seek(0)
            raw.open_buffer(source)
        sizes = raw.sizes
        if sizes.width * sizes.height > Image.MAX_IMAGE_PIXELS * 2:
            raise Image.DecompressionBombError("RAW image exceeds pixel limit")
        metadata = None
        # TIFF-based RAWs (e.g. NEF) expose EXIF through Pillow without decoding.
        try:
            if hasattr(source, 'seek'):
                source.seek(0)
            with Image.open(source) as header:
                exif = header.getexif()
                # Materialize nested IFDs before closing the original stream.
                for tag in (34665, 34853):
                    if tag in exif:
                        exif.get_ifd(tag)
                metadata = exif.tobytes()
        except (OSError, ValueError, SyntaxError):
            pass
        try:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                with Image.open(io.BytesIO(thumb.data)) as preview:
                    image = preview.copy()
            else:
                image = Image.fromarray(thumb.data)
            method = 'embedded'
            if full_resolution and (image.width < sizes.width or image.height < sizes.height):
                metadata = metadata or image.info.get('exif')
                image.close()
                image = None
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError, OSError):
            raw.unpack()
            image = Image.fromarray(raw.postprocess(use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB,
                                                   output_bps=8, user_flip=0))
            method = 'decoded'
        if full_resolution and image is None:
            raw.unpack()
            image = Image.fromarray(raw.postprocess(use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB,
                                                   output_bps=8, user_flip=0))
            method = 'decoded'
        if metadata:
            image.info['exif'] = metadata
            image._exif = None
        from datetime import datetime
        other = raw.other
        exif = image.getexif()
        photo_ifd = exif.get_ifd(34665) if 34665 in exif else {}
        if not photo_ifd.get(36867) and isinstance(getattr(other, 'timestamp', None), datetime):
            timestamp = other.timestamp.strftime('%Y:%m:%d %H:%M:%S')
            exif.setdefault(306, timestamp)
            photo_ifd[36867] = timestamp
        for tag, field in ((34855, 'iso_speed'), (33434, 'shutter_speed'),
                           (33437, 'aperture'), (37386, 'focal_length')):
            value = getattr(other, field, None)
            if tag not in photo_ifd and isinstance(value, (int, float)) and value > 0:
                photo_ifd[tag] = value
        if photo_ifd:
            exif[34665] = photo_ifd
        # LibRaw flip values map to EXIF orientation. Keep pixels unrotated;
        # the shared EXIF transpose in storage applies orientation once.
        if not image.getexif().get(274):
            image.getexif()[274] = {0: 1, 3: 3, 5: 8, 6: 6}.get(sizes.flip, 1)
        image.info['raw_original_size'] = (sizes.width, sizes.height)
        image.info['raw_preview_source'] = method
        return image

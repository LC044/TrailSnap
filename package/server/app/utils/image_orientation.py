from PIL import Image


def display_image_size(image: Image.Image) -> tuple[int, int]:
    """Return dimensions after EXIF orientation without decoding the pixels."""
    info = getattr(image, 'info', None)
    width, height = info.get('raw_original_size', image.size) if isinstance(info, dict) else image.size
    if image.getexif().get(274) in (5, 6, 7, 8):
        return height, width
    return width, height

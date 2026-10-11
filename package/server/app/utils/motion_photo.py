import os
import re
import mmap
from app.service.disk_budget import budgeted_open, disk_budget


# HEIF/AVIF images use the same ftyp box as MP4. Phone JPEGs can carry
# an auxiliary HEIF image, so ftyp alone is not evidence of a motion clip.
_IMAGE_BRANDS = {
    b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'hevm', b'hevs',
    b'mif1', b'mif2', b'msf1', b'avif', b'avis', b'miaf', b'j2ki',
}
_VIDEO_BRANDS = {b'isom', b'mp41', b'mp42', b'avc1', b'qt  ', b'M4V ', b'M4VH', b'M4VP'}


def extract_video_from_stream(source, video_path: str) -> str | None:
    """Extract from the import snapshot without reopening the original JPEG."""
    if source is None:
        return None
    try:
        source.seek(0, os.SEEK_END)
        size = source.tell()
        source.seek(0)
        header = source.read(64 * 1024)
        match = re.search(b'MicroVideoOffset=["\']?(\\d+)["\']?', header)
        if match is None:
            match = re.search(b'<[\\w:]*MicroVideoOffset>(\\d+)<', header)
        start = size - int(match.group(1)) if match else None
        if start is None:
            source.seek(0)
            tail = b''
            position = 0
            while chunk := source.read(1024 * 1024):
                data = tail + chunk
                for candidate in re.finditer(b'ftyp', data):
                    local_start = candidate.start() - 4
                    absolute_start = position - len(tail) + local_start
                    if local_start >= 0 and absolute_start > 0 and _is_video_ftyp(data, local_start, len(data)):
                        start = absolute_start
                        break
                if start is not None:
                    break
                position += len(chunk)
                tail = data[-132:]
        if start is None or not 0 < start < size:
            return None
        if os.path.exists(video_path):
            return video_path
        source.seek(start)
        with budgeted_open(video_path, 'wb') as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        return video_path
    except Exception:
        return None


def _is_video_ftyp(data, start: int, file_size: int) -> bool:
    size = int.from_bytes(data[start:start + 4], 'big')
    if size < 16 or size > 128 or size % 4 or start + size > file_size:
        return False
    # Skip minor_version (bytes 12..15); it is not a compatible brand.
    brands = {data[start + 8:start + 12]}
    brands.update(data[pos:pos + 4] for pos in range(start + 16, start + size, 4))
    if brands & _IMAGE_BRANDS:
        return False
    return any(
        brand in _VIDEO_BRANDS or brand.startswith((b'iso', b'3gp', b'3g2'))
        for brand in brands
    )

def get_video_offset(file_path: str) -> int | None:
    """
    Detects if a file is a Google Motion Photo and returns the video offset (bytes from end).
    Returns None if not a Motion Photo.
    """
    try:
        with budgeted_open(file_path) as f:
            # 1. Check for XMP Metadata (GCamera:MicroVideoOffset)
            # Read the beginning of the file (usually within first 64KB for XMP)
            chunk_size = 64 * 1024
            data = f.read(chunk_size)

            # Pattern for XMP MicroVideoOffset
            # Looks like: GCamera:MicroVideoOffset="12345" or <GCamera:MicroVideoOffset>12345</GCamera:MicroVideoOffset>
            # We look for the attribute/tag and capture the digits
            
            # Simple regex for MicroVideoOffset
            # We look for the keyword and then some digits
            # Note: XMP can be complex, but usually it's plain text in the header.

            # Case 1: Attribute style
            # xmp:GCamera:MicroVideoOffset="12345"
            match = re.search(b'MicroVideoOffset=["\']?(\\d+)["\']?', data)
            if match:
                return int(match.group(1))

            # Case 2: Tag style
            # <GCamera:MicroVideoOffset>12345</GCamera:MicroVideoOffset>
            match = re.search(b'<[\\w:]*MicroVideoOffset>(\\d+)<', data)
            if match:
                return int(match.group(1))

        # 2. Fallback: Scan for embedded MP4 (ftyp atom)
        # We assume the video is appended to the file.
        # We look for the 'ftyp' atom which marks the start of the video.
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return None
            
        with open(file_path, 'rb') as f:
            try:
                with disk_budget.slot(file_path), mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    matches = [m.start() for m in re.finditer(b'ftyp', mm)]
                    
                    for pos in matches:
                        if pos < 4: continue
                        atom_start = pos - 4
                        
                        # Check if this looks like a valid atom size
                        if atom_start + 4 > file_size: continue
                        
                        # We need to read the size bytes. mmap allows slicing.
                        size_bytes = mm[atom_start:atom_start+4]
                        size = int.from_bytes(size_bytes, 'big')
                        
                        # Sanity check for ftyp atom size (usually small, e.g. 20-32 bytes)
                        if 8 <= size <= 128 and _is_video_ftyp(mm, atom_start, file_size):
                            if atom_start > 0:
                                return file_size - atom_start
            except ValueError:
                # Can happen if file is empty (handled above) or other mmap issues
                return None
            
            return None

    except Exception:
        return None

def extract_video(file_path: str, offset: int = None, video_path: str = None) -> str | None:
    """
    Extracts the video from a Motion Photo to a separate .mp4 file.
    Returns the path to the extracted video if successful, else None.
    The video is saved with the same basename as the image, but with .mp4 extension.
    If the .mp4 file already exists, it is NOT overwritten, and we return its path.
    """
    if offset is None:
        offset = get_video_offset(file_path)
        if offset is None:
            return None

    if video_path is None:
        video_path = os.path.splitext(file_path)[0] + '.mp4'

    if os.path.exists(video_path):
        return video_path

    try:
        file_size = os.path.getsize(file_path)
        video_start = file_size - offset

        if video_start <= 0 or video_start >= file_size:
            return None

        with budgeted_open(file_path) as f_in:
            f_in.seek(video_start)
            video_data = f_in.read(offset)

            # Verify it looks like a video (check for 'ftyp' or generic binary signature?)
            # MP4 usually starts with size (4 bytes) + 'ftyp'
            # But the embedded stream might not have the header at exactly the offset?
            # Actually, the offset is usually exact.

            # Let's write it.
            with budgeted_open(video_path, 'wb') as f_out:
                f_out.write(video_data)

        return video_path
    except Exception:
        # If extraction fails, we might want to cleanup
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass
        return None

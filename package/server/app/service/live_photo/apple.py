import os
import re
from typing import Optional
from .base import LivePhotoParser

class AppleLivePhotoParser(LivePhotoParser):
    def is_supported(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext == '.heic' or ext =='.mov'

    def parse(self, file_path: str) -> Optional[str]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.heic':
            return self._parse_image(file_path)
        elif ext in ('.mov', '.mp4'):
            return self._parse_video(file_path)
        return None

    def _parse_image(self, file_path: str) -> Optional[str]:
        # Strip the image extension case-insensitively so paths normalised
        # by Linux / NAS tools (``IMG.heic``) still pair with the .MOV clip.
        import re as _re
        return _re.sub(r'\.[Hh][Ee][Ii][Cc]$', '', file_path)

    def _parse_video(self, file_path: str) -> Optional[str]:
        # Mirror of _parse_image for the video side; same case-insensitive
        # rationale. ``ScanFolderStrategy`` compares the two stems to decide
        # whether a pair is a live photo, so a case mismatch silently
        # disabled live-photo detection for every lowercase path.
        import re as _re
        return _re.sub(r'\.[Mm][Oo][Vv]$', '', file_path)

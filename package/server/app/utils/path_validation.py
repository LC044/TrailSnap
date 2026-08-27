"""Cross-platform validation for paths TrailSnap is about to create."""

import os
import re
from pathlib import Path


_WINDOWS_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _pathconf_limit(directory: str, name: str, fallback: int) -> int:
    """Read a filesystem limit from the nearest existing parent."""
    current = Path(directory).absolute()
    while not current.exists() and current.parent != current:
        current = current.parent
    try:
        return int(os.pathconf(str(current), name))
    except (AttributeError, OSError, ValueError):
        return fallback


def validate_filename(filename: str, directory: str) -> None:
    """Raise ValueError when *filename* cannot be one filesystem component."""
    if not filename or filename in {".", ".."}:
        raise ValueError("文件名不能为空或使用 . / ..")
    if os.path.basename(filename) != filename or "/" in filename or "\\" in filename:
        raise ValueError("文件名不能包含路径分隔符")
    if "\x00" in filename:
        raise ValueError("文件名不能包含空字符")

    if os.name == "nt":
        if _WINDOWS_INVALID_CHARS.search(filename):
            raise ValueError("文件名包含 Windows 不允许的字符")
        if filename.endswith((" ", ".")):
            raise ValueError("Windows 文件名不能以空格或句点结尾")
        if filename.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            raise ValueError("文件名使用了 Windows 保留名称")
        if _utf16_units(filename) > 255:
            raise ValueError("文件名超过 Windows 的 255 个 UTF-16 单元限制")
    else:
        name_max = _pathconf_limit(directory, "PC_NAME_MAX", 255)
        if len(os.fsencode(filename)) > name_max:
            raise ValueError(f"文件名超过当前文件系统的 {name_max} 字节限制")


def validate_target_path(path: str) -> None:
    """Validate the basename and total length of a path before file I/O."""
    absolute = os.path.abspath(path)
    directory, filename = os.path.split(absolute)
    validate_filename(filename, directory)

    if os.name == "nt":
        # NTFS long paths have a 32,767 UTF-16-unit ceiling. Whether legacy
        # applications accept paths above MAX_PATH is left to the OS/Python
        # runtime, which returns a precise OSError when long paths are disabled.
        if _utf16_units(absolute) > 32767:
            raise ValueError("完整路径超过 Windows 的 32767 个 UTF-16 单元限制")
    else:
        path_max = _pathconf_limit(directory, "PC_PATH_MAX", 4096)
        if len(os.fsencode(absolute)) > path_max:
            raise ValueError(f"完整路径超过当前文件系统的 {path_max} 字节限制")

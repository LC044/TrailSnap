import hashlib
import os
import asyncio
from app.service.disk_budget import media_io

@media_io()
def calculate_file_md5(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """
    Calculate MD5 hash of a file by reading it in chunks to avoid memory overflow.
    
    Args:
        file_path (str): The path to the file.
        chunk_size (int): The size of chunks to read. Defaults to 1 MiB.
        
    Returns:
        str: The MD5 hash of the file as a hexadecimal string.
    """
    if not os.path.exists(file_path):
        return ""
        
    md5_hash = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except Exception as e:
        return ""

async def calculate_file_md5_async(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """
    Calculate MD5 hash of a file asynchronously.
    
    Uses asyncio.to_thread to run the synchronous I/O and CPU-bound hashing 
    in a separate thread, avoiding blocking the event loop.
    
    Args:
        file_path (str): The path to the file.
        chunk_size (int): The size of chunks to read. Defaults to 1 MiB.
        
    Returns:
        str: The MD5 hash of the file as a hexadecimal string.
    """
    return await asyncio.to_thread(calculate_file_md5, file_path, chunk_size)

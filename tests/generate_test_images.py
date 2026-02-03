#!/usr/bin/env python3
"""Generate synthetic test images (red, green, blue).
Usage: python3 generate_test_images.py
"""

import os
from pathlib import Path
import struct
import zlib

def create_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """Create a raw PNG image with solid color."""
    # PNG Header
    header = b'\x89PNG\r\n\x1a\n'
    
    # IHDR chunk
    # Width, Height, Bit depth (8), Color type (2=Truecolor), Compression(0), Filter(0), Interlace(0)
    ihdr_data = struct.pack('!I', width) + struct.pack('!I', height) + b'\x08\x02\x00\x00\x00'
    ihdr = struct.pack('!I', len(ihdr_data)) + b'IHDR' + ihdr_data + struct.pack('!I', zlib.crc32(b'IHDR' + ihdr_data))
    
    # IDAT chunk
    # Raw pixel data: 1 byte filter type (0) per scanline + RGB bytes
    raw_data = b''
    row_data = b'\x00' + struct.pack('BBB', *color) * width
    raw_data = row_data * height
    
    compressed = zlib.compress(raw_data)
    idat = struct.pack('!I', len(compressed)) + b'IDAT' + compressed + struct.pack('!I', zlib.crc32(b'IDAT' + compressed))
    
    # IEND chunk
    iend = b'\x00\x00\x00\x00IEND\xAE\x42\x60\x82'
    
    return header + ihdr + idat + iend

def main():
    target_dir = Path.home() / "Work" / "cl_server_test_media"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    colors = {
        "test_red.png": (255, 0, 0),
        "test_green.png": (0, 255, 0),
        "test_blue.png": (0, 0, 255)
    }
    
    print(f"Generating images in {target_dir}...")
    
    for filename, color in colors.items():
        path = target_dir / filename
        data = create_png(100, 100, color)
        path.write_bytes(data)
        print(f"Created {path}")

if __name__ == "__main__":
    main()

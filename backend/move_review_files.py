#!/usr/bin/env python3
"""Move German review audio files from src/review_audio to review_audio"""
import shutil
from pathlib import Path

src_dir = Path("src/review_audio")
dest_dir = Path("review_audio")

if not src_dir.exists():
    print(f"❌ Source directory not found: {src_dir}")
    exit(1)

dest_dir.mkdir(parents=True, exist_ok=True)

# Copy all German files
copied = 0
for file in src_dir.glob("*_de.mp3"):
    dest_file = dest_dir / file.name
    shutil.copy2(file, dest_file)
    print(f"✅ Copied: {file.name}")
    copied += 1

if copied > 0:
    print(f"\n🎉 Successfully copied {copied} files to {dest_dir.absolute()}")
    # Optionally remove source directory
    try:
        for file in src_dir.glob("*_de.mp3"):
            file.unlink()
        src_dir.rmdir()
        print(f"🧹 Cleaned up {src_dir}")
    except Exception as e:
        print(f"⚠️ Could not clean up source directory: {e}")
else:
    print("⚠️ No German files found to copy")


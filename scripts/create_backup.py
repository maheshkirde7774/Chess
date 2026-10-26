"""
Automated Project Backup Utility for Neon Four Chess
Creates timestamped, portable zip archives of the source codebase while excluding
heavy build artifacts, node_modules, caches, and git directories.
"""

import os
import sys
import zipfile
import datetime
import hashlib

EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".gradle",
    "build",
    ".idea",
    ".vscode",
    "backups"
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd"
}

def create_backup():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backups_dir = os.path.join(base_dir, "backups")
    os.makedirs(backups_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"neon_four_chess_backup_{timestamp}.zip"
    archive_path = os.path.join(backups_dir, archive_name)

    total_files = 0
    total_uncompressed_bytes = 0

    print(f"Creating backup archive: {archive_path}")

    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(base_dir):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".git")]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in EXCLUDE_EXTENSIONS:
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_dir)

                # Skip root-level db or backups
                if rel_path.startswith("backups"):
                    continue

                zipf.write(full_path, rel_path)
                total_files += 1
                total_uncompressed_bytes += os.path.getsize(full_path)

    archive_size = os.path.getsize(archive_path)

    # Compute SHA-256 of the backup archive
    sha256 = hashlib.sha256()
    with open(archive_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    hash_hex = sha256.hexdigest()

    print("\nBackup Created Successfully!")
    print(f"Archive File:    {archive_name}")
    print(f"Absolute Path:   {archive_path}")
    print(f"Files Archived:  {total_files}")
    print(f"Uncompressed:    {total_uncompressed_bytes / (1024*1024):.2f} MB")
    print(f"Archive Size:    {archive_size / (1024*1024):.2f} MB")
    print(f"SHA-256:         {hash_hex}")

    return archive_path, archive_name, archive_size, total_files, hash_hex

if __name__ == "__main__":
    create_backup()

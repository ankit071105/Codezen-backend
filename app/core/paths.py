"""
Single source of truth for filesystem paths used across the app.
Both main.py (static file mount) and auth.py (avatar upload) import
from here so they can never accidentally point at two different
directories on disk.
"""
import os

# app/core/paths.py -> app/core -> app -> project root (3 levels up)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "static"))
AVATAR_DIR = os.path.abspath(os.path.join(STATIC_DIR, "avatars"))

os.makedirs(AVATAR_DIR, exist_ok=True)

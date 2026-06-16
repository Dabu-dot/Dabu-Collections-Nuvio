#!/usr/bin/env python3
"""
Backdrop generator adapted for Streaming Services using Vertical Posters.
Features heavy left-fading dark gradients and brand color accents.
"""

import argparse
import colorsys
import contextlib
import io
import itertools
import math
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl

import requests
from PIL import Image, ImageDraw, ImageFilter

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"

POSTER_SIZE = "w780" 
QUALITY_PRESETS = {
    "compressed": {"quality": 85, "progressive": True, "subsampling": "4:2:0"},
    "high": {"quality": 95, "progressive": False, "subsampling": 0},
}

CARD_RADIUS = 16
TILT_DEG = 10
TILE_W = 220        
TILE_H = 330        
GAP = 14            
ROWS = 7
COLS = 9
STAGGER = 0.35

FOCUS_X = 0.75
FOCUS_Y = 0.50

SIZE_PRESETS = {
    "4k": (3840, 2160, 3840 / 1920),
    "1080p": (1920, 1080, 1.0),
}

def cleanup_pycache():
    shutil.rmtree(SCRIPT_DIR / "__pycache__", ignore_errors=True)

def parse_accent_color(value):
    if not value:
        return (0, 0, 0)
    value = value.strip().lstrip("#")
    if "," in value:
        return tuple(int(p.strip()) for p in value.split(","))
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))

def tmdb_get(endpoint, params, api_key):
    query = dict(params)
    query["api_key"] = api_key
    for attempt in range(3):
        try:
            response = requests.get(f"{TMDB_BASE}{endpoint}", params=query, timeout=20)
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)

def parse_request_spec(spec):
    raw_media_type, raw_request = spec.split(":", 1)
    media_type = "tv" if raw_media_type.strip() == "series" else raw_media_type.strip()
    return {"media_type": media_type, "params": dict(parse_qsl(raw_request.strip(), keep_blank_values=True))}

def fetch_titles(request_specs, api_key, count=50):
    merged = []
    for spec in request_specs:
        endpoint = f"/discover/{spec['media_type']}"
        base_params = {
            "sort_by": "popularity.desc",
            "vote_count.gte": "150",
            **spec["params"]
        }
        
        for page in range(1, 3):
            data = tmdb_get(endpoint, {**base_params, "page": page}, api_key)
            for item in data.get("results", []):
                if item.get("poster_path"):
                    merged.append((spec["media_type"], item))
            if page >= data.get("total_pages", 3):
                break

    seen = set()
    unique = []
    for media_type, item in merged:
        key = (media_type, item["id"])
        if key not in seen:
            seen.add(key)
            unique.append((media_type, item))
            if len(unique) >= count:
                break
    return unique

def download_image_url(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except Exception:
        return None

def rounded_rect_mask(width, height, radius=CARD_RADIUS):
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=255)
    return mask

def make_tile(image, tile_width, tile_height):
    source_width, source_height = image.size
    target_ratio = tile_width / tile_height
    current_ratio = source_width / source_height
    
    if current_ratio > target_ratio:
        new_width = int(source_height * target_ratio)
        left = (source_width - new_width) // 2
        image = image.crop((left, 0, left + new_width, source_height))
    else:
        new_height = int(source_width / target_ratio)
        top = (source_height - new_height) // 2
        image = image.crop((0, top, source_width, top + new_height))
        
    image = image.resize((tile_width, tile_height), Image.LANCZOS)
    scaled_radius = max(12, int(CARD_RADIUS * tile_width / TILE_W))
    mask = rounded_rect_mask(tile_width, tile_height, radius=scaled_radius)
    result = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    result.paste(image, mask=mask)
    return result

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)

    cols, rows = COLS + 4, ROWS + 4
    needed = rows * cols
    tile_list = (tiles * (needed // len(tiles) + 1))[:needed]
    stagger_px = int(STAGGER * (tile_width + gap))

    grid_width = cols * (tile_width + gap) + rows * stagger_px
    grid_height = rows * (tile_height + gap)
    grid = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))

    for row in range(rows):
        for col in range(cols):
            idx = row * cols + col
            if idx >= len(tile_list):
                break
            x = row * stagger_px + col * (tile_width + gap)
            y = row * (tile_height + gap)
            tile = make_tile(tile_list[idx], tile_width, tile_height)
            grid.paste(tile, (x, y), tile)

    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rotated_width, rotated_height = rotated.size

    focus_in_rot_x = FOCUS_X * rotated_width
    focus_in_rot_y = FOCUS_Y * rotated_height

    paste_x = int(canvas_width * 0.55 - focus_in_rot_x)
    paste_y = int(canvas_height * 0.50 - focus_in_rot_y)

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (5, 7, 9, 255))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas

def apply_gradient(canvas, accent):
    width, height = canvas.size
    
    left_black = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels_lb = left_black.load()
    for x in range(width):
        mix = max(0.0, 1.0 - (x / (width * 0.58)))
        alpha = int(255 * (mix ** 1.3))
        if alpha:
            for y in range(height):
                pixels_lb[x, y] = (5, 7, 9, alpha)

    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels_v = vignette.load()
    for y in range(height):
        mix_bottom = max(0.0, (y - height * 0.65) / (height * 0.35))
        mix_top = max(0.0, (height * 0.25 - y) / (height * 0.25))
        alpha = int(220 * (mix_bottom ** 1.5)) + int(180 * (mix_top ** 1.5))
        if alpha:
            for x in range(width):
                pixels_v[x, y] = (5, 7, 9, min(255, alpha))

    accent_layer = Image.new("RGBA", (width // 4, height // 4), (0, 0, 0, 0))
    pixels_a = accent_layer.load()
    r, g, b = accent
    max_diag = math.hypot(width // 4, height // 4)
    for x in range(width // 4):
        for y in range(height // 4):
            dist = math.hypot((width // 4) - x, y)
            mix = max(0.0, 1.0 - (dist / (max_diag * 0.85)))
            alpha = int(140 * (mix ** 1.8))
            if alpha:
                pixels_a[x, y] = (r, g, b, alpha)
                
    accent_layer = accent_layer.resize((width, height), Image.BILINEAR)
    accent_layer = accent_layer.filter(ImageFilter.GaussianBlur(radius=width // 32))

    result = Image.alpha_composite(canvas, left_black)
    result = Image.alpha_composite(result, vignette)
    return Image.alpha_composite(result, accent_layer)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--tmdb-request", action="append", required=True)
    parser.add_argument("--accent-color", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", default="1080p")
    args = parser.parse_args()

    accent = parse_accent_color(args.accent_color)
    request_specs = [parse_request_spec(req) for req in args.tmdb_request]
    
    print(f"Generating optimized streaming backdrop for: {args.label}")
    titles = fetch_titles(request_specs, args.api_key, count=45)
    
    tile_images = []
    for idx, (media_type, item) in enumerate(titles, start=1):
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print("Error: No posters downloaded.")
        sys.exit(1)

    tile_images = (tile_images * (20 // len(tile_images) + 1))[:20] if len(tile_images) < 15 else tile_images

    width, height, scale = SIZE_PRESETS[args.size]
    canvas = build_tilted_grid(tile_images, width, height, scale=scale)
    canvas = apply_gradient(canvas, accent)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    final = canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully generated vertical-grid assets for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

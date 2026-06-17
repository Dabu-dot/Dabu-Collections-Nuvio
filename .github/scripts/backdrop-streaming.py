#!/usr/bin/env python3
"""
Premium Backdrop Generator - Strict Right Edge Positioning & Vertical Centering (V13)
Fixes the vertical sag and forces the grid layer to align flawlessly with the right boundary.
"""

import argparse
import io
import itertools
import math
import os
import shutil
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

SCRIPT_DIR = Path(__file__).resolve().parent
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"
POSTER_SIZE = "w780"

QUALITY_PRESETS = {
    "compressed": {"quality": 95, "progressive": True, "subsampling": "4:2:0"}
}

# --- CONFIGURATION GÉOMÉTRIQUE VERROUILLÉE ---
CARD_RADIUS = 22    
TILE_W = 320        
TILE_H = 480        
GAP = 34            
TILT_DEG = -20      

COLS = 4            
ROWS = 5            # Repassage à 5 lignes bien centrées pour éviter l'effet "trop bas"

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

BRAND_MAPPING = {
    "netflix":      {"network": "213",  "company": "60"},        
    "disneyplus":   {"network": "2739", "company": "2|3|2165"},  
    "hbomax":       {"network": "49",   "company": "174|429"},   
    "appletv":      {"network": "2552", "company": "191065"},    
    "hulu":         {"network": "453",  "company": "6113"},      
    "peacock":      {"network": "3353", "company": "33"},        
    "primevideo":   {"network": "1024", "company": "20580"},     
    "paramount":    {"network": "4330", "company": "4"},         
    "shudder":      {"network": "2326", "company": "60608"}      
}

BRAND_PALETTES = {
    "netflix":      {"base": (8, 0, 2),       "mid": (80, 5, 10),     "light": (229, 9, 20)},
    "disneyplus":   {"base": (2, 6, 23),      "mid": (5, 30, 80),     "light": (0, 110, 153)},
    "hbomax":       {"base": (11, 3, 24),     "mid": (40, 15, 95),    "light": (107, 33, 224)},
    "appletv":      {"base": (12, 12, 14),    "mid": (45, 45, 48),    "light": (145, 145, 150)},
    "crunchyroll":  {"base": (18, 8, 2),      "mid": (130, 40, 5),    "light": (244, 117, 33)},
    "hulu":         {"base": (0, 15, 7),      "mid": (10, 80, 45),    "light": (28, 231, 131)},
    "peacock":      {"base": (4, 8, 20),      "mid": (8, 45, 110),    "light": (0, 108, 225)},
    "shudder":      {"base": (15, 2, 2),      "mid": (80, 0, 0),      "light": (195, 10, 10)},
    "primevideo":   {"base": (2, 14, 28),     "mid": (7, 65, 125),    "light": (26, 146, 244)},
    "paramount":    {"base": (0, 8, 26),      "mid": (0, 50, 145),    "light": (0, 116, 228)}
}

def cleanup_pycache():
    shutil.rmtree(SCRIPT_DIR / "__pycache__", ignore_errors=True)

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

def fetch_curated_titles(label, api_key, target_count=40):
    merged = []
    seen_ids = set()
    slug = label.lower().replace(" ", "").replace("+", "plus")

    safe_params = {
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "without_genres": "10749,18",  
        "vote_count.gte": "20"
    }

    if slug == "crunchyroll":
        for media_type in ["tv", "movie"]:
            params = dict(safe_params)
            params.update({
                "with_genres": "16",
                "with_original_language": "ja|ko",
                "vote_count.gte": "30"
            })
            data = tmdb_get(f"/discover/{media_type}", params, api_key)
            for item in data.get("results", []):
                if item.get("poster_path") and item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    merged.append(item)
        return merged[:target_count]

    cfg = BRAND_MAPPING.get(slug, {})
    
    if cfg.get("network"):
        try:
            params = dict(safe_params)
            params["with_networks"] = cfg["network"]
            tv_data = tmdb_get("/discover/tv", params, api_key)
            for item in tv_data.get("results", []):
                if item.get("poster_path") and item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    merged.append(item)
        except Exception as e:
            print(f"TV Fetch Error: {e}")

    if len(merged) < target_count and cfg.get("company"):
        try:
            params = dict(safe_params)
            params["with_companies"] = cfg["company"]
            params["vote_count.gte"] = "40"
            movie_data = tmdb_get("/discover/movie", params, api_key)
            for item in movie_data.get("results", []):
                if item.get("poster_path") and item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    merged.append(item)
                if len(merged) >= target_count:
                    break
        except Exception as e:
            print(f"Movie Fallback Error: {e}")

    return merged[:target_count]

def download_image_url(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except Exception:
        return None

def make_premium_tile(image, tile_width, tile_height, scale):
    src_w, src_h = image.size
    target_ratio = tile_width / tile_height
    src_ratio = src_w / src_h
    
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        image = image.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        image = image.crop((0, top, src_w, top + new_h))
        
    image = image.resize((tile_width, tile_height), Image.LANCZOS)
    
    radius = max(14, int(CARD_RADIUS * scale))
    mask = Image.new("L", (tile_width, tile_height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, tile_width - 1, tile_height - 1], radius=radius, fill=255)
    
    poster_card = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    poster_card.paste(image, mask=mask)
    
    # Ombre Portée Rehaussée V12 préservée
    shadow_padding = int(36 * scale)
    shadow_w = tile_width + (shadow_padding * 2)
    shadow_h = tile_height + (shadow_padding * 2)
    
    shadow_layer = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.rounded_rectangle(
        [shadow_padding, shadow_padding, shadow_padding + tile_width - 1, shadow_padding + tile_height - 1],
        radius=radius,
        fill=(0, 0, 0, 210)  
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(14 * scale)))
    
    tile_container = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    tile_container.paste(shadow_layer, (0, int(8 * scale)))
    tile_container.paste(poster_card, (shadow_padding, shadow_padding), poster_card)
    
    return tile_container

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    """Génère et plaque la grille de manière robuste contre la bordure droite."""
    shadow_padding = int(36 * scale)
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)
    
    step_x = tile_width + gap
    step_y = tile_height + gap
    stagger_y = step_y // 2

    # Grille resserrée et prévisible avant rotation
    grid_width = COLS * step_x + (shadow_padding * 2)
    grid_height = ROWS * step_y + stagger_y + (shadow_padding * 2)
    grid = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))

    tile_pool = itertools.cycle(tiles)

    for col in range(COLS):
        y_offset = stagger_y if (col % 2 == 1) else 0
        for row in range(ROWS):
            tile_asset = next(tile_pool)
            tile_with_shadow = make_premium_tile(tile_asset, tile_width, tile_height, scale)
            
            x = col * step_x + shadow_padding
            y = row * step_y + y_offset + shadow_padding
            grid.paste(tile_with_shadow, (x - shadow_padding, y - shadow_padding), tile_with_shadow)

    # Pivotement propre
    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = rotated.size

    # CALCUL DE POSITION IMMUABLE : Plaquage flanc droit et recentrage vertical strict
    paste_x = int(canvas_width - rot_w + (120 * scale)) 
    paste_y = int((canvas_height - rot_h) // 2)

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    
    return canvas

def generate_diagonal_gradient(width, height, label):
    slug = label.lower().replace(" ", "").replace("+", "plus")
    palette = BRAND_PALETTES.get(slug, {"base": (10, 12, 16), "mid": (35, 40, 55), "light": (90, 100, 125)})
    
    c_dark = palette["base"]
    c_mid = palette["mid"]
    c_light = palette["light"]
    
    bg_gradient = Image.new("RGBA", (width, height))
    pixels = bg_gradient.load()
    
    for y in range(height):
        for x in range(width):
            factor = (x / width + (height - y) / height) / 2.0
            factor = max(0.0, min(1.0, factor))
            
            if factor < 0.5:
                t = factor * 2.0
                r = int(c_light[0] + (c_mid[0] - c_light[0]) * t)
                g = int(c_light[1] + (c_mid[1] - c_light[1]) * t)
                b = int(c_light[2] + (c_mid[2] - c_light[2]) * t)
            else:
                t = (factor - 0.5) * 2.0
                r = int(c_mid[0] + (c_dark[0] - c_mid[0]) * t)
                g = int(c_mid[1] + (c_dark[1] - c_mid[1]) * t)
                b = int(c_mid[2] + (c_dark[2] - c_mid[2]) * t)
                
            pixels[x, y] = (r, g, b, 255)
            
    return bg_gradient

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="TMDB API key")
    parser.add_argument("--label", required=True, help="Streaming Service name")
    parser.add_argument("--output", required=True, help="Output target path")
    parser.add_argument("--size", default="1080p", help="Output size dimension preset")
    args = parser.parse_args()

    print(f"Compiling Solid Anchored Layout V13 for: {args.label}")
    unique_items = fetch_curated_titles(args.label, args.api_key, target_count=40)
    
    tile_images = []
    for item in unique_items:
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print("Error: No posters downloaded.")
        sys.exit(1)

    if len(tile_images) < 16:
        tile_images = (tile_images * (16 // len(tile_images) + 1))[:16]

    width, height, scale = SIZE_PRESETS[args.size]
    
    background = generate_diagonal_gradient(width, height, args.label)
    posters_layer = build_tilted_grid(tile_images, width, height, scale=scale)
    final_canvas = Image.alpha_composite(background, posters_layer)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    final = final_canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully rendered final layout for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

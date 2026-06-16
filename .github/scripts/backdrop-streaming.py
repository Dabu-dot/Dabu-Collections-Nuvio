#!/usr/bin/env python3
"""
Premium Backdrop Generator - Angular Alignment Engine (V4)
Corrects grid layout positioning to eliminate abrupt cuts and aligns the 
brand multi-layer gradient directly onto the -20 degree layout axis.
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

# --- CONFIGURATION GÉOMÉTRIQUE STRICTE ---
CARD_RADIUS = 22    
TILE_W = 280        
TILE_H = 420        
GAP = 30            
TILT_DEG = -20      

# Grille surdimensionnée pour saturer l'espace et simuler la continuité hors-cadre
COLS = 12           
ROWS = 8            

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

# --- PALETTES OFFICIELLES AJUSTÉES (Sombre en haut à droite -> Éclatant en bas à gauche) ---
BRAND_PALETTES = {
    "netflix":      {"base": (8, 0, 2),       "mid": (95, 4, 8),      "light": (229, 9, 20)},
    "disneyplus":   {"base": (2, 6, 23),      "mid": (4, 28, 79),     "light": (0, 110, 153)},
    "hbomax":       {"base": (11, 3, 24),     "mid": (36, 11, 89),    "light": (107, 33, 224)},
    "appletv":      {"base": (12, 12, 14),    "mid": (45, 45, 48),    "light": (150, 150, 155)},
    "crunchyroll":  {"base": (18, 8, 2),      "mid": (135, 43, 2),    "light": (244, 117, 33)},
    "hulu":         {"base": (0, 15, 7),      "mid": (10, 85, 45),    "light": (28, 231, 131)},
    "peacock":      {"base": (4, 8, 20),      "mid": (8, 46, 115),    "light": (0, 108, 225)},
    "shudder":      {"base": (15, 2, 2),      "mid": (80, 0, 0),      "light": (195, 10, 10)},
    "primevideo":   {"base": (2, 14, 28),     "mid": (7, 68, 128),    "light": (26, 146, 244)},
    "paramount":    {"base": (0, 8, 26),      "mid": (0, 50, 150),    "light": (0, 116, 228)}
}

STREAMING_NETWORKS = {
    "netflix": {"networks": "213", "origin_country": "US"},
    "disneyplus": {"networks": "2739", "origin_country": "US"},
    "hbomax": {"networks": "49", "origin_country": "US"},
    "appletv": {"networks": "2552", "origin_country": "US"},
    "crunchyroll": {"networks": "1112|4343", "keywords": "210024|287501"},
    "hulu": {"networks": "453", "origin_country": "US"},
    "peacock": {"networks": "3353", "origin_country": "US"},
    "shudder": {"networks": "2326"}
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

def fetch_premium_titles(label, api_key, count=90):
    merged = []
    slug = label.lower().replace(" ", "").replace("+", "plus")
    net_config = STREAMING_NETWORKS.get(slug, {})

    for media_type in ["tv", "movie"]:
        endpoint = f"/discover/{media_type}"
        base_params = {
            "sort_by": "popularity.desc",
            "vote_count.gte": "100",
            "include_adult": "false",
            "with_original_language": "en|ja" if slug == "crunchyroll" else "en"
        }
        
        if "networks" in net_config and media_type == "tv":
            base_params["with_networks"] = net_config["networks"]
        elif "networks" in net_config and media_type == "movie" and slug == "disneyplus":
            base_params["with_companies"] = "22"
        
        if "origin_country" in net_config:
            base_params["with_origin_country"] = net_config["origin_country"]
        if "keywords" in net_config:
            base_params["with_keywords"] = net_config["keywords"]

        try:
            for page in range(1, 4):
                data = tmdb_get(endpoint, {**base_params, "page": page}, api_key)
                for item in data.get("results", []):
                    if item.get("poster_path"):
                        merged.append(item)
        except Exception as e:
            print(f"Warning fetching {media_type}: {e}")

    seen_ids = set()
    unique = []
    for item in merged:
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            unique.append(item)
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
    
    radius = max(12, int(CARD_RADIUS * scale))
    mask = Image.new("L", (tile_width, tile_height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, tile_width - 1, tile_height - 1], radius=radius, fill=255)
    
    poster_card = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    poster_card.paste(image, mask=mask)
    
    # Ombre portée douce (Drop Shadow) sous la jaquette
    shadow_padding = int(24 * scale)
    shadow_w = tile_width + (shadow_padding * 2)
    shadow_h = tile_height + (shadow_padding * 2)
    
    shadow_layer = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.rounded_rectangle(
        [shadow_padding, shadow_padding, shadow_padding + tile_width - 1, shadow_padding + tile_height - 1],
        radius=radius,
        fill=(0, 0, 0, 140)
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(10 * scale)))
    
    tile_container = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    tile_container.paste(shadow_layer, (0, int(6 * scale)))
    tile_container.paste(poster_card, (shadow_padding, shadow_padding), poster_card)
    
    return tile_container

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    """Génère une nappe géante en quinconce débordant largement pour assurer la continuité."""
    shadow_padding = int(24 * scale)
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)
    
    step_x = tile_width + gap
    step_y = tile_height + gap
    stagger_y = step_y // 2

    # Dimensions massives pour encaisser la rotation sans créer de bordures vides
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

    # Rotation pivotée
    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = rotated.size

    # Ancrage décalé vers le haut et la gauche pour éliminer les coupures nettes
    paste_x = int(canvas_width * 0.38 - (rot_w * 0.35))
    paste_y = int(canvas_height * 0.45 - (rot_h * 0.50))

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    
    # Masque d'opacité progressif global sur la nappe de posters (Plus opaque à droite qu'à gauche)
    grid_fade = Image.new("L", (canvas_width, canvas_height), 255)
    f_draw = ImageDraw.Draw(grid_fade)
    for x in range(canvas_width):
        if x < canvas_width * 0.20:
            alpha = 0
        elif x > canvas_width * 0.75:
            alpha = 200
        else:
            factor = (x - canvas_width * 0.20) / (canvas_width * 0.55)
            alpha = int(200 * (factor ** 1.2))
        f_draw.line([(x, 0), (x, canvas_height)], fill=alpha)
        
    final_grid = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    final_grid.paste(canvas, (0, 0), mask=grid_fade)
    return final_grid

def apply_premium_gradient(canvas, label):
    """Génère un dégradé directionnel linéaire incliné parallèlement à l'angle des posters."""
    width, height = canvas.size
    slug = label.lower().replace(" ", "").replace("+", "plus")
    
    palette = BRAND_PALETTES.get(slug, {"base": (10, 12, 16), "mid": (35, 40, 55), "light": (90, 100, 125)})
    
    c_dark = palette["base"]
    c_mid = palette["mid"]
    c_light = palette["light"]
    
    bg_gradient = Image.new("RGBA", (width, height))
    pixels = bg_gradient.load()
    
    # Angle aligné sur l'inclinaison des posters (-20 degrés convertis en radians)
    angle_rad = math.radians(-TILT_DEG)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    
    # Calcul de la projection maximale pour normaliser le dégradé sur la diagonale
    max_proj = width * cos_a + height * sin_a
    
    for y in range(height):
        for x in range(width):
            # Inversion de l'axe Y pour forcer la lumière claire en bas à gauche
            y_inv = height - y
            proj = x * cos_a + y_inv * sin_a
            factor = proj / max_proj
            factor = max(0.0, min(1.0, factor))
            
            # Interpolation non-linéaire fluide (Courbe sigmoïde douce)
            factor = math.sin(factor * math.pi / 2)
            
            if factor < 0.5:
                # Transition entre Light (Bas-Gauche) et Mid
                t = factor * 2.0
                r = int(c_light[0] + (c_mid[0] - c_light[0]) * t)
                g = int(c_light[1] + (c_mid[1] - c_light[1]) * t)
                b = int(c_light[2] + (c_mid[2] - c_light[2]) * t)
            else:
                # Transition entre Mid et Dark (Haut-Droit)
                t = (factor - 0.5) * 2.0
                r = int(c_mid[0] + (c_dark[0] - c_mid[0]) * t)
                g = int(c_mid[1] + (c_dark[1] - c_mid[1]) * t)
                b = int(c_mid[2] + (c_dark[2] - c_mid[2]) * t)
                
            pixels[x, y] = (r, g, b, 255)

    # Fusion des posters par-dessus le fond coloré linéaire
    return Image.alpha_composite(bg_gradient, canvas)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="TMDB API key")
    parser.add_argument("--label", required=True, help="Streaming Service name")
    parser.add_argument("--output", required=True, help="Output target path")
    parser.add_argument("--size", default="1080p", help="Output size dimension preset")
    args = parser.parse_args()

    print(f"Executing Angular Generation Engine for: {args.label}")
    unique_items = fetch_premium_titles(args.label, args.api_key, count=90)
    
    tile_images = []
    for item in unique_items:
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print(f"Error: No source posters fetched.")
        sys.exit(1)

    if len(tile_images) < 70:
        tile_images = (tile_images * (70 // len(tile_images) + 1))[:70]

    width, height, scale = SIZE_PRESETS[args.size]
    
    # 1. Génération de la nappe inclinée sans fin
    canvas = build_tilted_grid(tile_images, width, height, scale=scale)
    
    # 2. Application du dégradé de marque directionnel imbriqué à -20°
    canvas = apply_premium_gradient(canvas, args.label)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    final = canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully pushed aligned assets for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

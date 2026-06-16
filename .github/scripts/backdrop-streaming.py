#!/usr/bin/env python3
"""
Premium Backdrop Generator - Diagonal Vector Engine (V6)
Enforces a true corner-to-corner diagonal gradient for 16:9 aspect ratios
and pushes the poster matrix strictly to the right hemisphere.
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

# --- GEOMETRIE OPTIMISEE ---
CARD_RADIUS = 22    
TILE_W = 280        
TILE_H = 420        
GAP = 32            
TILT_DEG = -20      

# Grille calibrée pour occuper uniquement le flanc droit sans saturer l'espace
COLS = 8            
ROWS = 7            

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

# --- PALETTES OFFICIELLES ---
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

def fetch_premium_titles(label, api_key, count=70):
    merged = []
    slug = label.lower().replace(" ", "").replace("+", "plus")
    net_config = STREAMING_NETWORKS.get(slug, {})

    for media_type in ["tv", "movie"]:
        endpoint = f"/discover/{media_type}"
        base_params = {
            "sort_by": "popularity.desc",
            "vote_count.gte": "80",
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
            data = tmdb_get(endpoint, base_params, api_key)
            for item in data.get("results", []):
                if item.get("poster_path"):
                    merged.append(item)
        except Exception as e:
            print(f"Warning: {e}")

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
    
    # Ombre portée
    shadow_padding = int(24 * scale)
    shadow_w = tile_width + (shadow_padding * 2)
    shadow_h = tile_height + (shadow_padding * 2)
    
    shadow_layer = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.rounded_rectangle(
        [shadow_padding, shadow_padding, shadow_padding + tile_width - 1, shadow_padding + tile_height - 1],
        radius=radius,
        fill=(0, 0, 0, 160)
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(12 * scale)))
    
    tile_container = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    tile_container.paste(shadow_layer, (0, int(4 * scale)))
    tile_container.paste(poster_card, (shadow_padding, shadow_padding), poster_card)
    
    return tile_container

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    """Génère la nappe de jaquettes décalée magnétiquement vers la droite."""
    shadow_padding = int(24 * scale)
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)
    
    step_x = tile_width + gap
    step_y = tile_height + gap
    stagger_y = step_y // 2

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

    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = rotated.size

    # Ancrage poussé vers la droite pour libérer la moitié gauche
    paste_x = int(canvas_width * 0.65 - (rot_w * 0.40))
    paste_y = int(canvas_height * 0.50 - (rot_h * 0.50))

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    
    # Masque d'opacité horizontal strict (Garantit le vide à gauche)
    grid_fade = Image.new("L", (canvas_width, canvas_height), 255)
    f_draw = ImageDraw.Draw(grid_fade)
    for x in range(canvas_width):
        if x < canvas_width * 0.45:
            alpha = 0
        elif x > canvas_width * 0.85:
            alpha = 220
        else:
            factor = (x - canvas_width * 0.45) / (canvas_width * 0.40)
            alpha = int(220 * factor)
        f_draw.line([(x, 0), (x, canvas_height)], fill=alpha)
        
    final_grid = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    final_grid.paste(canvas, (0, 0), mask=grid_fade)
    return final_grid

def generate_diagonal_gradient(width, height, label):
    """Calcule une projection vectorielle pure de l'angle bas-gauche vers le angle haut-droit."""
    slug = label.lower().replace(" ", "").replace("+", "plus")
    palette = BRAND_PALETTES.get(slug, {"base": (10, 12, 16), "mid": (35, 40, 55), "light": (90, 100, 125)})
    
    c_dark = palette["base"]
    c_mid = palette["mid"]
    c_light = palette["light"]
    
    bg_gradient = Image.new("RGBA", (width, height))
    pixels = bg_gradient.load()
    
    # Vecteur directeur de la diagonale exacte 16:9 (Du coin inférieur gauche vers supérieur droit)
    # Start: (0, height), End: (width, 0) -> Vecteur = (width, -height)
    vx = float(width)
    vy = -float(height)
    v_len_sq = vx*vx + vy*vy
    
    for y in range(height):
        for x in range(width):
            # Coordonnées relatives depuis l'origine du dégradé (0, height)
            rx = float(x) - 0.0
            ry = float(y) - float(height)
            
            # Produit scalaire pour obtenir la projection linéaire brute
            dot = rx * vx + ry * vy
            factor = dot / v_len_sq
            factor = max(0.0, min(1.0, factor))
            
            # Lissage de transition premium
            factor = math.sin(factor * math.pi / 2)
            
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

    print(f"Executing Vector Diagonal Generation for: {args.label}")
    unique_items = fetch_premium_titles(args.label, args.api_key, count=70)
    
    tile_images = []
    for item in unique_items:
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print(f"Error: No posters found.")
        sys.exit(1)

    if len(tile_images) < 45:
        tile_images = (tile_images * (45 // len(tile_images) + 1))[:45]

    width, height, scale = SIZE_PRESETS[args.size]
    
    # 1. Calcul du fond dégradé vectoriel pur d'un angle à l'autre
    background = generate_diagonal_gradient(width, height, args.label)
    
    # 2. Construction de la nappe filtrée et décalée à droite (posters nets)
    posters_layer = build_tilted_grid(tile_images, width, height, scale=scale)
    
    # 3. Superposition finale (les posters restent au-dessus sans contamination de couleur)
    final_canvas = Image.alpha_composite(background, posters_layer)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    final = final_canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully rendered diagonal vector backdrop for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

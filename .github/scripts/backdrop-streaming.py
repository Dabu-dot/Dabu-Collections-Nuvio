#!/usr/bin/env python3
"""
Premium Backdrop Generator - Perfect Blend Engine (V5)
Fixes the layering sequence (posters on top of background), adjusts the brand 
gradient axis to a true 16:9 diagonal (-30°), and tightens the visibility mask.
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
TILT_DEG = -20      # L'inclinaison des posters reste à -20° pour le style...

# Grille large pour garantir la continuité hors-cadre à droite et en haut
COLS = 12           
ROWS = 8            

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

# --- PALETTES OFFICIELLES RECALIBRÉES ---
BRAND_PALETTES = {
    "netflix":      {"base": (6, 0, 1),       "mid": (95, 4, 8),      "light": (229, 9, 20)},
    "disneyplus":   {"base": (2, 6, 21),      "mid": (4, 32, 85),     "light": (0, 120, 165)},
    "hbomax":       {"base": (9, 2, 20),      "mid": (36, 11, 95),    "light": (115, 30, 235)},
    "appletv":      {"base": (10, 10, 11),    "mid": (45, 45, 48),    "light": (155, 155, 160)},
    "crunchyroll":  {"base": (15, 6, 1),      "mid": (140, 40, 2),    "light": (244, 117, 33)},
    "hulu":         {"base": (0, 12, 5),      "mid": (10, 85, 42),    "light": (28, 231, 131)},
    "peacock":      {"base": (3, 6, 18),      "mid": (8, 50, 125),    "light": (0, 115, 235)},
    "shudder":      {"base": (12, 1, 1),      "mid": (85, 0, 0),      "light": (205, 10, 10)},
    "primevideo":   {"base": (2, 12, 25),     "mid": (7, 72, 135),    "light": (26, 146, 244)},
    "paramount":    {"base": (0, 6, 22),      "mid": (0, 55, 160),    "light": (0, 122, 240)}
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
    
    # Drop shadow sous la jaquette
    shadow_padding = int(24 * scale)
    shadow_w = tile_width + (shadow_padding * 2)
    shadow_h = tile_height + (shadow_padding * 2)
    
    shadow_layer = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.rounded_rectangle(
        [shadow_padding, shadow_padding, shadow_padding + tile_width - 1, shadow_padding + tile_height - 1],
        radius=radius,
        fill=(0, 0, 0, 150)  # Ombres légèrement plus denses pour détacher du fond coloré
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(10 * scale)))
    
    tile_container = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    tile_container.paste(shadow_layer, (0, int(6 * scale)))
    tile_container.paste(poster_card, (shadow_padding, shadow_padding), poster_card)
    
    return tile_container

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    """Génère la nappe de jaquettes et applique le masque de fondu strict sans altérer les couleurs."""
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

    # Point d'ancrage optimisé pour la visibilité droite
    paste_x = int(canvas_width * 0.42 - (rot_w * 0.35))
    paste_y = int(canvas_height * 0.45 - (rot_h * 0.50))

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    
    # --- MASQUE D'OPACITÉ DES POSTERS (Resserré pour libérer la gauche) ---
    grid_fade = Image.new("L", (canvas_width, canvas_height), 255)
    f_draw = ImageDraw.Draw(grid_fade)
    for x in range(canvas_width):
        if x < canvas_width * 0.35:     # Disparition totale à gauche avant 35% de l'écran
            alpha = 0
        elif x > canvas_width * 0.85:   # Opacité maximale retenue à droite
            alpha = 215
        else:
            factor = (x - canvas_width * 0.35) / (canvas_width * 0.50)
            alpha = int(215 * (factor ** 1.4))  # Courbe plus abrupte pour un retrait propre
        f_draw.line([(x, 0), (x, canvas_height)], fill=alpha)
        
    final_grid = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    final_grid.paste(canvas, (0, 0), mask=grid_fade)
    return final_grid

def generate_premium_background(width, height, label):
    """Calcule un fond dégradé diagonal parfait à -30° (Bas-Gauche -> Haut-Droit)."""
    slug = label.lower().replace(" ", "").replace("+", "plus")
    palette = BRAND_PALETTES.get(slug, {"base": (10, 12, 16), "mid": (35, 40, 55), "light": (90, 100, 125)})
    
    c_dark = palette["base"]
    c_mid = palette["mid"]
    c_light = palette["light"]
    
    bg_gradient = Image.new("RGBA", (width, height))
    pixels = bg_gradient.load()
    
    # Angle fixé à -30 degrés (Alignement diagonal idéal pour le format 16:9)
    angle_rad = math.radians(30)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    
    max_proj = width * cos_a + height * sin_a
    
    for y in range(height):
        for x in range(width):
            # Inversion de l'axe Y pour ancrer la lumière claire strictement en bas à gauche
            y_inv = height - y
            proj = x * cos_a + y_inv * sin_a
            factor = proj / max_proj
            factor = max(0.0, min(1.0, factor))
            
            # Lissage sigmoïde pour étaler la transition de façon fluide
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

    print(f"Executing Layer-Corrected Blend Engine for: {args.label}")
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
    
    # Étape 1 : Génération du fond dégradé diagonal pur à -30°
    background = generate_premium_background(width, height, args.label)
    
    # Étape 2 : Génération de la nappe de posters posée AU-DESSUS avec son masque d'opacité propre
    posters_layer = build_tilted_grid(tile_images, width, height, scale=scale)
    
    # Étape 3 : Fusion finale (Grille de posters posée proprement sur le fond)
    final_canvas = Image.alpha_composite(background, posters_layer)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    final = final_canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully pushed unified premium backdrop for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

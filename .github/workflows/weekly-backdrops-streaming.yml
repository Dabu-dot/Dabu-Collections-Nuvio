#!/usr/bin/env python3
"""
Premium Backdrop Generator - UI Optimized Style (V2)
Aligns posters in strict vertical columns, applies a 50% vertical staggered 
checkerboard pattern, fixes the aspect ratio, and restores rich, ambient brand gradients.
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
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"
POSTER_SIZE = "w780"

QUALITY_PRESETS = {
    "compressed": {"quality": 92, "progressive": True, "subsampling": "4:2:0"}
}

# --- AJUSTEMENTS DE LA GRILLE PREMIUM ---
CARD_RADIUS = 24    # Coins arrondis fidèles aux modèles
TILE_W = 270        # Largeur de l'affiche
TILE_H = 405        # Ratio 1:1.5 pur (évite l'effet écrasé) [Point 2]
GAP = 24            # Espacement resserré et harmonieux [Point 3]
COLS = 6            # Nombre de colonnes verticales
ROWS = 6            # Nombre de posters par colonne
TILT_DEG = -20      # Inclinaison parfaite constatée sur les modèles

# Ancrage pour pousser la grille sur le tiers droit
FOCUS_X = 0.28
FOCUS_Y = 0.50

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

def cleanup_pycache():
    shutil.rmtree(SCRIPT_DIR / "__pycache__", ignore_errors=True)

def parse_accent_color(value):
    if not value:
        return (10, 15, 25)
    value = value.strip().lstrip("#")
    if len(value) == 6:
        safe_chars = [c if c in "0123456789ABCDEF" else "0" for c in value.upper()]
        safe_value = "".join(safe_chars)
        return tuple(int(safe_value[i:i+2], 16) for i in (0, 2, 4))
    return (10, 15, 25)

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

def fetch_titles(request_specs, api_key, count=60):
    merged = []
    for spec in request_specs:
        endpoint = f"/discover/{spec['media_type']}"
        base_params = {
            "sort_by": "popularity.desc",
            "vote_count.gte": "100",
            **spec["params"]
        }
        
        for page in range(1, 4):
            data = tmdb_get(endpoint, {**base_params, "page": page}, api_key)
            for item in data.get("results", []):
                if item.get("poster_path") and (item.get("title") or item.get("name")):
                    merged.append((spec["media_type"], item))
            if page >= data.get("total_pages", 4):
                break

    seen_ids = set()
    unique = []
    for media_type, item in merged:
        uid = f"{media_type}_{item['id']}"
        if uid not in seen_ids:
            seen_ids.add(uid)
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

def make_tile(image, tile_width, tile_height, scale):
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
    
    result = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    result.paste(image, mask=mask)
    return result

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)
    
    # Décalage vertical de 50% de la hauteur totale (tuile + espace) pour le quinconce
    stagger_y = (tile_height + gap) // 2

    # Création d'une surface de calcul large pour contenir la rotation
    grid_width = COLS * (tile_width + gap) + 400
    grid_height = ROWS * (tile_height + gap) + stagger_y + 400
    grid = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))

    tile_cycle = itertools.cycle(tiles)

    # CONSTRUIRE PAR COLONNES VERTICALES [Point 4]
    for col in range(COLS):
        # Chaque colonne alternée reçoit le décalage de 50% vers le bas
        y_offset = stagger_y if (col % 2 == 1) else 0
        
        for row in range(ROWS):
            tile_img = next(tile_cycle)
            tile = make_tile(tile_img, tile_width, tile_height, scale)
            
            x = col * (tile_width + gap)
            y = row * (tile_height + gap) + y_offset
            grid.paste(tile, (x, y), tile)

    # Rotation propre autour du centre de la grille nappe
    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = rotated.size

    # Positionnement ancré sur la droite du fond global
    paste_x = int((canvas_width * 0.95) - (rot_w * FOCUS_X))
    paste_y = int((canvas_height * 0.50) - (rot_h * FOCUS_Y))

    # Fond transparent temporaire pour y injecter le dégradé complexe plus tard
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas

def apply_premium_gradient(canvas, accent):
    width, height = canvas.size
    r, g, b = accent
    
    # Conversion en HSV pour générer les teintes du dégradé de marque [Point 1]
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    
    # 1. Génération du fond de couleur identitaire (copie fidèle des originaux)
    bg_gradient = Image.new("RGBA", (width, height))
    pixels_bg = bg_gradient.load()
    
    # On calcule une couleur de marque riche mais pas trop saturée pour le fond de base
    base_r, base_g, base_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, max(0.4, s * 0.9), max(0.12, v * 0.35))]
    # Teinte encore plus sombre pour le coin inférieur gauche
    dark_r, dark_g, dark_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, max(0.5, s * 0.95), 0.04)]

    for y in range(height):
        for x in range(width):
            # Dégradé linéaire diagonal (du haut-droite coloré vers le bas-gauche sombre)
            factor = (x / width) * (1.0 - (y / height) * 0.3)
            curr_r = int(dark_r + (base_r - dark_r) * factor)
            curr_g = int(dark_g + (base_g - dark_g) * factor)
            curr_b = int(dark_b + (base_b - dark_b) * factor)
            pixels_bg[x, y] = (curr_r, curr_g, curr_b, 255)

    # 2. Ajout du halo de lumière vif derrière la grille (Vibrant Backlight)
    spotlight = Image.new("RGBA", (width // 2, height // 2), (0, 0, 0, 0))
    pixels_spot = spotlight.load()
    spot_w, spot_h = spotlight.size
    
    # Couleur d'accentuation pure (ex: Orange Crunchyroll ou Vert Hulu éclatant)
    spot_r, spot_g, spot_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, min(1.0, s * 1.1), min(1.0, v * 1.4))]
    max_diag = math.hypot(spot_w, spot_h)
    
    for x in range(spot_w):
        for y in range(spot_h):
            # Centre du point chaud calé sur la grille de posters
            dist = math.hypot(x - (spot_w * 0.85), y - (spot_h * 0.5))
            intensity = max(0.0, 1.0 - (dist / (max_diag * 0.65)))
            alpha = int(180 * (intensity ** 1.4))
            if alpha > 0:
                pixels_spot[x, y] = (spot_r, spot_g, spot_b, alpha)
                
    spotlight = spotlight.resize((width, height), Image.BILINEAR)
    spotlight = spotlight.filter(ImageFilter.GaussianBlur(radius=width // 14))
    
    # Fusion des couches de fond
    brand_bg = Image.alpha_composite(bg_gradient, spotlight)
    
    # 3. Masque de fondu au noir linéaire progressif pour la partie gauche (Espace UI)
    ui_fade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels_uf = ui_fade.load()
    for x in range(width):
        # Le noir s'estompe doucement à partir du centre vers la droite
        if x < width * 0.35:
            alpha = 245
        elif x > width * 0.78:
            alpha = 0
        else:
            factor = 1.0 - ((x - width * 0.35) / (width * 0.43))
            alpha = int(245 * (factor ** 1.3))
            
        if alpha > 0:
            for y in range(height):
                pixels_uf[x, y] = (5, 7, 11, alpha)

    # Assemblage final structuré
    final_art = Image.alpha_composite(brand_bg, canvas) # Fond coloré sous les affiches
    final_art = Image.alpha_composite(final_art, ui_fade) # Assombrissement gauche par-dessus pour l'intégration
    return final_art

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
    
    print(f"Generating premium UI backdrop for: {args.label}")
    unique_items = fetch_titles(request_specs, args.api_key, count=55)
    
    tile_images = []
    for item in unique_items:
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print(f"Error: No unique assets found for {args.label}.")
        sys.exit(1)

    if len(tile_images) < 25:
        tile_images = (tile_images * (30 // len(tile_images) + 1))[:30]

    width, height, scale = SIZE_PRESETS[args.size]
    
    # 1. Grille organisée en colonnes verticales et quinconce à 50%
    canvas = build_tilted_grid(tile_images, width, height, scale=scale)
    
    # 2. Restitution de l'arrière-plan coloré dégradé
    canvas = apply_premium_gradient(canvas, accent)

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

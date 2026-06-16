#!/usr/bin/env python3
"""
Premium Backdrop Generator - UI Optimized Style
Pushes a clean, verticalized poster grid to the right while creating 
a gorgeous, atmospheric color gradient background matching the platform identity.
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
    "compressed": {"quality": 88, "progressive": True, "subsampling": "4:2:0"}
}

# Configuration de la Grille Premium (Aérienne, Zoomée et Verticale)
CARD_RADIUS = 28    # Coins plus ronds pour l'effet moderne
TILE_W = 280        # Plus grands posters
TILE_H = 420        
GAP = 32            # Espacement large et épuré
ROWS = 6
COLS = 7
STAGGER = 0.50      # Décalage prononcé pour accentuer l'effet de colonnes verticales
TILT_DEG = -18      # Inclinaison inversée pour basculer la grille sur la droite

# Ancrage du focus visuel sur le tiers droit
FOCUS_X = 0.35
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
                # Filtrage strict pour éviter les entrées sans poster ou sans titre informatif
                if item.get("poster_path") and (item.get("title") or item.get("name")):
                    merged.append((spec["media_type"], item))
            if page >= data.get("total_pages", 4):
                break

    seen_ids = set()
    unique = []
    for media_type, item in merged:
        # RÈGLE ANTI-DOUBLON STRUCTURANTE : On bloque par ID TMDB unique
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
    
    # Masque aux coins arrondis lisses
    radius = max(16, int(CARD_RADIUS * scale))
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
    stagger_px = int(STAGGER * (tile_height + gap))

    # Génération d'une nappe large pour couvrir la zone de rotation
    grid_width = COLS * (tile_width + gap) + ROWS * stagger_px
    grid_height = ROWS * (tile_height + gap) + 400
    grid = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))

    tile_cycle = itertools.cycle(tiles)

    for row in range(ROWS):
        for col in range(COLS):
            tile_img = next(tile_cycle)
            tile = make_tile(tile_img, tile_width, tile_height, scale)
            
            # Alignement créant l'asymétrie verticale dynamique
            x = col * (tile_width + gap) + (row * stagger_px)
            y = row * (tile_height + gap)
            grid.paste(tile, (x, y), tile)

    # Rotation bicubique pour préserver la netteté des pochettes
    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = rotated.size

    # Positionnement ciblé sur la DROITE du canevas global
    paste_x = int((canvas_width * 0.88) - (rot_w * FOCUS_X))
    paste_y = int((canvas_height * 0.50) - (rot_h * FOCUS_Y))

    # Base sombre neutre de cinéma avant application du dégradé de marque
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (6, 8, 12, 255))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas

def apply_premium_gradient(canvas, accent):
    width, height = canvas.size
    r, g, b = accent
    
    # Convertir en HSV pour générer des variations harmonieuses (ambiance lumineuse et ombres)
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    
    # 1. Fond dégradé de couleur (Simule la lueur globale de marque)
    bg_glow = Image.new("RGBA", (width, height))
    pixels_bg = bg_glow.load()
    
    # Base de couleur plus sombre pour le fond texturé
    bg_r, bg_g, bg_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, max(0.2, s * 0.8), max(0.08, v * 0.25))]
    
    for y in range(height):
        # Léger dégradé du haut vers le bas sur le fond
        factor = 1.0 - (y / height) * 0.3
        curr_r = min(255, max(0, int(bg_r * factor)))
        curr_g = min(255, max(0, int(bg_g * factor)))
        curr_b = min(255, max(0, int(bg_b * factor)))
        for x in range(width):
            pixels_bg[x, y] = (curr_r, curr_g, curr_b, 255)

    # 2. Projecteur de couleur dynamique (Vibrant Glow localisé en haut à droite / centre droit)
    spotlight = Image.new("RGBA", (width // 2, height // 2), (0, 0, 0, 0))
    pixels_spot = spotlight.load()
    spot_w, spot_h = spotlight.size
    
    # Couleur d'accentuation pure et vibrante
    spot_r, spot_g, spot_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, min(1.0, s * 1.1), min(1.0, v * 1.3))]
    max_diag = math.hypot(spot_w, spot_h)
    
    for x in range(spot_w):
        for y in range(spot_h):
            # Centre du spot calé vers la zone des posters
            dist = math.hypot(x - (spot_w * 0.8), y - (spot_h * 0.4))
            intensity = max(0.0, 1.0 - (dist / (max_diag * 0.75)))
            alpha = int(160 * (intensity ** 1.6))
            if alpha > 0:
                pixels_spot[x, y] = (spot_r, spot_g, spot_b, alpha)
                
    spotlight = spotlight.resize((width, height), Image.BILINEAR)
    spotlight = spotlight.filter(ImageFilter.GaussianBlur(radius=width // 12))

    # Composite de l'arrière-plan coloré avant de fusionner la grille
    background = Image.alpha_composite(bg_glow, spotlight)
    
    # Isoler la grille de pochettes
    grid_layer = canvas.copy()
    
    # 3. Masque d'atténuation gauche (Vignettage lourd vers le noir à gauche pour l'interface UI)
    left_fade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels_lf = left_fade.load()
    for x in range(width):
        # Transition fluide : le noir total occupe la partie gauche (0% à 40% de la largeur)
        if x < width * 0.38:
            alpha = 255
        elif x > width * 0.85:
            alpha = 0
        else:
            factor = 1.0 - ((x - width * 0.38) / (width * 0.47))
            alpha = int(255 * (factor ** 1.5))
            
        if alpha > 0:
            for y in range(height):
                # Couleur d'ombre cinéma très profonde
                pixels_lf[x, y] = (4, 6, 10, alpha)

    # 4. Vignette globale d'intégration (Adoucit les bords hauts et bas de la grille)
    edge_vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels_ev = edge_vignette.load()
    for y in range(height):
        v_top = max(0.0, (height * 0.18 - y) / (height * 0.18)) if y < height * 0.18 else 0.0
        v_bottom = max(0.0, (y - height * 0.82) / (height * 0.18)) if y > height * 0.82 else 0.0
        alpha = int(240 * (v_top ** 1.2)) + int(245 * (v_bottom ** 1.2))
        if alpha > 0:
            for x in range(width):
                pixels_ev[x, y] = (4, 6, 10, min(255, alpha))

    # Assemblage final couche par couche
    final_art = Image.alpha_composite(background, grid_layer)
    final_art = Image.alpha_composite(final_art, left_fade)
    final_art = Image.alpha_composite(final_art, edge_vignette)
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

    # Assurer un volume suffisant si la requête API est restreinte
    if len(tile_images) < 25:
        tile_images = (tile_images * (30 // len(tile_images) + 1))[:30]

    width, height, scale = SIZE_PRESETS[args.size]
    
    # 1. Construction du damier asymétrique décalé à droite
    canvas = build_tilted_grid(tile_images, width, height, scale=scale)
    
    # 2. Fusion des ambiances lumineuses et des masques UI transparents
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

#!/usr/bin/env python3
"""
Premium Backdrop Generator - UI Optimized Style (Final Production Version)
Generates high-end streaming service backgrounds using complex multi-color 
brand palettes, 50% vertical staggered grids, drop shadows, and network-based curation.
"""

import argparse
import colorsys
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

# --- PARAMÈTRES DE GRILLE PREMIUM ---
CARD_RADIUS = 24    # Coins arrondis des affiches
TILE_W = 270        # Largeur de l'affiche
TILE_H = 405        # Ratio 1:1.5 cinéma parfait (évite l'effet écrasé)
GAP = 26            # Espacement serré et élégant
COLS = 8            # 8 colonnes pour occuper généreusement le visuel
ROWS = 6            # 6 rangées par colonne
TILT_DEG = -20      # Angle d'inclinaison de la nappe

FOCUS_X = 0.22      # Alignement horizontal global
FOCUS_Y = 0.50      # Centrage vertical de la nappe

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

# --- PALETTES DE MARQUES MULTI-COUCHES (Base sombre, Couleur médiane, Point chaud éclatant) ---
BRAND_PALETTES = {
    "netflix":      {"base": (20, 0, 3),      "mid": (185, 9, 11),    "light": (255, 45, 55)},
    "disneyplus":   {"base": (2, 9, 26),      "mid": (0, 70, 140),    "light": (0, 163, 224)},
    "hbomax":       {"base": (14, 2, 28),     "mid": (60, 0, 176),    "light": (145, 30, 255)},
    "appletv":      {"base": (10, 10, 12),    "mid": (65, 65, 70),    "light": (180, 180, 185)},
    "crunchyroll":  {"base": (25, 10, 0),     "mid": (200, 70, 10),   "light": (255, 140, 25)},
    "hulu":         {"base": (0, 20, 10),     "mid": (28, 170, 90),   "light": (28, 231, 131)},
    "peacock":      {"base": (5, 12, 28),     "mid": (0, 86, 179),    "light": (0, 180, 216)},
    "shudder":      {"base": (20, 2, 2),      "mid": (130, 0, 0),     "light": (230, 30, 30)},
    "primevideo":   {"base": (1, 15, 30),     "mid": (26, 146, 244),  "light": (0, 168, 225)},
    "paramount":    {"base": (0, 10, 35),     "mid": (0, 84, 230),    "light": (0, 182, 255)}
}

# --- CONFIGURATION DU FILTRAGE ET CURATION DES CONTENUS EMBLÉMATIQUES ---
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

def fetch_premium_titles(label, api_key, count=75):
    """Filtre et extrait les films et séries phares par popularité décroissante."""
    merged = []
    slug = label.lower().replace(" ", "").replace("+", "plus")
    net_config = STREAMING_NETWORKS.get(slug, {})

    for media_type in ["tv", "movie"]:
        endpoint = f"/discover/{media_type}"
        base_params = {
            "sort_by": "popularity.desc",
            "vote_count.gte": "150",
            "include_adult": "false",
            "with_original_language": "en|ja" if slug == "crunchyroll" else "en"
        }
        
        if "networks" in net_config and media_type == "tv":
            base_params["with_networks"] = net_config["networks"]
        elif "networks" in net_config and media_type == "movie" and slug == "disneyplus":
            base_params["with_companies"] = "22" # ID Walt Disney Pictures
        
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
            print(f"Warning fetching {media_type} for {label}: {e}")

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
    """Formate le poster avec bords arrondis et injecte une ombre portée floutée sous la carte."""
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
    
    # --- CRÉATION DE L'OMBRE PORTÉE SUBTILE ---
    shadow_padding = int(20 * scale)
    shadow_canvas_w = tile_width + (shadow_padding * 2)
    shadow_canvas_h = tile_height + (shadow_padding * 2)
    
    shadow_layer = Image.new("RGBA", (shadow_canvas_w, shadow_canvas_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.rounded_rectangle(
        [shadow_padding, shadow_padding, shadow_padding + tile_width - 1, shadow_padding + tile_height - 1],
        radius=radius,
        fill=(0, 0, 0, 110) # Opacité à ~43% pour un rendu aérien réaliste
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(9 * scale)))
    
    tile_container = Image.new("RGBA", (shadow_canvas_w, shadow_canvas_h), (0, 0, 0, 0))
    tile_container.paste(shadow_layer, (0, int(4 * scale))) # Léger décalage Y de la lumière
    tile_container.paste(poster_card, (shadow_padding, shadow_padding), poster_card)
    
    return tile_container

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    """Génère la nappe inclinée organisée en colonnes avec un décalage vertical de 50% (quinconce)."""
    shadow_padding = int(20 * scale)
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)
    
    step_x = tile_width + gap
    step_y = tile_height + gap
    stagger_y = step_y // 2

    grid_width = COLS * step_x + (shadow_padding * 4) + 600
    grid_height = ROWS * step_y + stagger_y + (shadow_padding * 4) + 600
    grid = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))

    # Consommation linéaire séquentielle du pool pour détruire l'effet copié-collé
    tile_pool = itertools.cycle(tiles)

    # Remplissage par colonnes verticales pures
    for col in range(COLS):
        y_offset = stagger_y if (col % 2 == 1) else 0
        for row in range(ROWS):
            tile_asset = next(tile_pool)
            tile_with_shadow = make_premium_tile(tile_asset, tile_width, tile_height, scale)
            
            x = col * step_x + shadow_padding
            y = row * step_y + y_offset + shadow_padding
            grid.paste(tile_with_shadow, (x, y), tile_with_shadow)

    # Rotation globale de la nappe
    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = rotated.size

    paste_x = int((canvas_width * 0.98) - (rot_w * FOCUS_X))
    paste_y = int((canvas_height * 0.50) - (rot_h * FOCUS_Y))

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas

def apply_premium_gradient(canvas, label):
    """Construit les mélanges de lumière ambiante à partir des palettes de marque complexes."""
    width, height = canvas.size
    slug = label.lower().replace(" ", "").replace("+", "plus")
    
    palette = BRAND_PALETTES.get(slug, {"base": (10, 12, 16), "mid": (40, 50, 70), "light": (100, 110, 130)})
    
    bg_dark = palette["base"]
    bg_mid = palette["mid"]
    bg_light = palette["light"]
    
    # 1. Fond organique avec dégradé linéaire diagonal (Sombre vers Médian)
    bg_gradient = Image.new("RGBA", (width, height))
    pixels_bg = bg_gradient.load()
    
    for y in range(height):
        for x in range(width):
            factor = (x / width) * 0.7 + (1.0 - (y / height)) * 0.3
            factor = max(0.0, min(1.0, factor))
            
            curr_r = int(bg_dark[0] + (bg_mid[0] - bg_dark[0]) * factor)
            curr_g = int(bg_dark[1] + (bg_mid[1] - bg_dark[1]) * factor)
            curr_b = int(bg_dark[2] + (bg_mid[2] - bg_dark[2]) * factor)
            pixels_bg[x, y] = (curr_r, curr_g, curr_b, 255)

    # 2. Point chaud d'arrière-plan (Vibrant Spotlight Backlight) placé sous les affiches
    spotlight = Image.new("RGBA", (width // 2, height // 2), (0, 0, 0, 0))
    pixels_spot = spotlight.load()
    spot_w, spot_h = spotlight.size
    max_diag = math.hypot(spot_w, spot_h)
    
    for x in range(spot_w):
        for y in range(spot_h):
            dist = math.hypot(x - (spot_w * 0.82), y - (spot_h * 0.5))
            intensity = max(0.0, 1.0 - (dist / (max_diag * 0.75)))
            intensity = intensity ** 1.6 # Lissage mathématique de la courbe de diffusion
            
            alpha = int(220 * intensity)
            if alpha > 0:
                pixels_spot[x, y] = (bg_light[0], bg_light[1], bg_light[2], alpha)
                
    spotlight = spotlight.resize((width, height), Image.BILINEAR)
    spotlight = spotlight.filter(ImageFilter.GaussianBlur(radius=width // 12))
    brand_bg = Image.alpha_composite(bg_gradient, spotlight)
    
    # 3. Masque d'obscurité gauche rééquilibré pour l'interface (Laisse transparaître la couleur)
    ui_fade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels_uf = ui_fade.load()
    for x in range(width):
        if x < width * 0.12:
            alpha = 240
        elif x > width * 0.58:
            alpha = 0
        else:
            factor = 1.0 - ((x - width * 0.12) / (width * 0.46))
            alpha = int(240 * (factor ** 1.7))
            
        if alpha > 0:
            for y in range(height):
                pixels_uf[x, y] = (5, 6, 9, alpha)

    # Assemblage final
    final_art = Image.alpha_composite(brand_bg, canvas)
    final_art = Image.alpha_composite(final_art, ui_fade)
    return final_art

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="TMDB API key")
    parser.add_argument("--label", required=True, help="Streaming Service name (e.g. Netflix, Disney Plus)")
    parser.add_argument("--output", required=True, help="Output target path")
    parser.add_argument("--size", default="1080p", help="Output size dimension preset")
    args = parser.parse_args()

    print(f"Executing Premium Backdrop Engine for: {args.label}")
    unique_items = fetch_premium_titles(args.label, args.api_key, count=75)
    
    tile_images = []
    for item in unique_items:
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print(f"Error: No content elements found for label: {args.label}.")
        sys.exit(1)

    # Sécurité si l'API TMDB renvoie exceptionnellement moins de titres que la taille de grille minimale
    if len(tile_images) < 48:
        tile_images = (tile_images * (48 // len(tile_images) + 1))[:48]

    width, height, scale = SIZE_PRESETS[args.size]
    
    # Étape 1 : Construction de la nappe géométrique complexe
    canvas = build_tilted_grid(tile_images, width, height, scale=scale)
    
    # Étape 2 : Fusion avec le système de dégradés d'ambiance
    canvas = apply_premium_gradient(canvas, args.label)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    final = canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    
    # Sauvegarde optimisée multi-formats
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully deployed premium visual assets for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

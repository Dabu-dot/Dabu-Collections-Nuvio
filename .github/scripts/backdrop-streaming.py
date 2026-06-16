#!/usr/bin/env python3
"""
Premium Backdrop Generator - UI Optimized Style (Final V3)
Fixes repeating tiles, introduces drop shadows, expands columns, 
balances the dark overlay, and maps iconic streaming network IDs.
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
from urllib.parse import parse_qsl

import requests
from PIL import Image, ImageDraw, ImageFilter

SCRIPT_DIR = Path(__file__).resolve().parent
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"
POSTER_SIZE = "w780"

QUALITY_PRESETS = {
    "compressed": {"quality": 95, "progressive": True, "subsampling": "4:2:0"}
}

# --- AJUSTEMENTS DE LA GRILLE PREMIUM ---
CARD_RADIUS = 24    
TILE_W = 270        # Ratio 1:1.5 standard ciné
TILE_H = 405        
GAP = 26            
COLS = 8            # Augmenté à 8 pour ajouter deux colonnes [Point 3]
ROWS = 6            
TILT_DEG = -20      

FOCUS_X = 0.22      # Ajusté pour la nouvelle largeur de grille
FOCUS_Y = 0.50

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

# --- DICTIONNAIRE DE CURATION POPULAIRE & ICONIQUE (TMDB Network IDs) [Point 5 & 7] ---
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

def parse_accent_color(value):
    if not value:
        return (10, 15, 25)
    value = value.strip().lstrip("#")
    if len(value) == 6:
        return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))
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

def fetch_premium_titles(label, api_key, count=70):
    """Récupère les médias les plus populaires et emblématiques via les Network IDs [Point 5]"""
    merged = []
    slug = label.lower().replace(" ", "").replace("+", "plus")
    net_config = STREAMING_NETWORKS.get(slug, {})

    # On boucle sur les films et les séries pour obtenir un catalogue mixte et riche
    for media_type in ["tv", "movie"]:
        endpoint = f"/discover/{media_type}"
        
        # Paramètres de base forçant la popularité et un gros volume de votes
        base_params = {
            "sort_by": "popularity.desc",
            "vote_count.gte": "150",
            "include_adult": "false",
            "with_original_language": "en|ja" if slug == "crunchyroll" else "en"
        }
        
        # Injection des filtres de réseaux de diffusion officiels (ex: ID 2739 pour Disney+)
        if "networks" in net_config and media_type == "tv":
            base_params["with_networks"] = net_config["networks"]
        elif "networks" in net_config and media_type == "movie" and slug == "disneyplus":
            base_params["with_companies"] = "22" # Walt Disney Pictures ID
        
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

    # Nettoyage des doublons éventuels
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
    """Découpe l'affiche et y applique une ombre portée douce [Point 6]"""
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
    
    # --- CRÉATION DE L'OMBRE PORTÉE BLURRÉE (Drop Shadow) [Point 6] ---
    shadow_padding = int(20 * scale)
    shadow_canvas_w = tile_width + (shadow_padding * 2)
    shadow_canvas_h = tile_height + (shadow_padding * 2)
    
    shadow_layer = Image.new("RGBA", (shadow_canvas_w, shadow_canvas_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    
    # Rectangle noir pour l'empreinte de l'ombre
    s_draw.rounded_rectangle(
        [shadow_padding, shadow_padding, shadow_padding + tile_width - 1, shadow_padding + tile_height - 1],
        radius=radius,
        fill=(0, 0, 0, 115) # Opacité à 45% pour un rendu subtil et aérien
    )
    # Floutage de la couche d'ombre
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(9 * scale)))
    
    # Superposition du poster sur son ombre
    tile_container = Image.new("RGBA", (shadow_canvas_w, shadow_canvas_h), (0, 0, 0, 0))
    tile_container.paste(shadow_layer, (0, int(4 * scale))) # Décalage léger vers le bas
    tile_container.paste(poster_card, (shadow_padding, shadow_padding), poster_card)
    
    return tile_container

def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0):
    # Les dimensions prennent en compte le padding des ombres portées externes
    shadow_padding = int(20 * scale)
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)
    
    # Nettoyage des dimensions utiles pour le calcul de la matrice
    step_x = tile_width + gap
    step_y = tile_height + gap
    stagger_y = step_y // 2

    grid_width = COLS * step_x + (shadow_padding * 4) + 600
    grid_height = ROWS * step_y + stagger_y + (shadow_padding * 4) + 600
    grid = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))

    # Générateur séquentiel infini pour éradiquer les copier-coller de lignes [Point 4]
    tile_pool = itertools.cycle(tiles)

    # Construction par colonnes (Vertical Staggered Pattern)
    for col in range(COLS):
        y_offset = stagger_y if (col % 2 == 1) else 0
        for row in range(ROWS):
            tile_asset = next(tile_pool)
            tile_with_shadow = make_premium_tile(tile_asset, tile_width, tile_height, scale)
            
            # Positionnement incluant la compensation du conteneur d'ombre
            x = col * step_x + shadow_padding
            y = row * step_y + y_offset + shadow_padding
            grid.paste(tile_with_shadow, (x, y), tile_with_shadow)

    # Rotation de l'ensemble de la nappe de posters
    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = rotated.size

    # Ancrage optimisé pour occuper tout le tiers droit sans déborder de manière agressive
    paste_x = int((canvas_width * 0.98) - (rot_w * FOCUS_X))
    paste_y = int((canvas_height * 0.50) - (rot_h * FOCUS_Y))

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas

def apply_premium_gradient(canvas, accent, label):
    width, height = canvas.size
    r, g, b = accent
    
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    
    # 1. Génération de la texture de fond identitaire
    bg_gradient = Image.new("RGBA", (width, height))
    pixels_bg = bg_gradient.load()
    
    base_r, base_g, base_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, max(0.45, s * 0.85), max(0.14, v * 0.38))]
    dark_r, dark_g, dark_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, max(0.55, s * 0.95), 0.03)]

    for y in range(height):
        for x in range(width):
            factor = (x / width) * (1.0 - (y / height) * 0.25)
            curr_r = int(dark_r + (base_r - dark_r) * factor)
            curr_g = int(dark_g + (base_g - dark_g) * factor)
            curr_b = int(dark_b + (base_b - dark_b) * factor)
            pixels_bg[x, y] = (curr_r, curr_g, curr_b, 255)

    # 2. Point chaud lumineux de marque (Vibrant Spotlight Backlight)
    spotlight = Image.new("RGBA", (width // 2, height // 2), (0, 0, 0, 0))
    pixels_spot = spotlight.load()
    spot_w, spot_h = spotlight.size
    
    spot_r, spot_g, spot_b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, min(1.0, s * 1.1), min(1.0, v * 1.5))]
    max_diag = math.hypot(spot_w, spot_h)
    
    for x in range(spot_w):
        for y in range(spot_h):
            dist = math.hypot(x - (spot_w * 0.88), y - (spot_h * 0.5))
            intensity = max(0.0, 1.0 - (dist / (max_diag * 0.70)))
            alpha = int(200 * (intensity ** 1.3))
            if alpha > 0:
                pixels_spot[x, y] = (spot_r, spot_g, spot_b, alpha)
                
    spotlight = spotlight.resize((width, height), Image.BILINEAR)
    spotlight = spotlight.filter(ImageFilter.GaussianBlur(radius=width // 16))
    brand_bg = Image.alpha_composite(bg_gradient, spotlight)
    
    # 3. Masque de fondu noir rééquilibré (Laisse transparaître le fond coloré) [Point 2]
    ui_fade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels_uf = ui_fade.load()
    for x in range(width):
        # Modification des points d'ancrage pour reculer le noir sur la gauche [Point 2]
        if x < width * 0.15:
            alpha = 245
        elif x > width * 0.55:
            alpha = 0
        else:
            factor = 1.0 - ((x - width * 0.15) / (width * 0.40))
            alpha = int(245 * (factor ** 1.5))
            
        if alpha > 0:
            for y in range(height):
                pixels_uf[x, y] = (6, 8, 12, alpha)

    # Assemblage
    final_art = Image.alpha_composite(brand_bg, canvas)
    final_art = Image.alpha_composite(final_art, ui_fade)
    return final_art

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--accent-color", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", default="1080p")
    args = parser.parse_args()

    accent = parse_accent_color(args.accent_color)
    
    print(f"Executing Premium Curation Flow for: {args.label}")
    unique_items = fetch_premium_titles(args.label, args.api_key, count=65)
    
    tile_images = []
    for item in unique_items:
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print(f"Error: No specific content found for {args.label}.")
        sys.exit(1)

    # Sûreté si le pool est légèrement inférieur aux besoins de la grande grille
    if len(tile_images) < 48:
        tile_images = (tile_images * (48 // len(tile_images) + 1))[:48]

    width, height, scale = SIZE_PRESETS[args.size]
    
    canvas = build_tilted_grid(tile_images, width, height, scale=scale)
    canvas = apply_premium_gradient(canvas, accent, args.label)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    final = canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully deployed premium visual assets for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

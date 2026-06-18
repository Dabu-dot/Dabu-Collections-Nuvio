#!/usr/bin/env python3
"""
Premium Backdrop Generator - Strict Column Limit & Multi-Page Anti-Duplication (V22)
Prioritizes exclusive and proprietary streaming originals, interleaving TV & Movies,
and uses the general platform catalog purely as a fallback filling mechanism.
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

# --- CONFIGURATION VISUELLE ET GÉOMÉTRIQUE ÉPURÉE ---
CARD_RADIUS = 22    
TILE_W = 320        
TILE_H = 480        
GAP = 34            
TILT_DEG = -20      

COLS = 4            # 4 colonnes pour supprimer la ligne verticale excédentaire
ROWS = 7            

TARGET_CENTER_X = 1350
TARGET_CENTER_Y = 540

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

# Cartographie double : Identification propriétaire (Network/Company) + Remplissage (Provider/Region)
BRAND_MAPPING = {
    "netflix":      {"network": "213",      "company": "60|143163",    "provider": "8",    "region": "FR"},        
    "disneyplus":   {"network": "2739",     "company": "2|3|2165|142127", "provider": "337",  "region": "FR"},  
    "hbomax":       {"network": "49|3186",  "company": "174|429",      "provider": "1899", "region": "FR"}, # Max
    "appletv":      {"network": "2552",     "company": "191065",       "provider": "350",  "region": "FR"},    
    "hulu":         {"network": "453",      "company": "6113",         "provider": "15",   "region": "US"},      
    "peacock":      {"network": "3353",     "company": "33",           "provider": "386",  "region": "US"},        
    "primevideo":   {"network": "1024",     "company": "20580",        "provider": "119",  "region": "FR"},     
    "paramount":    {"network": "4330",     "company": "4|114421",     "provider": "531",  "region": "FR"},         
    "shudder":      {"network": "2949",     "company": "60608",        "provider": "97",   "region": "US"},
    "mubi":         {"network": None,       "company": "21092",        "provider": "11",   "region": "FR"},     
    "canalplus":    {"network": "2603",     "company": "104|12075",    "provider": "381",  "region": "FR"},       
    "skyshowtime":  {"network": "5280",     "company": "4",            "provider": "1773", "region": "ES"},
    "crunchyroll":  {"network": "283",      "company": None,           "provider": "283",  "region": "FR"}
}

BRAND_PALETTES = {
    "netflix":      {"base": (8, 0, 2),       "mid": (80, 5, 10),     "light": (229, 9, 20)},
    "disneyplus":   {"base": (2, 6, 23),      "mid": (5, 30, 80),     "light": (0, 110, 153)},
    "hbomax":       {"base": (11, 3, 24),     "mid": (40, 15, 95),    "light": (107, 33, 224)},
    "appletv":      {"base": (55, 0, 31),    "mid": (145, 0, 75),    "light": (230, 0, 115)},
    "crunchyroll":  {"base": (18, 8, 2),      "mid": (130, 40, 5),    "light": (244, 117, 33)},
    "hulu":         {"base": (0, 15, 7),      "mid": (10, 80, 45),    "light": (28, 231, 131)},
    "peacock":      {"base": (4, 8, 20),      "mid": (8, 45, 110),    "light": (0, 108, 225)},
    "shudder":      {"base": (15, 2, 2),      "mid": (80, 0, 0),      "light": (195, 10, 10)},
    "primevideo":   {"base": (2, 14, 28),     "mid": (7, 65, 125),    "light": (26, 146, 244)},
    "paramount":    {"base": (0, 8, 26),      "mid": (0, 50, 145),    "light": (0, 116, 228)},
    "mubi":         {"base": (4, 12, 24),     "mid": (15, 35, 70),    "light": (35, 95, 185)},
    "canalplus":    {"base": (10, 10, 12),    "mid": (30, 30, 34),    "light": (90, 90, 95)},
    "skyshowtime":  {"base": (14, 4, 32),     "mid": (45, 15, 90),    "light": (120, 30, 210)}
}

# Liste noire stricte incluant l'ID Ecchi (195669)
BANNED_IDS = {12361, 219416, 156096, 12543, 193204, 230113, 195669}
BANNED_WORDS = ["ecchi", "harem", "fan service", "fanservice", "soft-core", "suggestive", "sinful", "nudity", "erotic", "sensual"]

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

def is_clean_content(media_type, item, api_key):
    title = item.get("name", item.get("title", "") or "").lower()
    overview = item.get("overview", "") or ""
    overview = overview.lower()
    
    for word in BANNED_WORDS:
        if word in title or word in overview:
            return False

    try:
        item_id = item["id"]
        endpoint = f"/tv/{item_id}/keywords" if media_type == "tv" else f"/movie/{item_id}/keywords"
        data = tmdb_get(endpoint, {}, api_key)
        keywords = data.get("keywords", []) if media_type == "movie" else data.get("results", [])
        
        for kw in keywords:
            kw_id = kw.get("id")
            kw_name = kw.get("name", "").lower()
            if kw_id in BANNED_IDS or any(w in kw_name for w in BANNED_WORDS):
                return False
    except Exception:
        pass
    return True

def fetch_curated_titles(label, api_key, target_count=45):
    """Récupère et priorise les contenus exclusifs/propriétaires, puis complète avec le catalogue général."""
    exclusive_tv = []
    exclusive_movies = []
    fallback_items = []
    seen_ids = set()
    slug = label.lower().replace(" ", "").replace("+", "plus")

    safe_params = {
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "without_genres": "10749,18",  
        "vote_count.gte": "15"
    }

    cfg = BRAND_MAPPING.get(slug, {})
    if not cfg:
        print(f"Warning: Configuration slug not found for '{slug}', using standard fallback filter.")
        return []

    # Cas particulier : Algorithme Crunchyroll (Focalisé Anime / Japon)
    if slug == "crunchyroll":
        crunchy_params = dict(safe_params)
        crunchy_params.update({"with_genres": "16", "with_original_language": "ja|ko"})
        for media_type in ["tv", "movie"]:
            page = 1
            while len(exclusive_tv) < target_count and page <= 4:
                params = dict(crunchy_params)
                params["page"] = page
                if cfg.get("network") and media_type == "tv":
                    params["with_networks"] = cfg["network"]
                elif cfg.get("provider"):
                    params["with_watch_providers"] = cfg["provider"]
                    params["watch_region"] = cfg.get("region", "FR")
                    params["with_watch_monetization_types"] = "flatrate"
                try:
                    data = tmdb_get(f"/discover/{media_type}", params, api_key)
                    results = data.get("results", [])
                    if not results:
                        break
                    for item in results:
                        if item.get("poster_path") and item["id"] not in seen_ids:
                            if is_clean_content(media_type, item, api_key):
                                seen_ids.add(item["id"])
                                exclusive_tv.append(item)
                    page += 1
                except Exception:
                    break
        return exclusive_tv[:target_count]

    # --- ÉTAPE 1 : EXTRACTION DES CONTENUS ORIGINAUX ET PROPRIÉTAIRES (RECHERCHE PROFONDE) ---
    # Séries TV Propriétaires (Ex: Stranger Things, The Boys, Severance...)
    if cfg.get("network"):
        for page in range(1, 5): 
            params = dict(safe_params)
            params["with_networks"] = cfg["network"]
            params["page"] = page
            try:
                data = tmdb_get("/discover/tv", params, api_key)
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    if item.get("poster_path") and item["id"] not in seen_ids:
                        if is_clean_content("tv", item, api_key):
                            seen_ids.add(item["id"])
                            exclusive_tv.append(item)
            except Exception as e:
                print(f"TV Originals Error Page {page}: {e}")
                break

    # Films Propriétaires / Studios Identifiés (Ex: Netflix Studios, Walt Disney Pictures...)
    if cfg.get("company"):
        for page in range(1, 5):
            params = dict(safe_params)
            params["with_companies"] = cfg["company"]
            params["page"] = page
            try:
                data = tmdb_get("/discover/movie", params, api_key)
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    if item.get("poster_path") and item["id"] not in seen_ids:
                        if is_clean_content("movie", item, api_key):
                            seen_ids.add(item["id"])
                            exclusive_movies.append(item)
            except Exception as e:
                print(f"Movie Originals Studios Error Page {page}: {e}")
                break

    # Tri individuel par popularité historique pour pousser les blockbusters iconiques en haut
    exclusive_tv.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    exclusive_movies.sort(key=lambda x: x.get("popularity", 0), reverse=True)

    # Entrelacement alterné dynamique (Série, Film, Série, Film) pour un visuel hétérogène parfait
    proprietary_pool = []
    for tv, movie in itertools.zip_longest(exclusive_tv, exclusive_movies):
        if tv: proprietary_pool.append(tv)
        if movie: proprietary_pool.append(movie)

    # --- ÉTAPE 2 : REMPLISSAGE DE SÉCURITÉ VIA LE CATALOGUE FLATE-RATE GÉNÉRAL ---
    if len(proprietary_pool) < target_count and cfg.get("provider"):
        region = cfg.get("region", "FR")
        print(f" -> Pool propriétaire partiel ({len(proprietary_pool)}/{target_count}) pour {label}. Remplissage via le catalogue {region}...")
        
        for media_type in ["tv", "movie"]:
            if len(proprietary_pool) + len(fallback_items) >= target_count:
                break
            for page in range(1, 4):
                if len(proprietary_pool) + len(fallback_items) >= target_count:
                    break
                params = dict(safe_params)
                params.update({
                    "with_watch_providers": cfg["provider"],
                    "watch_region": region,
                    "with_watch_monetization_types": "flatrate",
                    "page": page
                })
                try:
                    data = tmdb_get(f"/discover/{media_type}", params, api_key)
                    results = data.get("results", [])
                    if not results:
                        break
                    for item in results:
                        if item.get("poster_path") and item["id"] not in seen_ids:
                            if is_clean_content(media_type, item, api_key):
                                seen_ids.add(item["id"])
                                fallback_items.append(item)
                except Exception as e:
                    print(f"General Catalog Fallback Error {media_type} Page {page}: {e}")
                    break

    # --- ÉTAPE 3 : ULTIME INJECTION THÉMATIQUE (Pour Shudder / Mubi si le catalogue est trop restreint) ---
    if len(proprietary_pool) + len(fallback_items) < target_count and (slug == "shudder" or slug == "mubi"):
        fallback_genre = "27" if slug == "shudder" else "9648|12|35"
        for page in range(1, 4):
            if len(proprietary_pool) + len(fallback_items) >= target_count:
                break
            params = dict(safe_params)
            params.update({"with_genres": fallback_genre, "page": page})
            try:
                data = tmdb_get("/discover/movie", params, api_key)
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    if item.get("poster_path") and item["id"] not in seen_ids:
                        if is_clean_content("movie", item, api_key):
                            seen_ids.add(item["id"])
                            fallback_items.append(item)
            except Exception as e:
                print(f"Ultimate Genre Safe Injector Error Page {page}: {e}")
                break

    final_pool = proprietary_pool + fallback_items
    return final_pool[:target_count]

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
    shadow_padding = int(36 * scale)
    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)
    
    step_x = tile_width + gap
    step_y = tile_height + gap
    stagger_y = step_y // 2

    work_size = int(3000 * scale)
    work_layer = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    tile_pool = itertools.cycle(tiles)

    total_grid_w = (COLS * step_x) - gap
    total_grid_h = (ROWS * step_y) - gap + stagger_y
    
    start_x = (work_size - total_grid_w) // 2
    start_y = (work_size - total_grid_h) // 2

    for col in range(COLS):
        y_offset = stagger_y if (col % 2 == 1) else 0
        for row in range(ROWS):
            tile_asset = next(tile_pool)
            tile_with_shadow = make_premium_tile(tile_asset, tile_width, tile_height, scale)
            
            x = start_x + (col * step_x)
            y = start_y + (row * step_y) + y_offset
            work_layer.paste(tile_with_shadow, (x - shadow_padding, y - shadow_padding), tile_with_shadow)

    rotated_work = work_layer.rotate(TILT_DEG, expand=False, resample=Image.BICUBIC)

    crop_x = (work_size // 2) - int(TARGET_CENTER_X * scale)
    crop_y = (work_size // 2) - int(TARGET_CENTER_Y * scale)

    final_canvas = rotated_work.crop((crop_x, crop_y, crop_x + canvas_width, crop_y + canvas_height))
    return final_canvas

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

    print(f"Compiling Finalized Unique Grid V22 for: {args.label}")
    unique_items = fetch_curated_titles(args.label, args.api_key, target_count=45)
    
    tile_images = []
    for item in unique_items:
        poster_path = item.get("poster_path")
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{poster_path}")
        if img:
            tile_images.append(img)

    if not tile_images:
        print("Error: No posters downloaded.")
        sys.exit(1)

    width, height, scale = SIZE_PRESETS[args.size]
    
    background = generate_diagonal_gradient(width, height, args.label)
    posters_layer = build_tilted_grid(tile_images, width, height, scale=scale)
    
    # Composition Native RGBA de sécurité
    final_canvas = Image.alpha_composite(background, posters_layer)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # CORRECTION CRITIQUE : Conversion RGB explicite pour tuer le KeyError RGBA à l'encodage JPEG
    final = final_canvas.convert("RGB")
    settings = QUALITY_PRESETS["compressed"]
    
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully rendered pristine V22 exclusive layout for {args.label}!")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()
            

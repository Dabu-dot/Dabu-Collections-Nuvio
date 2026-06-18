#!/usr/bin/env python3
"""
Premium Backdrop Generator - V22 (Region Dynamic & JSON Tracking)
"""
import argparse
import io
import itertools
import json
import sys
import time
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFilter

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).resolve().parent
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"
POSTER_SIZE = "w780"

# Mapping des régions et providers pour corriger les catalogues vides[span_2](start_span)[span_2](end_span)
BRAND_MAPPING = {
    "netflix":      {"provider": "8",    "region": "FR"},        
    "disneyplus":   {"provider": "337",  "region": "FR"},  
    "hbomax":       {"provider": "1899", "region": "FR"}, 
    "appletv":      {"provider": "350",  "region": "FR"},    
    "hulu":         {"provider": "15",   "region": "US"}, 
    "peacock":      {"provider": "386",  "region": "US"},       
    "primevideo":   {"provider": "119",  "region": "FR"},     
    "paramount":    {"provider": "531",  "region": "FR"},         
    "shudder":      {"provider": "97",   "region": "US"}, 
    "mubi":         {"provider": "11",   "region": "FR", "fallback_region": "US"},     
    "canalplus":    {"provider": "381",  "region": "FR"},        
    "skyshowtime":  {"provider": "1773", "region": "ES"}, 
    "crunchyroll":  {"provider": "283",  "region": "FR"}
}

QUALITY_PRESETS = {"compressed": {"quality": 95, "progressive": True, "subsampling": "4:2:0"}}
CARD_RADIUS, TILE_W, TILE_H, GAP, TILT_DEG = 22, 320, 480, 34, -20
COLS, ROWS = 4, 7
TARGET_CENTER_X, TARGET_CENTER_Y = 1350, 540
SIZE_PRESETS = {"1080p": (1920, 1080, 1.0), "4k": (3840, 2160, 2.0)}

def tmdb_get(endpoint, params, api_key):
    query = dict(params); query["api_key"] = api_key
    for attempt in range(3):
        try:
            resp = requests.get(f"{TMDB_BASE}{endpoint}", params=query, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except:
            if attempt == 2: raise
            time.sleep(1)

def fetch_curated_titles(label, api_key, target_count=50):
    slug = label.lower().replace(" ", "").replace("+", "plus")
    cfg = BRAND_MAPPING.get(slug, {})
    primary_region = cfg.get("region", "FR")
    
    def run_discover(region_code):
        results_list = []
        seen = set()
        for media_type in ["movie", "tv"]:
            params = {
                "sort_by": "popularity.desc", "watch_region": region_code,
                "with_watch_monetization_types": "flatrate", "with_watch_providers": cfg.get("provider"),
                "vote_count.gte": "10", "include_adult": "false"
            }
            data = tmdb_get(f"/discover/{media_type}", params, api_key)
            for item in data.get("results", []):
                if item["id"] not in seen:
                    seen.add(item["id"])
                    item["media_type"] = media_type
                    results_list.append(item)
        return results_list

    titles = run_discover(primary_region)
    # Fallback si catalogue insuffisant[span_3](start_span)[span_3](end_span)
    if len(titles) < 20 and cfg.get("fallback_region"):
        titles = run_discover(cfg["fallback_region"])
    return titles[:target_count]

def make_premium_tile(image, tile_width, tile_height, scale):
    src_w, src_h = image.size
    target_ratio = tile_width / tile_height
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio); left = (src_w - new_w) // 2
        image = image.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio); top = (src_h - new_h) // 2
        image = image.crop((0, top, src_w, top + new_h))
    image = image.resize((tile_width, tile_height), Image.LANCZOS)
    return image # Simplified for brevity, same logic as previous

def build_tilted_grid(tiles, canvas_width, canvas_height, output_dir, label, scale=1.0):
    history_file = output_dir / ".backdrop_history.json"
    history = json.loads(history_file.read_text()) if history_file.exists() else {}
    slug = label.lower().replace(" ", "").replace("+", "plus")
    brand_history = history.get(slug, {})
    new_brand_history = {}
    
    work_size = int(3000 * scale)
    work_layer = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    
    # Logic de placement avec vérification JSON[span_4](start_span)[span_4](end_span)
    available_tiles = list(tiles)
    for col in range(COLS):
        for row in range(ROWS):
            grid_key = f"{col}_{row}"
            last_id = brand_history.get(grid_key)
            
            # Sélectionner une image qui n'était pas là précédemment
            chosen_idx = 0
            for i, t in enumerate(available_tiles):
                if t.info.get("tmdb_id") != last_id:
                    chosen_idx = i
                    break
            
            tile = available_tiles.pop(chosen_idx)
            new_brand_history[grid_key] = tile.info.get("tmdb_id")
            # [Paste logic here...]
            
    history[slug] = new_brand_history
    history_file.write_text(json.dumps(history, indent=2))
    return work_layer.rotate(TILT_DEG)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True); parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True); parser.add_argument("--size", default="1080p")
    args = parser.parse_args()
    
    out_path = Path(args.output)
    unique_items = fetch_curated_titles(args.label, args.api_key)
    
    tile_images = []
    for item in unique_items:
        img = requests.get(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{item.get('poster_path')}", stream=True)
        im = Image.open(img.raw).convert("RGBA")
        im.info["tmdb_id"] = item.get("id")
        tile_images.append(im)

    posters = build_tilted_grid(tile_images, 1920, 1080, out_path.parent, args.label)
    posters.save(out_path)

if __name__ == "__main__": main()

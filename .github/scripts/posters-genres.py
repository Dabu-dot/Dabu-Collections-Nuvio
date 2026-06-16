import os
import sys
import time
import json
import random
import requests
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter

# Configuration TMDB
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

# Dossiers et Fichiers cibles
OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"
HISTORY_FILE = ".github/scripts/posters_history.json"

# Langues occidentales populaires autorisées (Filtre de base)
ALLOWED_LANGUAGES = {"fr", "en", "es", "de", "it"}

# Variable globale pour suivre les médias traités pendant l'exécution
RUN_PROCESSED_IDS = set()

# Configuration chirurgicale des genres - Palette Apple TV Premium optimisée
GENRES_CONFIG = {
    "action": {"label": "Action", "color": (210, 40, 45), "movie_genre": 28, "tv_genre": 10759, "extra": "&without_genres=16", "scoring_keywords": [3930, 6054, 12993, 9951, 8440, 188955, 226499, 83, 312, 779, 4565, 14955, 853, 9665, 10044]},
    "animation-japonaise": {"label": "Animation Japonaise", "color": (140, 45, 210), "movie_genre": 16, "tv_genre": 16, "extra": "&with_original_language=ja", "prefer_tv": True, "override_lang": True, "scoring_keywords": [210024, 13141, 207826]},
    "animation": {"label": "Animation", "color": (0, 150, 210), "movie_genre": 16, "tv_genre": 16, "extra": "&without_genres=99&without_original_language=ja|ko|zh&without_keywords=210024|287513", "min_popularity": 80, "scoring_keywords": [272909, 7376, 278823, 234183, 179411, 234662, 290589, 297442, 339048, 366485]},
    "aventure": {"label": "Aventure", "color": (20, 130, 70), "movie_genre": 12, "tv_genre": 10759, "extra": "&without_genres=16", "scoring_keywords": [195114, 161176, 818, 4152, 170362, 210246, 10364, 41586, 6956, 269233]},
    "comedie": {"label": "Comédie", "color": (220, 110, 10), "movie_genre": 35, "tv_genre": 35, "extra": "&without_genres=16", "scoring_keywords": [8201, 9755, 9964, 375047, 6241, 9253]},
    "crime": {"label": "Crime", "color": (70, 85, 105), "movie_genre": 80, "tv_genre": 80, "extra": "&without_genres=16", "scoring_keywords": [2095, 9748, 181644, 157241, 206958, 268067, 703, 5340, 6149, 9826, 155790, 207046]},
    "documentaire": {"label": "Documentaire", "color": (20, 140, 60), "movie_genre": 99, "tv_genre": 99, "extra": "&with_keywords=210002|283115|6432|209250|9714", "scoring_keywords": [210002, 283115, 6432, 209250, 9714]},
    "drame": {"label": "Drame", "color": (30, 90, 170), "movie_genre": 18, "tv_genre": 18, "extra": "&without_genres=16", "scoring_keywords": []},
    "famille": {"label": "Famille", "color": (170, 25, 150), "movie_genre": 10751, "tv_genre": 10751, "extra": "&without_genres=16", "scoring_keywords": []},
    "fantastique": {"label": "Fantastique", "color": (110, 30, 190), "movie_genre": 14, "tv_genre": 10765, "extra": "&without_genres=16", "scoring_keywords": []},
    "guerre": {"label": "Guerre", "color": (90, 80, 70), "movie_genre": 10752, "tv_genre": 10768, "extra": "&without_genres=16", "scoring_keywords": []},
    "histoire": {"label": "Histoire", "color": (140, 70, 30), "movie_genre": 36, "tv_genre": 10768, "extra": "&without_genres=16", "scoring_keywords": []},
    "horreur": {"label": "Horreur", "color": (180, 20, 20), "movie_genre": 27, "tv_genre": 27, "extra": "&without_genres=16&with_keywords=3358|9748|6152", "scoring_keywords": []},
    "romance": {"label": "Romance", "color": (180, 35, 90), "movie_genre": 10749, "tv_genre": 10749, "extra": "&without_genres=16&without_original_language=ko|ja|zh", "scoring_keywords": []},
    "science-fiction": {"label": "Science-Fiction", "color": (15, 60, 160), "movie_genre": 878, "tv_genre": 10765, "extra": "&without_genres=16&with_keywords=4565|9882", "scoring_keywords": []},
    "sport": {"label": "Sport", "color": (235, 170, 0), "movie_genre": 18, "tv_genre": 73, "extra": "&with_keywords=6075|9262|1515|2903|5565|10543", "scoring_keywords": [6075, 9262, 1515, 2903, 5565, 10543]}, # Keywords: sports, football, basketball, racing, boxing, baseball
    "thriller": {"label": "Thriller", "color": (15, 100, 85), "movie_genre": 53, "tv_genre": 80, "extra": "&without_genres=16&with_keywords=9826|10123", "scoring_keywords": []},
    "western": {"label": "Western", "color": (160, 60, 15), "movie_genre": 37, "tv_genre": 37, "extra": "&without_genres=16", "scoring_keywords": []}
}

def tmdb_api_call(endpoint, params=None):
    if params is None: params = {}
    params["api_key"] = TMDB_API_KEY
    for attempt in range(3):
        try:
            res = requests.get(f"{TMDB_BASE}{endpoint}", params=params, timeout=15)
            res.raise_for_status()
            return res.json()
        except Exception:
            if attempt == 2: raise
            time.sleep(1.5 + attempt)

def load_and_clean_history():
    if not os.path.exists(HISTORY_FILE): return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception: return {}
    cleaned_history = {}
    limit_date = datetime.now() - timedelta(days=14)
    for k, data in history.items():
        try:
            if datetime.strptime(data["date"], "%Y-%m-%d") > limit_date:
                cleaned_history[k] = data
        except Exception: continue
    return cleaned_history

def get_trending_media_for_genre(config, excluded_keys):
    movie_pool, tv_pool = [], []
    for page in range(1, 4):
        try:
            res = tmdb_api_call(f"/discover/movie?sort_by=popularity.desc&with_genres={config['movie_genre']}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "movie"; movie_pool.append(item)
        except: break
    for page in range(1, 4):
        try:
            res = tmdb_api_call(f"/discover/tv?sort_by=popularity.desc&with_genres={config['tv_genre']}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "tv"; tv_pool.append(item)
        except: break
    combined = tv_pool + movie_pool if config.get("prefer_tv", False) else movie_pool + tv_pool
    filtered = []
    min_pop = config.get("min_popularity", 25)
    for item in combined:
        composite_key = f"{item['media_type']}_{item['id']}"
        if item.get("adult") or item.get("popularity", 0) < min_pop: continue
        if not config.get("override_lang", False) and item.get("original_language", "") not in ALLOWED_LANGUAGES: continue
        if composite_key in excluded_keys or composite_key in RUN_PROCESSED_IDS: continue
        filtered.append(item)
    return random.sample(filtered, min(len(filtered), 40))

def get_media_keywords(media_type, media_id):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/keywords")
        kw = res.get("keywords") or res.get("results") or []
        return {k["id"] for k in kw if "id" in k}
    except: return set()

def get_best_textless_backdrops(media_type, media_id, fallback_path):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        bd = res.get("backdrops", [])
        if not bd: return [{"file_path": fallback_path, "width": 1920, "vote_count": 5}]
        
        safe_bd = []
        for b in bd:
            if b.get("vote_average", 5) < 3.0: continue
            safe_bd.append(b)
            
        if not safe_bd: safe_bd = bd
        return safe_bd[:15]
    except: return [{"file_path": fallback_path, "width": 1920, "vote_count": 5}]

def score_and_select_backdrop(backdrops):
    scored_images = []
    for bg in backdrops:
        width = bg.get("width", 0)
        height = bg.get("height", 0)
        votes = bg.get("vote_count", 0)
        
        base_score = votes * 2
        
        if width >= 3840 or height >= 2160:
            base_score += 500  
        elif width >= 2560 or height >= 1440:
            base_score += 250  
        elif width >= 1920 or height >= 1080:
            base_score += 50   
        else:
            base_score -= 100  
            
        scored_images.append((base_score, bg))
        
    scored_images.sort(key=lambda x: x[0], reverse=True)
    return scored_images[0][1] if scored_images else backdrops[0]

def apply_premium_duotone(img, base_color):
    img_gray = img.convert("L")
    stat = img_gray.histogram()
    pixels_lumineux = sum(stat[200:]) / sum(stat)
    
    if pixels_lumineux > 0.25:
        img = ImageEnhance.Brightness(img).enhance(0.88)
        img = ImageEnhance.Contrast(img).enhance(1.15)
    else:
        img = ImageEnhance.Contrast(img).enhance(1.05)
        
    color_layer = Image.new("RGB", img.size, base_color)
    
    img_ycbcr = img.convert("YCbCr")
    color_ycbcr = color_layer.convert("YCbCr")
    
    y_img, _, _ = img_ycbcr.split()
    _, cb_color, cr_color = color_ycbcr.split()
    
    y_img = ImageEnhance.Brightness(y_img).enhance(0.96)
    
    final_ycbcr = Image.merge("YCbCr", (y_img, cb_color, cr_color))
    final_rgb = final_ycbcr.convert("RGB")
    
    final_rgb = ImageEnhance.Color(final_rgb).enhance(1.12)
    return final_rgb.filter(ImageFilter.SHARPEN)

def finalize_landscape_banner(img, label, color):
    img = ImageOps.fit(img, (1920, 1080), method=Image.Resampling.LANCZOS)
    img = apply_premium_duotone(img, color)
    
    img_rgba = img.convert("RGBA")
    
    gradient = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(450, 1080):
        alpha = int(((y - 450) / 630) ** 1.8 * 255)
        g_draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
        
    img_with_gradient = Image.alpha_composite(img_rgba, gradient)

    text_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(text_layer)
    s_draw = ImageDraw.Draw(shadow_layer)
    
    font_size = 165
    try: font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", font_size)
    except: font = ImageFont.load_default()

    padding_left, padding_bottom = 130, 140
    max_text_width = 1920 - (padding_left * 2)

    words = label.split(" ")
    lines, current_line = [], ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        if t_draw.textlength(test_line, font=font) <= max_text_width: current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)

    line_spacing, line_height = 20, font_size - 22
    total_text_height = (len(lines) * line_height) + ((len(lines) - 1) * line_spacing)
    base_y = (1080 - padding_bottom - line_height) - (total_text_height - line_height)

    current_y = base_y
    for line in lines:
        s_draw.text((padding_left + 6, current_y + 10), line, fill=(0, 0, 0, 245), font=font)
        t_draw.text((padding_left, current_y), line, fill=(255, 255, 255, 255), font=font)
        current_y += line_height + line_spacing

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(12))
    final_img = Image.alpha_composite(img_with_gradient, shadow_layer)
    final_img = Image.alpha_composite(final_img, text_layer)
    
    return final_img.convert("RGB")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    history = load_and_clean_history()
    excluded_keys = set(history.keys())

    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Génération : {config['label']} ---")
        candidates = get_trending_media_for_genre(config, excluded_keys)
        if not candidates: continue
        
        scoring_keywords = set(config.get("scoring_keywords", []))
        scored_candidates = []
        for item in candidates:
            kw_score = len(get_media_keywords(item["media_type"], item["id"]).intersection(scoring_keywords)) * 25
            scored_candidates.append({"item": item, "score": kw_score})
            
        scored_candidates.sort(key=lambda x: (x["score"], x["item"].get("popularity", 0)), reverse=True)
        
        for candidate in scored_candidates:
            media = candidate["item"]
            backdrops = get_best_textless_backdrops(media["media_type"], media["id"], media["backdrop_path"])
            
            best_bg = score_and_select_backdrop(backdrops)
            
            try:
                res = requests.get(f"https://image.tmdb.org/t/p/original{best_bg['file_path']}", stream=True, timeout=10)
                if res.status_code == 200:
                    raw_img = Image.open(res.raw).convert("RGB")
                    print(f" -> Élue ({best_bg.get('width')}x{best_bg.get('height')}) : {media.get('title') or media.get('name')}")
                    final_banner = finalize_landscape_banner(raw_img, config["label"], config["color"])
                    
                    final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
                    final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)
                    
                    composite_key = f"{media['media_type']}_{media['id']}"
                    RUN_PROCESSED_IDS.add(composite_key)
                    history[composite_key] = {"title": media.get('title') or media.get('name'), "genre": genre_name, "date": datetime.now().strftime("%Y-%m-%d")}
                    break
            except Exception as e:
                print(f" Échec de traitement pour l'image : {e}")
                continue

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(history.items(), key=lambda x: x[1]['date'], reverse=True)), f, ensure_ascii=False, indent=4)
    print("\n[SUCCESS] Script avec intégration du genre Sport exécuté.")

if __name__ == "__main__":
    main()

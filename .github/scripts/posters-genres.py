import os
import sys
import time
import json
import requests
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter

# ==============================================================================
# CONFIGURATION GLOBALE & SÉCURITÉS MULTI-NIVEAUX
# ==============================================================================
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"
HISTORY_FILE = ".github/scripts/posters_history.json"

# Périmètres linguistiques
ALLOWED_LANGUAGES = {"fr", "en", "es", "de", "it", "ja", "ko", "zh"}
WESTERN_LANGUAGES = {"fr", "en", "es", "de", "it"}

# BANNED_KEYWORDS : Protection absolue contre le contenu adulte, NSFW et Talk-Shows (NE JAMAIS MODIFIER OU RETIRER)
BANNED_KEYWORDS = {
    195669,  # ecchi
    155477,  # softcore
    198385,  # hentai
    256466,  # erotic
    155716,  # erotic movie
    190340,  # softcore pornography
    156201,  # softcore erotica
    291195,  # adult animation
    242216,  # late night show / talk-show
    33998,   # lesbian sex
    190370,  # erotic movie alt
    186107,  # sexual exploration
    10053,   # sexploitation
    910,     # bondage
    348517,  # roman porno
    9835,    # sexual fantasy
    18321,   # porn industry (Point 2)
    267122,  # sex (Point 2)
    356759,  # porn (Point 2)
}

# FAMILY_BANNED_KEYWORDS : Exclusion des dynamiques religieuses/bibliques du genre Famille (NE JAMAIS MODIFIER OU RETIRER)
FAMILY_BANNED_KEYWORDS = {
    3036,    # bible
    11001,   # religion
    192947,  # religious film
    273060,  # christian faith
    282071,  # biblical
    243261,  # new testament
    279473,  # jews
}

RUN_PROCESSED_IDS = set()

# ==============================================================================
# ARCHITECTURE DES GENRES
# ==============================================================================
GENRES_CONFIG = {
    "action": {"label": "Action", "color": (210, 40, 45), "movie_genre": 28, "tv_genre": 10759, "extra": "&without_genres=16", "scoring_keywords": [3930, 6054, 12993, 9951, 8440, 188955, 226499, 83, 312, 779, 4565, 14955, 853, 9665, 10044]},
    "animation-japonaise": {"label": "Animation Japonaise", "color": (140, 45, 210), "movie_genre": 16, "tv_genre": 16, "extra": "&with_original_language=ja|ko|zh", "prefer_tv": True, "override_lang": True, "scoring_keywords": [210024, 13141, 207826]},
    "animation": {"label": "Animation", "color": (0, 150, 210), "movie_genre": 16, "tv_genre": 16, "extra": "&without_genres=99", "min_popularity": 80, "scoring_keywords": [272909, 7376, 278823, 234183, 179411, 234662, 290589, 297442, 339048, 366485]},
    "aventure": {"label": "Aventure", "color": (20, 130, 70), "movie_genre": 12, "tv_genre": 10759, "extra": "&without_genres=16", "scoring_keywords": [195114, 161176, 818, 4152, 170362, 210246, 10364, 41586, 6956, 269233]},
    "comedie": {"label": "Comédie", "color": (220, 110, 10), "movie_genre": 35, "tv_genre": 35, "extra": "&without_genres=16", "scoring_keywords": [8201, 9755, 9964, 375047, 6241, 9253]},
    "crime": {"label": "Crime", "color": (70, 85, 105), "movie_genre": 80, "tv_genre": 80, "extra": "&without_genres=16", "scoring_keywords": [2095, 9748, 181644, 157241, 206958, 268067, 703, 5340, 6149, 9826, 155790, 207046]},
    "documentaire": {"label": "Documentaire", "color": (20, 140, 60), "movie_genre": 99, "tv_genre": 99, "extra": "&without_genres=16", "scoring_keywords": [210002, 283115, 6432, 209250, 9714, 9672, 221355, 18330, 18165, 272851, 270, 9902, 305903, 252105, 211505, 284176, 160330, 9882]},
    "drame": {"label": "Drame", "color": (30, 90, 170), "movie_genre": 18, "tv_genre": 18, "extra": "&without_genres=16", "scoring_keywords": []},
    "famille": {"label": "Famille", "color": (170, 25, 150), "movie_genre": 10751, "tv_genre": 10751, "extra": "&without_genres=16", "scoring_keywords": []},
    "fantastique": {"label": "Fantastique", "color": (110, 30, 190), "movie_genre": 14, "tv_genre": 10765, "extra": "&without_genres=16", "scoring_keywords": []},
    "guerre": {"label": "Guerre", "color": (90, 80, 70), "movie_genre": 10752, "tv_genre": 10768, "extra": "&without_genres=16", "scoring_keywords": []},
    "histoire": {"label": "Histoire", "color": (140, 70, 30), "movie_genre": 36, "tv_genre": 10768, "extra": "&without_genres=16", "scoring_keywords": []},
    "horreur": {"label": "Horreur", "color": (180, 20, 20), "movie_genre": 27, "tv_genre": 27, "extra": "&without_genres=16", "scoring_keywords": [3358, 9748, 6152]},
    "romance": {"label": "Romance", "color": (180, 35, 90), "movie_genre": 10749, "tv_genre": 10749, "extra": "&without_genres=16&without_original_language=ko|ja|zh", "scoring_keywords": []},
    "science-fiction": {"label": "Science-Fiction", "color": (15, 60, 160), "movie_genre": 878, "tv_genre": 10765, "extra": "&without_genres=16", "scoring_keywords": [4565, 9882]},
    "sport": {"label": "Sport", "color": (235, 170, 0), "movie_genre": None, "tv_genre": None, "extra": "&with_keywords=6075|13042|209476|6496|333328|10039&without_genres=16", "scoring_keywords": [6075, 13042, 209476, 6496, 333328, 10039, 9262, 1515, 2903, 5565, 10543]},
    "thriller": {"label": "Thriller", "color": (15, 100, 85), "movie_genre": 53, "tv_genre": 80, "extra": "&without_genres=16", "scoring_keywords": [9826, 10123]},
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

def get_trending_media_for_genre(genre_name, config, excluded_keys, current_min_pop=None):
    movie_pool, tv_pool = [], []
    
    movie_genre_param = f"&with_genres={config['movie_genre']}" if config.get('movie_genre') else ""
    tv_genre_param = f"&with_genres={config['tv_genre']}" if config.get('tv_genre') else ""

    # Correction Point 2 : Extension de la profondeur de recherche à 8 pages (320 résultats bruts analysés)
    for page in range(1, 9):
        try:
            res = tmdb_api_call(f"/discover/movie?sort_by=popularity.desc{movie_genre_param}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "movie"; movie_pool.append(item)
        except: break
        time.sleep(0.1) # Respect du rate-limiting de TMDB
        
    for page in range(1, 9):
        try:
            res = tmdb_api_call(f"/discover/tv?sort_by=popularity.desc{tv_genre_param}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "tv"; tv_pool.append(item)
        except: break
        time.sleep(0.1)
    
    combined = tv_pool + movie_pool if config.get("prefer_tv", False) else movie_pool + tv_pool
    filtered = []
    
    # Correction Point 1 : Utilisation de la popularité dynamique reçue
    min_pop = current_min_pop if current_min_pop is not None else config.get("min_popularity", 20)
    
    for item in combined:
        composite_key = f"{item['media_type']}_{item['id']}"
        if item.get("adult") or item.get("popularity", 0) < min_pop: continue
        if not config.get("override_lang", False) and item.get("original_language", "") not in ALLOWED_LANGUAGES: continue
        
        if genre_name not in ["documentaire", "sport"]:
            if composite_key in excluded_keys: continue
            
        if composite_key in RUN_PROCESSED_IDS: continue
        filtered.append(item)
    return filtered

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
        if not bd: return [{"file_path": fallback_path, "width": 1920, "vote_count": 5, "vote_average": 5.0}]
        
        safe_bd = [b for b in bd if b.get("vote_average", 5.0) >= 3.0]
        if not safe_bd: safe_bd = bd
        return safe_bd[:15]
    except: return [{"file_path": fallback_path, "width": 1920, "vote_count": 5, "vote_average": 5.0}]

def score_and_select_backdrop(backdrops):
    scored_images = []
    for bg in backdrops:
        width = bg.get("width", 0)
        height = bg.get("height", 0)
        votes = bg.get("vote_count", 0)
        vote_avg = bg.get("vote_average", 5.0)
        
        base_score = (votes * 4) + (vote_avg * 15)
        
        aspect_ratio = width / height if height > 0 else 0
        if abs(aspect_ratio - 1.777) > 0.04:
            base_score -= 250
        
        if width >= 3840 or height >= 2160:
            base_score += 600  
        elif width >= 2560 or height >= 1440:
            base_score += 350  
        elif width >= 1920 or height >= 1080:
            base_score += 100  
        else:
            base_score -= 200  
            
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
    return final_ycbcr.convert("RGB").filter(ImageFilter.SHARPEN)

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
    return Image.alpha_composite(final_img, text_layer).convert("RGB")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    history = load_and_clean_history()
    excluded_keys = set(history.keys())
    
    excluded_backdrops = {data["backdrop_path"] for data in history.values() if "backdrop_path" in data}
    current_year = datetime.now().year

    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Analyse Algorithmique : {config['label']} ---")
        
        success_genre = False
        base_min_pop = config.get("min_popularity", 20)
        
        # Correction Point 1 : Définition des paliers de dégradation de la popularité (100% -> 75% -> 50% -> 25% -> Plancher à 5)
        pop_paliers = [base_min_pop, max(15, int(base_min_pop * 0.75)), max(10, int(base_min_pop * 0.5)), max(5, int(base_min_pop * 0.25)), 5]
        pop_paliers = sorted(list(set(pop_paliers)), reverse=True) # Nettoyage des doublons éventuels
        
        candidates_pool_all_paliers = []
        
        for current_min_pop in pop_paliers:
            if success_genre: break
            
            print(f" -> Analyse avec un seuil de popularité minimale fixé à : {current_min_pop}")
            candidates = get_trending_media_for_genre(genre_name, config, excluded_keys, current_min_pop=current_min_pop)
            if not candidates: continue
            
            scoring_keywords = set(config.get("scoring_keywords", []))
            scored_candidates = []
            
            for item in candidates:
                if genre_name == "animation" and item.get("original_language", "") not in WESTERN_LANGUAGES:
                    continue
                    
                media_keywords = get_media_keywords(item["media_type"], item["id"])
                
                # SÉCURITÉ INVIOLABLE : Les mots-clés interdits provoquent toujours un rejet immédiat
                if media_keywords.intersection(BANNED_KEYWORDS): continue
                if genre_name == "famille" and media_keywords.intersection(FAMILY_BANNED_KEYWORDS): continue
                
                kw_score = len(media_keywords.intersection(scoring_keywords)) * 55
                pop_score = min(item.get("popularity", 0) / 2.5, 140)
                total_score = kw_score + pop_score
                
                release_date_str = item.get("release_date") or item.get("first_air_date") or ""
                if release_date_str and len(release_date_str) >= 4 and release_date_str[:4].isdigit():
                    if int(release_date_str[:4]) >= (current_year - 10):
                        total_score += 150  
                    else:
                        total_score -= 100  
                else:
                    total_score -= 50
                
                if genre_name != "animation-japonaise" and item.get("original_language", "") in WESTERN_LANGUAGES:
                    total_score += 75  
                    
                scored_candidates.append({"item": item, "score": total_score})
                
            scored_candidates.sort(key=lambda x: x["score"], reverse=True)
            
            # Stockage dans le pool global de secours en cas d'impasse totale sur les images neuves
            for c in scored_candidates:
                if c not in candidates_pool_all_paliers:
                    candidates_pool_all_paliers.append(c)
            
            # ------------------------------------------------------------------
            # PASSE N°1 : RECHERCHE PRIORITAIRE D'UNE IMAGE ULTRA-FRAÎCHE (INÉDITE)
            # ------------------------------------------------------------------
            for candidate in scored_candidates:
                media = candidate["item"]
                backdrops = get_best_textless_backdrops(media["media_type"], media["id"], media["backdrop_path"])
                
                # Extraction stricte des visuels n'ayant jamais été affichés par le passé
                fresh_backdrops = [b for b in backdrops if b["file_path"] not in excluded_backdrops]
                if not fresh_backdrops: 
                    continue # On passe directement au média suivant pour forcer l'apparition de nouveautés
                
                best_bg = score_and_select_backdrop(fresh_backdrops)
                
                try:
                    res = requests.get(f"https://image.tmdb.org/t/p/original{best_bg['file_path']}", stream=True, timeout=10)
                    if res.status_code == 200:
                        raw_img = Image.open(res.raw).convert("RGB")
                        media_title = media.get('title') or media.get('name')
                        print(f" -> [IMAGE INÉDITE] Sélectionnée ({best_bg.get('width')}x{best_bg.get('height')} - Score: {candidate['score']:.1f}) : {media_title}")
                        
                        final_banner = finalize_landscape_banner(raw_img, config["label"], config["color"])
                        final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
                        final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)
                        
                        composite_key = f"{media['media_type']}_{media['id']}"
                        RUN_PROCESSED_IDS.add(composite_key)
                        
                        history[composite_key] = {
                            "title": media_title, 
                            "genre": genre_name, 
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "backdrop_path": best_bg["file_path"]
                        }
                        success_genre = True
                        break
                except Exception as e:
                    print(f" Échec image neuve : {e}")
                    continue
            
            if success_genre: break
            
        # ------------------------------------------------------------------
        # PASSE N°2 : RECYCLAGE EN ULTIME RECOURS (Sécurité anti-échec critique)
        # ------------------------------------------------------------------
        if not success_genre and candidates_pool_all_paliers:
            print(f" [⚠️ INFO] Aucune image inédite disponible sur l'ensemble des paliers pour '{config['label']}'. Utilisation du pool de secours...")
            candidates_pool_all_paliers.sort(key=lambda x: x["score"], reverse=True)
            
            for candidate in candidates_pool_all_paliers:
                media = candidate["item"]
                backdrops = get_best_textless_backdrops(media["media_type"], media["id"], media["backdrop_path"])
                best_bg = score_and_select_backdrop(backdrops) # Réutilisation autorisée en dernier recours
                
                try:
                    res = requests.get(f"https://image.tmdb.org/t/p/original{best_bg['file_path']}", stream=True, timeout=10)
                    if res.status_code == 200:
                        raw_img = Image.open(res.raw).convert("RGB")
                        media_title = media.get('title') or media.get('name')
                        print(f" -> [RECYCLAGE DE SECOURS] Sélectionné ({best_bg.get('width')}x{best_bg.get('height')}) : {media_title}")
                        
                        final_banner = finalize_landscape_banner(raw_img, config["label"], config["color"])
                        final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
                        final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)
                        
                        composite_key = f"{media['media_type']}_{media['id']}"
                        RUN_PROCESSED_IDS.add(composite_key)
                        
                        history[composite_key] = {
                            "title": media_title, 
                            "genre": genre_name, 
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "backdrop_path": best_bg["file_path"]
                        }
                        success_genre = True
                        break
                except Exception as e:
                    print(f" Échec image secours : {e}")
                    continue
                    
        if not success_genre:
            print(f" [ALERTE CRITIQUE] Aucun visuel n'a pu être généré pour le genre : {config['label']}")

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(history.items(), key=lambda x: x[1]['date'], reverse=True)), f, ensure_ascii=False, indent=4)
    print("\n[SUCCESS] Génération journalière terminée, stabilisée et purifiée.")

if __name__ == "__main__":
    main()

import os
import sys
import time
import json
import requests
import random
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

# BANNED_KEYWORDS : Ajout du tag 180340 (voyeur) suite à l'analyse du genre Romance
BANNED_KEYWORDS = {
    195669, 155477, 198385, 256466, 155716, 190340, 156201, 291195, 
    242216, 33998, 190370, 186107, 10053, 910, 348517, 9835, 18321, 
    267122, 356759, 180340
}

FAMILY_BANNED_KEYWORDS = {3036, 11001, 192947, 273060, 282071, 243261, 279473}

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
    "documentaire": {"label": "Documentaire", "color": (20, 140, 60), "movie_genre": 99, "tv_genre": 99, "extra": "&without_genres=16", "scoring_keywords": []},
    "drame": {"label": "Drame", "color": (30, 90, 170), "movie_genre": 18, "tv_genre": 18, "extra": "&without_genres=16", "scoring_keywords": []},
    # Amélioration 1 : Alignement linguistique pour Famille (Exclusion Asie)
    "famille": {"label": "Famille", "color": (170, 25, 150), "movie_genre": 10751, "tv_genre": 10751, "extra": "&without_genres=16&without_original_language=ko|ja|zh", "scoring_keywords": []},
    "fantastique": {"label": "Fantastique", "color": (110, 30, 190), "movie_genre": 14, "tv_genre": 10765, "extra": "&without_genres=16", "scoring_keywords": []},
    "guerre": {"label": "Guerre", "color": (90, 80, 70), "movie_genre": 10752, "tv_genre": 10768, "extra": "&without_genres=16", "scoring_keywords": []},
    # Préservation Intégrale des Séries TV d'Histoire (ID 10768 pour le volet TV de TMDB)
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

def get_trending_media_for_genre(genre_name, config):
    movie_pool, tv_pool = [], []
    
    movie_genre_param = f"&with_genres={config['movie_genre']}" if config.get('movie_genre') else ""
    tv_genre_param = f"&with_genres={config['tv_genre']}" if config.get('tv_genre') else ""

    # Exploration en profondeur : passage de 3 à 8 pages pour multiplier les choix de l'algorithme
    for page in range(1, 9):
        try:
            res = tmdb_api_call(f"/discover/movie?sort_by=popularity.desc{movie_genre_param}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "movie"; movie_pool.append(item)
        except: break
    for page in range(1, 9):
        try:
            res = tmdb_api_call(f"/discover/tv?sort_by=popularity.desc{tv_genre_param}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "tv"; tv_pool.append(item)
        except: break
    
    combined = tv_pool + movie_pool if config.get("prefer_tv", False) else movie_pool + tv_pool
    filtered = []
    min_pop = config.get("min_popularity", 20)
    
    for item in combined:
        composite_key = f"{item['media_type']}_{item['id']}"
        if item.get("adult") or item.get("popularity", 0) < min_pop: continue
        if not config.get("override_lang", False) and item.get("original_language", "") not in ALLOWED_LANGUAGES: continue
        if composite_key in RUN_PROCESSED_IDS: continue
        
        # NOTE IMPORTANTE : Nous ne filtrons PLUS l'historique ici. Tout le vivier est conservé
        # afin de permettre une véritable logique de "Pass 1 (Inédit)" puis "Pass 2 (Fallback)".
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
        
        # ------------------------------------------------------------------
        # TRICHE ET MANAGEMENT LOCAL EXCLUSIF POUR LE GENRE DOCUMENTAIRE
        # ------------------------------------------------------------------
        if genre_name == "documentaire":
            print(" -> [MODE CHEAT] Interception locale activée pour Documentaire.")
            ref_dir = os.path.join(OUTPUT_DIR, "References")
            
            if os.path.exists(ref_dir):
                valid_extensions = (".jpg", ".jpeg", ".png", ".webp")
                local_files = [f for f in os.listdir(ref_dir) if f.lower().endswith(valid_extensions)]
                
                if local_files:
                    fresh_local_files = [f for f in local_files if f"local_{f}" not in excluded_keys]
                    if not fresh_local_files:
                        fresh_local_files = local_files
                        
                    chosen_file = random.choice(fresh_local_files)
                    file_path = os.path.join(ref_dir, chosen_file)
                    
                    try:
                        raw_img = Image.open(file_path).convert("RGB")
                        print(f" -> [IMAGE LOCALE] Sélectionnée aléatoirement : {chosen_file}")
                        
                        final_banner = finalize_landscape_banner(raw_img, config["label"], config["color"])
                        final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
                        final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)
                        
                        composite_key = f"local_{chosen_file}"
                        RUN_PROCESSED_IDS.add(composite_key)
                        
                        history[composite_key] = {
                            "title": f"Curation : {chosen_file}", 
                            "genre": genre_name, 
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "backdrop_path": file_path
                        }
                        success_genre = True
                    except Exception as e:
                        print(f" Échec du traitement de la photo locale : {e}")
                else:
                    print(f" [⚠️ ERREUR] Le dossier {ref_dir} est vide.")
            else:
                print(f" [⚠️ ERREUR] Le dossier de référence n'existe pas : {ref_dir}")
            
            if success_genre:
                continue

        # ------------------------------------------------------------------
        # ROUTINE STANDARD VIA API TMDB (TOUS LES AUTRES GENRES)
        # ------------------------------------------------------------------
        candidates = get_trending_media_for_genre(genre_name, config)
        if not candidates: 
            print(" [⚠️ INFO] Aucun candidat renvoyé par l'API.")
            continue
        
        scoring_keywords = set(config.get("scoring_keywords", []))
        scored_candidates = []
        
        for item in candidates:
            if genre_name == "animation" and item.get("original_language", "") not in WESTERN_LANGUAGES:
                continue
                
            media_keywords = get_media_keywords(item["media_type"], item["id"])
            
            if media_keywords.intersection(BANNED_KEYWORDS):
                continue
            if genre_name == "famille" and media_keywords.intersection(FAMILY_BANNED_KEYWORDS):
                continue
            
            kw_score = len(media_keywords.intersection(scoring_keywords)) * 55
            pop_score = min(item.get("popularity", 0) / 2.5, 140)
            total_score = kw_score + pop_score
            
            # Application stricte de l'avantage chronologique (Bonus +150 aux œuvres de moins de 10 ans)
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
        
        # ------------------------------------------------------------------
        # PASSE 1 : ESSAI EXCLUSIF DE CONTENU STRITEMENT INÉDIT (Anti-Doublons)
        # ------------------------------------------------------------------
        print(f" -> [PASSE 1] Recherche d'un média inédit sur {len(scored_candidates)} candidats...")
        for candidate in scored_candidates:
            media = candidate["item"]
            composite_key = f"{media['media_type']}_{media['id']}"
            
            # Si le média a été traité ces 14 derniers jours, on le passe (pour le moment)
            if composite_key in excluded_keys:
                continue
                
            backdrops = get_best_textless_backdrops(media["media_type"], media["id"], media["backdrop_path"])
            if len(backdrops) < 5:  # Conservation du critère de qualité de 5 backdrops min
                continue
            
            fresh_backdrops = [b for b in backdrops if b["file_path"] not in excluded_backdrops]
            if not fresh_backdrops:
                continue
                
            best_bg = score_and_select_backdrop(fresh_backdrops)
            
            try:
                res = requests.get(f"https://image.tmdb.org/t/p/original{best_bg['file_path']}", stream=True, timeout=10)
                if res.status_code == 200:
                    raw_img = Image.open(res.raw).convert("RGB")
                    media_title = media.get('title') or media.get('name')
                    print(f" -> [IMAGE INÉDITE] Sélectionnée ({best_bg.get('width')}x{best_bg.get('height')}) : {media_title}")
                    
                    final_banner = finalize_landscape_banner(raw_img, config["label"], config["color"])
                    final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
                    final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)
                    
                    RUN_PROCESSED_IDS.add(composite_key)
                    history[composite_key] = {
                        "title": media_title, 
                        "genre": genre_name, 
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "backdrop_path": best_bg["file_path"]
                    }
                    success_genre = True
                    break
            except:
                continue
                
        # ------------------------------------------------------------------
        # PASSE 2 : SECOURS / MODE FALLBACK COUVRE-FEU (Recyclage intelligent)
        # ------------------------------------------------------------------
        if not success_genre and scored_candidates:
            print(" -> [PASSE 2 - FALLBACK] Aucun contenu inédit valide. Recours au recyclage des tops tendances...")
            for candidate in scored_candidates:
                media = candidate["item"]
                
                backdrops = get_best_textless_backdrops(media["media_type"], media["id"], media["backdrop_path"])
                if len(backdrops) < 5:
                    continue
                
                # On essaie d'abord un backdrop pas encore affiché, sinon on accepte le meilleur existant
                fresh_backdrops = [b for b in backdrops if b["file_path"] not in excluded_backdrops]
                final_backdrops_pool = fresh_backdrops if fresh_backdrops else backdrops
                
                best_bg = score_and_select_backdrop(final_backdrops_pool)
                
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
                except:
                    continue
                    
        if not success_genre:
            print(f" [ALERTE CRITIQUE] Aucun visuel n'a pu être généré pour le genre : {config['label']}")

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(history.items(), key=lambda x: x[1]['date'], reverse=True)), f, ensure_ascii=False, indent=4)
    print("\n[SUCCESS] Génération journalière terminée, stabilisée et purifiée.")

if __name__ == "__main__":
    main()

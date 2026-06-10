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

# Configuration chirurgicale des genres - Palette Apple TV Premium optimisée
GENRES_CONFIG = {
    "action": {"label": "Action", "color": (210, 40, 45), "movie_genre": 28, "tv_genre": 10759, "extra": "&without_genres=16", "scoring_keywords": [3930, 6054, 12993, 9951, 8440, 188955, 226499, 83, 312, 779, 4565, 14955, 853, 9665, 10044]},
    "animation-japonaise": {"label": "Animation Japonaise", "color": (120, 60, 200), "movie_genre": 16, "tv_genre": 16, "extra": "&with_original_language=ja", "prefer_tv": True, "override_lang": True, "scoring_keywords": [210024, 13141, 207826]},
    "animation": {
        "label": "Animation", 
        "color": (0, 200, 255), 
        "movie_genre": 16, 
        "tv_genre": 16, 
        "extra": "&without_genres=99&without_original_language=ja|ko|zh&without_keywords=210024|287513",
        "min_popularity": 80,
        "scoring_keywords": [272909, 7376, 278823, 234183, 179411, 234662, 290589, 297442, 339048, 366485]
    },
    "aventure": {"label": "Aventure", "color": (20, 140, 90), "movie_genre": 12, "tv_genre": 10759, "extra": "&without_genres=16", "scoring_keywords": [195114, 161176, 818, 4152, 170362, 210246, 10364, 41586, 6956, 269233]},
    "comedie": {"label": "Comédie", "color": (220, 170, 30), "movie_genre": 35, "tv_genre": 35, "extra": "&without_genres=16", "scoring_keywords": [8201, 9755, 9964, 375047, 6241, 9253]},
    "crime": {"label": "Crime", "color": (107, 114, 128), "movie_genre": 80, "tv_genre": 80, "extra": "&without_genres=16", "scoring_keywords": [2095, 9748, 181644, 157241, 206958, 268067, 703, 5340, 6149, 9826, 155790, 207046]},
    "documentaire": {"label": "Documentaire", "color": (34, 197, 94), "movie_genre": 99, "tv_genre": 99, "extra": "&without_genres=16", "scoring_keywords": [221355, 305903, 343303, 284176]},
    "drame": {"label": "Drame", "color": (14, 165, 233), "movie_genre": 18, "tv_genre": 18, "extra": "&without_genres=16", "scoring_keywords": []},
    "famille": {"label": "Famille", "color": (217, 70, 239), "movie_genre": 10751, "tv_genre": 10751, "extra": "&without_genres=16", "scoring_keywords": []},
    "fantastique": {"label": "Fantastique", "color": (168, 85, 247), "movie_genre": 14, "tv_genre": 10765, "extra": "&without_genres=16", "scoring_keywords": []},
    "guerre": {"label": "Guerre", "color": (120, 113, 108), "movie_genre": 10752, "tv_genre": 10768, "extra": "&without_genres=16", "scoring_keywords": []},
    "histoire": {"label": "Histoire", "color": (139, 90, 60), "movie_genre": 36, "tv_genre": 10768, "extra": "&without_genres=16", "scoring_keywords": []},
    "horreur": {"label": "Horreur", "color": (239, 68, 68), "movie_genre": 27, "tv_genre": 27, "extra": "&without_genres=16&with_keywords=3358|9748|6152", "scoring_keywords": []},
    "romance": {"label": "Romance", "color": (230, 90, 140), "movie_genre": 10749, "tv_genre": 10749, "extra": "&without_genres=16&without_original_language=ko|ja|zh", "scoring_keywords": []},
    "science-fiction": {"label": "Science-Fiction", "color": (6, 182, 212), "movie_genre": 878, "tv_genre": 10765, "extra": "&without_genres=16&with_keywords=4565|9882", "scoring_keywords": []},
    "thriller": {"label": "Thriller", "color": (30, 120, 80), "movie_genre": 53, "tv_genre": 80, "extra": "&without_genres=16&with_keywords=9826|10123", "scoring_keywords": []},
    "western": {"label": "Western", "color": (214, 100, 42), "movie_genre": 37, "tv_genre": 37, "extra": "&without_genres=16", "scoring_keywords": []}
}

RUN_PROCESSED_IDS = set()

def tmdb_api_call(endpoint, params=None):
    if params is None:
        params = {}
    params["api_key"] = TMDB_API_KEY
    for attempt in range(3):
        try:
            res = requests.get(f"{TMDB_BASE}{endpoint}", params=params, timeout=15)
            res.raise_for_status()
            return res.json()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 + attempt)

def load_and_clean_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        return {}
        
    cleaned_history = {}
    limit_date = datetime.now() - timedelta(days=14)
    
    for media_key, data in history.items():
        try:
            entry_date = datetime.strptime(data["date"], "%Y-%m-%d")
            if entry_date > limit_date:
                cleaned_history[media_key] = data
        except Exception:
            continue
            
    return cleaned_history

def get_trending_media_for_genre(config, excluded_keys):
    movie_pool = []
    tv_pool = []
    
    for page in range(1, 4):
        movie_url = f"/discover/movie?sort_by=popularity.desc&with_genres={config['movie_genre']}{config.get('extra', '')}&page={page}&include_adult=false"
        try:
            movie_data = tmdb_api_call(movie_url)
            results = movie_data.get("results", [])
            if not results:
                break
            for item in results:
                if item.get("backdrop_path"):
                    item["media_type"] = "movie"
                    movie_pool.append(item)
        except Exception as e:
            print(f"      Alerte discover movie (page {page}): {e}")
            break

    for page in range(1, 4):
        tv_url = f"/discover/tv?sort_by=popularity.desc&with_genres={config['tv_genre']}{config.get('extra', '')}&page={page}&include_adult=false"
        try:
            tv_data = tmdb_api_call(tv_url)
            results = tv_data.get("results", [])
            if not results:
                break
            for item in results:
                if item.get("backdrop_path"):
                    item["media_type"] = "tv"
                    tv_pool.append(item)
        except Exception as e:
            print(f"      Alerte discover tv (page {page}): {e}")
            break

    combined_pool = tv_pool + movie_pool if config.get("prefer_tv", False) else movie_pool + tv_pool
    filtered_pool = []
    min_pop_threshold = config.get("min_popularity", 25)

    for item in combined_pool:
        lang = item.get("original_language", "")
        composite_key = f"{item['media_type']}_{item['id']}"
        popularity = item.get("popularity", 0)
        
        if item.get("adult") is True:
            continue
        if popularity < min_pop_threshold:
            continue
        if not config.get("override_lang", False) and lang not in ALLOWED_LANGUAGES:
            continue
        if composite_key in excluded_keys or composite_key in RUN_PROCESSED_IDS:
            continue
            
        filtered_pool.append(item)
        
    print(f"   Pool éligible après filtrage : {len(filtered_pool)} œuvres (Films & Séries).")
    
    if len(filtered_pool) > 50:
        selected_pool = random.sample(filtered_pool, 50)
        print(f"   Sélection aléatoire de 50 candidats parmi les {len(filtered_pool)} œuvres.")
        return selected_pool
    else:
        print(f"   Conservation de l'intégralité du pool ({len(filtered_pool)} candidats éligibles).")
        return filtered_pool

def get_keyword_id_by_name(name):
    try:
        data = tmdb_api_call("/search/keyword", {"query": name})
        if data and "results" in data:
            for kw in data["results"]:
                if kw.get("name", "").lower() == name.lower():
                    return kw["id"]
    except Exception as e:
        print(f"      Alerte recherche de mot-clé '{name}': {e}")
    return None

def get_media_keywords(media_type, media_id):
    try:
        endpoint = f"/{media_type}/{media_id}/keywords"
        data = tmdb_api_call(endpoint)
        if not data:
            return set()
        keyword_list = data.get("keywords") or data.get("results") or []
        return {kw["id"] for kw in keyword_list if "id" in kw}
    except Exception as e:
        print(f"      Alerte keywords pour {media_type} {media_id}: {e}")
        return set()

def get_best_textless_backdrops(media_type, media_id, fallback_path):
    try:
        data = tmdb_api_call(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        backdrops = data.get("backdrops", [])
        if not backdrops:
            return [{"file_path": fallback_path, "width": 1920, "vote_count": 5, "vote_average": 5.0}]
            
        backdrops.sort(key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)), reverse=True)
        return backdrops[:5]
    except Exception:
        return [{"file_path": fallback_path, "width": 1920, "vote_count": 5, "vote_average": 5.0}]

def analyze_and_score_backdrop(bg, item):
    score = 40
    width = bg.get("width", 0)
    popularity = item.get("popularity", 0)
    vote_count = bg.get("vote_count", 0)
    
    if vote_count == 0:
        score -= 30

    release_date_str = item.get("release_date") or item.get("first_air_date") or ""
    if release_date_str:
        try:
            year = datetime.strptime(release_date_str, "%Y-%m-%d").year
            if year >= 2022: score += 35
            elif year >= 2015: score += 15
            elif year < 2005: score -= 20
        except ValueError:
            pass

    if width >= 3840: score += 15
    elif width >= 1920: score += 10
        
    if popularity > 150: score += 15
        
    return score

def apply_apple_tv_duotone(img, target_color):
    """Applique un traitement d'image adaptatif et non linéaire (Style Apple TV Premium)"""
    # 1. Conversion en niveaux de gris et extraction de la matrice float32
    gray = img.convert("L")
    gray_np = np.array(gray, dtype=np.float32)
    
    # 2. Normalisation Min-Max adaptative (Étirement de l'histogramme pour révéler les textures)
    f_min, f_max = gray_np.min(), gray_np.max()
    if f_max > f_min:
        gray_np = (gray_np - f_min) * (255.0 / (f_max - f_min))
    
    # 3. Courbe en S Sigmoïde dynamique pour booster le contraste local sans boucher les noirs
    # Centre autour du gris moyen (127.5), facteur d'accentuation chirurgical à 0.022
    gray_np = 255.0 / (1.0 + np.exp(-0.022 * (gray_np - 127.5)))
    
    # 4. Cartographie du Duotone avec le noir bleuté emblématique d'Apple
    base_dark = np.array([12, 16, 26])  # Fond sombre profond cinéma
    target_light = np.array(target_color)
    
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        # Interpolation linéaire basée sur l'histogramme boosté en numpy
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
        
    return Image.fromarray(duotone)

def finalize_landscape_banner(img, label, target_color):
    img = ImageOps.fit(img, (1920, 1080), method=Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.05) # Réduit légèrement l'apport PIL linéaire devenu inutile
    img = apply_apple_tv_duotone(img, target_color)
    
    # Dégradé cinématique
    gradient = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(400, 1080):
        alpha = int(((y - 400) / 680) ** 1.8 * 252)
        g_draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), gradient)

    text_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    
    t_draw = ImageDraw.Draw(text_layer)
    s_draw = ImageDraw.Draw(shadow_layer)
    
    font_size = 165
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", font_size)
    except IOError:
        font = ImageFont.load_default()

    padding_left = 130
    padding_bottom = 140
    max_text_width = 1920 - (padding_left * 2)

    words = label.split(" ")
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        if t_draw.textlength(test_line, font=font) <= max_text_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)

    line_spacing = 20
    line_height = font_size - 22
    total_text_height = (len(lines) * line_height) + ((len(lines) - 1) * line_spacing)
    
    base_y = (1080 - padding_bottom - line_height) - (total_text_height - line_height)

    current_y = base_y
    for line in lines:
        s_draw.text((padding_left + 6, current_y + 10), line, fill=(0, 0, 0, 245), font=font)
        t_draw.text((padding_left, current_y), line, fill=(255, 255, 255, 255), font=font)
        current_y += line_height + line_spacing

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(12))
    
    final_img = Image.alpha_composite(img, shadow_layer)
    final_img = Image.alpha_composite(final_img, text_layer)
    
    return final_img.convert("RGB")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    EXCLUDED_KEYWORD_IDS = set()
    raw_excludes = []
    for name_or_id in raw_excludes:
        if isinstance(name_or_id, int):
            EXCLUDED_KEYWORD_IDS.add(name_or_id)
        elif isinstance(name_or_id, str):
            kw_id = get_keyword_id_by_name(name_or_id)
            if kw_id:
                EXCLUDED_KEYWORD_IDS.add(kw_id)
                print(f"Mot-clé à exclure résolu : '{name_or_id}' -> ID {kw_id}")
    
    history = load_and_clean_history()
    excluded_keys = set(history.keys())
    
    print(f"Chargement de l'historique : {len(excluded_keys)} œuvres verrouillées pour préservation.")

    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Sélection pour le Genre : {config['label']} ---")
        
        candidates_pool = get_trending_media_for_genre(config, excluded_keys)
        if not candidates_pool:
            print(f" [CONSERVATION] Aucun candidat éligible trouvé pour le genre {config['label']}. Ancien poster préservé.")
            sys.stdout.write(f"::warning file=.github/scripts/posters-genres.py,line=200,title=Génération Sautée ({config['label']})::Aucun média valide trouvé dans l'API. L'ancien poster est conservé.\n")
            continue
            
        scoring_keywords = set(config.get("scoring_keywords", []))
        scored_candidates = []
        
        print(f" -> Évaluation par mots-clés de {len(candidates_pool)} candidats...")
        for idx, item in enumerate(candidates_pool):
            media_type = item["media_type"]
            media_id = item["id"]
            media_title = item.get("title") or item.get("name")
            
            keywords = get_media_keywords(media_type, media_id)
            
            bad_tags = keywords.intersection(EXCLUDED_KEYWORD_IDS)
            if bad_tags:
                print(f"      [{idx+1}/{len(candidates_pool)}] {media_title} ({media_type.upper()}) - ÉLIMINÉ (contient un tag exclu : {list(bad_tags)})")
                continue
            
            matching_keywords = keywords.intersection(scoring_keywords)
            tag_score = len(matching_keywords) * 10
            
            scored_candidates.append({
                "item": item,
                "score": tag_score,
                "keywords_found": list(matching_keywords)
            })
            
            if tag_score > 0:
                print(f"      [{idx+1}/{len(candidates_pool)}] {media_title} ({media_type.upper()}) - Score: {tag_score} (Tags: {list(matching_keywords)})")
                
            time.sleep(0.05)
            
        if not scored_candidates:
            print(f" [CONSERVATION] Aucun candidat éligible restant après filtrage par tags éliminatoires pour {config['label']}. Ancien poster préservé.")
            sys.stdout.write(f"::warning file=.github/scripts/posters-genres.py,line=320,title=Tous Éliminés ({config['label']})::Tous les candidats ont été éliminés par les tags exclus. L'ancien poster est conservé.\n")
            continue
            
        scored_candidates.sort(key=lambda x: (x["score"], x["item"].get("popularity", 0)), reverse=True)
        
        winner_data = scored_candidates[0]
        selected_media = winner_data["item"]
        winner_score = winner_data["score"]
        
        media_id = selected_media["id"]
        media_type = selected_media["media_type"]
        composite_key = f"{media_type}_{media_id}"
        media_title = selected_media.get("title") or selected_media.get("name")
        
        print(f" -> Vainqueur sélectionné : {media_title} ({media_type.upper()} - ID: {media_id})")
        
        backdrops_list = get_best_textless_backdrops(media_type, media_id, selected_media["backdrop_path"])
        time.sleep(0.2)
        
        scored_backdrops = []
        for bg in backdrops_list:
            img_url = f"https://image.tmdb.org/t/p/original{bg['file_path']}"
            try:
                res = requests.get(img_url, stream=True, timeout=10)
                if res.status_code == 200:
                    raw_img = Image.open(res.raw).convert("RGB")
                    score = analyze_and_score_backdrop(bg, selected_media)
                    scored_backdrops.append({"image": raw_img, "score": score, "path": bg["file_path"]})
            except Exception:
                continue
                
        if scored_backdrops:
            scored_backdrops.sort(key=lambda x: x["score"], reverse=True)
            winner_bg = scored_backdrops[0]
            
            print(f"   ==> Backdrop élu (Score: {winner_bg['score']}/100) | Image: {winner_bg['path']}")
            
            final_banner = finalize_landscape_banner(winner_bg["image"], config["label"], config["color"])
            
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            RUN_PROCESSED_IDS.add(composite_key)
            history[composite_key] = {
                "title": media_title,
                "genre": genre_name,
                "date": datetime.now().strftime("%Y-%m-%d")
            }
        else:
            print(f" [CONSERVATION] Échec d'extraction visuelle pour {media_title}. L'ancien poster de {config['label']} reste en place.")
            sys.stdout.write(f"::warning file=.github/scripts/posters-genres.py,line=240,title=Visuel Manquant ({config['label']})::Impossible d'extraire un fond pour '{media_title}'. L'ancien poster est conservé.\n")

    sorted_history = dict(sorted(history.items(), key=lambda item: item[1]['date'], reverse=True))

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_history, f, ensure_ascii=False, indent=4)
        
    print("\n[SUCCESS] Déploiement terminé. Protection contre les bannières vides active.")

if __name__ == "__main__":
    main()

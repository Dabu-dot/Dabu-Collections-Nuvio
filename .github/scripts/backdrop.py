import os
import sys
import time
import math
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageEnhance, ImageOps, ImageFilter

# ==============================================================================
# CONFIGURATION GLOBALE
# ==============================================================================
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

OUTPUT_DIR = "Ressources/Collections Covers/Genres"

# Paramètres de style de la charte graphique Streaming
TILT_ANGLE = -10      # Inclinaison de la grille de vignettes
CARD_GAP = 28         # Espacement harmonieux pour les grandes cartes
CORNER_RADIUS = 14    # Angles arrondis plus prononcés pour les grandes cartes

# Sécurités et filtres de contenu
ALLOWED_LANGUAGES = {"fr", "en", "es", "de", "it", "ja", "ko", "zh"}
WESTERN_LANGUAGES = {"fr", "en", "es", "de", "it"}

BANNED_KEYWORDS = {
    195669, 155477, 198385, 256466, 155716, 190340, 156201, 291195,
    242216, 33998, 190370, 186107, 10053, 910, 348517, 9835, 18321, 
    267122, 356759
}
FAMILY_BANNED_KEYWORDS = {3036, 11001, 192947, 273060, 282071, 243261, 279473}

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
    "documentaire": {"label": "Documentaire", "color": (20, 140, 60), "movie_genre": 99, "tv_genre": 99, "extra": "&without_genres=16", "min_popularity": 50, "scoring_keywords": [210002, 283115, 6432, 209250, 9714, 9672, 221355, 18330, 18165, 272851, 270, 9902, 305903, 252105, 211505, 284176, 160330, 9882]},
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
        except:
            if attempt == 2: raise
            time.sleep(1.5 + attempt)

def get_trending_media(config):
    movie_pool, tv_pool = [], []
    m_genre = f"&with_genres={config['movie_genre']}" if config.get('movie_genre') else ""
    t_genre = f"&with_genres={config['tv_genre']}" if config.get('tv_genre') else ""

    # Exploration massive étendue à 10 pages complètes (Films et Séries) pour maximiser le choix original
    for page in range(1, 11):
        try:
            res = tmdb_api_call(f"/discover/movie?sort_by=popularity.desc{m_genre}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "movie"; movie_pool.append(item)
        except: break
    for page in range(1, 11):
        try:
            res = tmdb_api_call(f"/discover/tv?sort_by=popularity.desc{t_genre}{config.get('extra', '')}&page={page}&include_adult=false")
            for item in res.get("results", []):
                if item.get("backdrop_path"): item["media_type"] = "tv"; tv_pool.append(item)
        except: break
    
    return tv_pool + movie_pool if config.get("prefer_tv", False) else movie_pool + tv_pool

def get_media_keywords(media_type, media_id):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/keywords")
        kw = res.get("keywords") or res.get("results") or []
        return {k["id"] for k in kw if "id" in k}
    except: return set()

def get_best_backdrop(media_type, media_id, fallback_path):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/images")
        bd = res.get("backdrops", [])
        if bd:
            def sort_by_preference(x):
                lang = x.get("iso_639_1")
                lang_priority = 2 if lang == "en" else (1 if lang is None or lang == "" else 0)
                vote_score = (x.get("vote_average", 0) * 10) + x.get("vote_count", 0)
                return (lang_priority, vote_score)

            bd.sort(key=sort_by_preference, reverse=True)
            return bd[0]["file_path"]
    except: pass
    return fallback_path

def create_premium_gradient(width, height, base_color):
    # Dégradé linéaire orienté à 40° (Sombre bas-gauche vers Clair haut-droit)
    r, g, b = base_color
    c_light = (min(255, int(r * 1.35)), min(255, int(g * 1.35)), min(255, int(b * 1.35)))
    c_mid = (r, g, b)
    c_dark = (max(15, int(r * 0.30)), max(15, int(g * 0.30)), max(15, int(b * 0.30)))
    
    sw, sh = 192, 108
    grad_img = Image.new("RGB", (sw, sh))
    pixels = []
    
    rad = math.radians(40)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    
    p_min = -sh * sin_a
    p_max = sw * cos_a
    p_range = p_max - p_min if (p_max - p_min) != 0 else 1
    
    for y in range(sh):
        for x in range(sw):
            p = x * cos_a - y * sin_a
            t = (p - p_min) / p_range
            t = max(0.0, min(1.0, t))
            
            if t < 0.5:
                local_t = t * 2.0
                r_c = int(c_dark[0] + (c_mid[0] - c_dark[0]) * local_t)
                g_c = int(c_dark[1] + (c_mid[1] - c_dark[1]) * local_t)
                b_c = int(c_dark[2] + (c_mid[2] - c_dark[2]) * local_t)
            else:
                local_t = (t - 0.5) * 2.0
                r_c = int(c_mid[0] + (c_light[0] - c_mid[0]) * local_t)
                g_c = int(c_mid[1] + (c_light[1] - c_mid[1]) * local_t)
                b_c = int(c_mid[2] + (c_light[2] - c_mid[2]) * local_t)
                
            pixels.append((r_c, g_c, b_c))
            
    grad_img.putdata(pixels)
    return grad_img.resize((width, height), Image.Resampling.BILINEAR)

def add_rounded_corners(img, radius):
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.size[0], img.size[1]), radius, fill=255)
    img_with_corners = img.copy()
    img_with_corners.putalpha(mask)
    return img_with_corners

def generate_grid_backdrop(genre_name, config):
    canvas_w, canvas_h = 1920, 1080
    background = create_premium_gradient(canvas_w, canvas_h, config["color"])
    
    raw_candidates = get_trending_media(config)
    # Tri absolu par popularité TMDB décroissante pour assurer la priorité au haut du panier
    raw_candidates.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    
    scoring_keywords = set(config.get("scoring_keywords", []))
    current_year = datetime.now().year
    
    cell_w, cell_h = 444, 250  
    cols, rows = 7, 6          
    max_vignettes = cols * rows
    
    processed_candidates = []
    seen_ids = set()
    
    # --- ENTONNOIR ADAPTATIF DYNAMIQUE ---
    # On commence par le min_popularity cible configuré. Si le pool filtré est trop petit, 
    # on diminue le seuil de 15 en 15 jusqu'à un plancher absolu de 5 pour forcer la diversité unique.
    target_pop = config.get("min_popularity", 15)
    while target_pop >= 5:
        for item in raw_candidates:
            composite_key = f"{item['media_type']}_{item['id']}"
            if composite_key in seen_ids or item.get("adult"): continue
            if item.get("popularity", 0) < target_pop: continue
            
            # Application des restrictions linguistiques structurelles
            if not config.get("override_lang", False) and item.get("original_language", "") not in ALLOWED_LANGUAGES: continue
            if genre_name == "animation" and item.get("original_language", "") not in WESTERN_LANGUAGES: continue
            
            keywords = get_media_keywords(item["media_type"], item["id"])
            if keywords.intersection(BANNED_KEYWORDS): 
                seen_ids.add(composite_key)
                continue
            if genre_name == "famille" and keywords.intersection(FAMILY_BANNED_KEYWORDS):
                seen_ids.add(composite_key)
                continue
            
            # Calcul qualitatif du score de positionnement
            score = len(keywords.intersection(scoring_keywords)) * 30
            score += min(item.get("popularity", 0) / 1.8, 180)
            
            release_date = item.get("release_date") or item.get("first_air_date") or ""
            if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
                if int(release_date[:4]) >= (current_year - 10): score += 150
                else: score -= 100
            
            if genre_name != "animation-japonaise" and item.get("original_language", "") in WESTERN_LANGUAGES:
                score += 75
                
            processed_candidates.append((score, item))
            seen_ids.add(composite_key)
            
        # Si on dispose d'un pool suffisant avec une marge de +10 candidats (en cas de liens morts au téléchargement)
        if len(processed_candidates) >= (max_vignettes + 10):
            break
        if target_pop == 5: 
            break
        target_pop = max(5, target_pop - 15)
        
    # Tri définitif du pool adaptatif extrait selon le score qualitatif décroissant
    processed_candidates.sort(key=lambda x: x[0], reverse=True)
    
    grid_w, grid_h = 3600, 2400
    grid_layer = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))
    
    grid_total_w = cols * cell_w + (cols - 1) * CARD_GAP + ((cell_w + CARD_GAP) // 2)
    grid_total_h = rows * cell_h + (rows - 1) * CARD_GAP
    start_x = (grid_w - grid_total_w) // 2
    start_y = (grid_h - grid_total_h) // 2
    
    # Téléchargement effectif des images uniques récoltées
    successful_vignettes = []
    for score, item in processed_candidates:
        if len(successful_vignettes) >= max_vignettes: break
        backdrop_path = get_best_backdrop(item["media_type"], item["id"], item["backdrop_path"])
        url = f"https://image.tmdb.org/t/p/w780{backdrop_path}"
        
        try:
            res = requests.get(url, stream=True, timeout=10)
            if res.status_code == 200:
                vignette = Image.open(res.raw).convert("RGB")
                vignette = ImageOps.fit(vignette, (cell_w, cell_h), method=Image.Resampling.LANCZOS)
                vignette = add_rounded_corners(vignette, radius=CORNER_RADIUS)
                successful_vignettes.append(vignette)
        except:
            continue

    # Sécurité absolue : Si le réseau subit des pertes massives, on duplique localement pour éviter les trous
    if successful_vignettes and len(successful_vignettes) < max_vignettes:
        base_vignettes = list(successful_vignettes)
        idx = 0
        while len(successful_vignettes) < max_vignettes:
            successful_vignettes.append(base_vignettes[idx % len(base_vignettes)])
            idx += 1

    # Préparation de l'ombre premium individualisée sous chaque vignette
    shadow_blur = 12
    shadow_offset_x = 4
    shadow_offset_y = 6
    card_shadow = Image.new("RGBA", (cell_w + shadow_blur * 2, cell_h + shadow_blur * 2), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(card_shadow)
    s_draw.rounded_rectangle((shadow_blur, shadow_blur, shadow_blur + cell_w, shadow_blur + cell_h), radius=CORNER_RADIUS, fill=(0, 0, 0, 110))
    card_shadow = card_shadow.filter(ImageFilter.GaussianBlur(shadow_blur // 2))
    
    count = 0
    for vignette in successful_vignettes:
        r_idx = count // cols
        c_idx = count % cols
        
        x = start_x + c_idx * (cell_w + CARD_GAP)
        if r_idx % 2 == 1:
            x += (cell_w + CARD_GAP) // 2
        
        y = start_y + r_idx * (cell_h + CARD_GAP)
        
        # Collage séquentiel Ombre -> Vignette
        grid_layer.paste(card_shadow, (x - shadow_blur + shadow_offset_x, y - shadow_blur + shadow_offset_y), card_shadow)
        grid_layer.paste(vignette, (x, y), vignette)
        count += 1

    print(f" -> Grille XXL diversifiée stabilisée : {count}/{max_vignettes} visuels uniques assemblés.")
    
    rotated_grid = grid_layer.rotate(TILT_ANGLE, resample=Image.Resampling.BILINEAR, expand=False)
    
    offset_x = (grid_w - canvas_w) // 2
    offset_y = (grid_h - canvas_h) // 2
    crop_box = (offset_x, offset_y, offset_x + canvas_w, offset_y + canvas_h)
    final_grid_cropped = rotated_grid.crop(crop_box)
    
    background.paste(final_grid_cropped, (0, 0), final_grid_cropped)
    final_output = background.convert("RGB")
    
    final_output.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
    final_output.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Génération Hebdomadaire Backdrops : {config['label']} ---")
        generate_grid_backdrop(genre_name, config)
    print("\n[SUCCESS] Tous vos backdrops hebdomadaires géants sont prêts.")

if __name__ == "__main__":
    main()

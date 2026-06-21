import os
import sys
import time
import requests
from PIL import Image, ImageDraw, ImageOps, ImageFilter

# ==============================================================================
# CONFIGURATION GLOBALE
# ==============================================================================
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

OUTPUT_DIR = "Ressources/Collections Covers/Genres/Weekly Backdrops"

# Paramètres de style de la charte graphique
TILT_ANGLE = -10      # Inclinaison de la grille de vignettes
CARD_GAP = 24         # Espacement prononcé entre les cartes
CORNER_RADIUS = 12    # Angles arrondis des cartes paysage

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
    "animation": {"label": "Animation", "color": (0, 150, 210), "movie_genre": 16, "tv_genre": 16, "extra": "&without_genres=99", "scoring_keywords": [272909, 7376, 278823, 234183, 179411, 234662, 290589, 297442, 339048, 366485]},
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
        except:
            if attempt == 2: raise
            time.sleep(1.5 + attempt)

def get_trending_media(config):
    """Explore jusqu'à 15 pages de résultats pour garantir un pool massif de médias uniques"""
    movie_pool, tv_pool = [], []
    m_genre = f"&with_genres={config['movie_genre']}" if config.get('movie_genre') else ""
    t_genre = f"&with_genres={config['tv_genre']}" if config.get('tv_genre') else ""

    for page in range(1, 16):
        try:
            res = tmdb_api_call(f"/discover/movie?sort_by=popularity.desc{m_genre}{config.get('extra', '')}&page={page}&include_adult=false")
            results = res.get("results", [])
            if not results: break
            for item in results:
                if item.get("backdrop_path"): item["media_type"] = "movie"; movie_pool.append(item)
        except: break
        
    for page in range(1, 16):
        try:
            res = tmdb_api_call(f"/discover/tv?sort_by=popularity.desc{t_genre}{config.get('extra', '')}&page={page}&include_adult=false")
            results = res.get("results", [])
            if not results: break
            for item in results:
                if item.get("backdrop_path"): item["media_type"] = "tv"; tv_pool.append(item)
        except: break
    
    return tv_pool + movie_pool if config.get("prefer_tv", False) else movie_pool + tv_pool

def get_media_keywords(media_type, media_id):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/keywords")
        kw = res.get("keywords") or res.get("results") or []
        return {k["id"] for k in kw if "id" in k}
    except: return set()

def get_textless_backdrop(media_type, media_id, fallback_path):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        bd = res.get("backdrops", [])
        if bd:
            bd.sort(key=lambda x: (x.get("vote_average", 0) * 10) + x.get("vote_count", 0), reverse=True)
            return bd[0]["file_path"]
    except: pass
    return fallback_path

def create_premium_angled_gradient(width, height, base_color):
    """Génère un dégradé diagonal parfait aligné à 40/45° (Sombre Bas-Gauche -> Clair Haut-Droite)"""
    small_canvas = Image.new("RGB", (100, 100))
    r, g, b = base_color
    
    c_light = (min(255, int(r * 1.45)), min(255, int(g * 1.45)), min(255, int(b * 1.45)))
    c_mid = (r, g, b)
    c_dark = (max(12, int(r * 0.22)), max(12, int(g * 0.22)), max(12, int(b * 0.22)))
    
    pixels = []
    for y in range(100):
        for x in range(100):
            factor = (x + (99 - y)) / 198.0
            if factor < 0.5:
                t = factor * 2.0
                curr_color = (
                    int(c_dark[0] * (1 - t) + c_mid[0] * t),
                    int(c_dark[1] * (1 - t) + c_mid[1] * t),
                    int(c_dark[2] * (1 - t) + c_mid[2] * t)
                )
            else:
                t = (factor - 0.5) * 2.0
                curr_color = (
                    int(c_mid[0] * (1 - t) + c_light[0] * t),
                    int(c_mid[1] * (1 - t) + c_light[1] * t),
                    int(c_mid[2] * (1 - t) + c_light[2] * t)
                )
            pixels.append(curr_color)
            
    small_canvas.putdata(pixels)
    return small_canvas.resize((width, height), Image.Resampling.BILINEAR)

def add_rounded_corners(img, radius):
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.size[0], img.size[1]), radius, fill=255)
    img_with_corners = img.copy()
    img_with_corners.putalpha(mask)
    return img_with_corners

def generate_grid_backdrop(genre_name, config):
    canvas_w, canvas_h = 1920, 1080
    background = create_premium_angled_gradient(canvas_w, canvas_h, config["color"])
    
    raw_candidates = get_trending_media(config)
    scoring_keywords = set(config.get("scoring_keywords", []))
    
    processed_candidates = []
    seen_ids = set()
    
    for item in raw_candidates:
        composite_key = f"{item['media_type']}_{item['id']}"
        if composite_key in seen_ids or item.get("adult"): continue
        if not config.get("override_lang", False) and item.get("original_language", "") not in ALLOWED_LANGUAGES: continue
        if genre_name == "animation" and item.get("original_language", "") not in WESTERN_LANGUAGES: continue
        
        keywords = get_media_keywords(item["media_type"], item["id"])
        if keywords.intersection(BANNED_KEYWORDS): continue
        if genre_name == "famille" and keywords.intersection(FAMILY_BANNED_KEYWORDS): continue
        
        score = len(keywords.intersection(scoring_keywords)) * 55
        score += min(item.get("popularity", 0) / 2.5, 140)
        
        if genre_name != "animation-japonaise" and item.get("original_language", "") in WESTERN_LANGUAGES:
            score += 75
            
        processed_candidates.append((score, item))
        seen_ids.add(composite_key)
        
    processed_candidates.sort(key=lambda x: x[0], reverse=True)
    
    # Configuration précise de la mosaïque (8x9 = 72 vignettes uniques requises)
    cell_w, cell_h = 266, 150  
    cols, rows = 8, 9
    max_vignettes = cols * rows
    
    if len(processed_candidates) < max_vignettes:
        print(f" [ALERTE] Seulement {len(processed_candidates)} médias uniques trouvés pour {genre_name}.")
        # Mode secours ultime : Si TMDB renvoie vraiment trop peu de résultats uniques (très rare désormais)
        grid_items = list(processed_candidates)
        if grid_items:
            while len(grid_items) < max_vignettes:
                grid_items.extend(processed_candidates)
            grid_items = grid_items[:max_vignettes]
        else:
            print(f" [ERREUR CRITIQUE] Aucun média trouvé pour {genre_name}. Saut.")
            return
    else:
        grid_items = processed_candidates[:max_vignettes]

    grid_w, grid_h = 2600, 1600
    grid_layer = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))
    
    # Initialisation du calque d'ombres portées sous les cartes (Effet Premium)
    shadow_layer_grid = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))
    s_draw_grid = ImageDraw.Draw(shadow_layer_grid)
    
    # Correction majeure : Calcul et centrage géométrique parfait de la mosaïque brute
    total_grid_w = cols * cell_w + (cols - 1) * CARD_GAP
    total_grid_h = rows * cell_h + (rows - 1) * CARD_GAP
    start_x = (grid_w - total_grid_w) // 2
    start_y = (grid_h - total_grid_h) // 2
    
    count = 0
    for entry in grid_items:
        item = entry[1]
        backdrop_path = get_textless_backdrop(item["media_type"], item["id"], item["backdrop_path"])
        url = f"https://image.tmdb.org/t/p/w500{backdrop_path}"
        
        try:
            res = requests.get(url, stream=True, timeout=10)
            if res.status_code == 200:
                vignette = Image.open(res.raw).convert("RGB")
                vignette = ImageOps.fit(vignette, (cell_w, cell_h), method=Image.Resampling.LANCZOS)
                vignette = add_rounded_corners(vignette, radius=CORNER_RADIUS)
                
                r_idx = count // cols
                c_idx = count % cols
                
                x = start_x + c_idx * (cell_w + CARD_GAP)
                y = start_y + r_idx * (cell_h + CARD_GAP)
                
                # Tracé des rectangles d'ombres (décalés vers le bas droit)
                s_draw_grid.rounded_rectangle(
                    (x + 4, y + 8, x + cell_w + 4, y + cell_h + 8), 
                    radius=CORNER_RADIUS, 
                    fill=(0, 0, 0, 150)
                )
                
                grid_layer.paste(vignette, (x, y), vignette)
                count += 1
        except:
            continue

    print(f" -> Mosaïque {genre_name} : {count}/{max_vignettes} médias valides incrustés.")
    
    # Application du flou gaussien sur le calque d'ombrage pour un rendu vaporeux haut de gamme
    shadow_layer_grid = shadow_layer_grid.filter(ImageFilter.GaussianBlur(10))
    
    # Fusion de l'ombre portée derrière la mosaïque réelle
    grid_composite = Image.alpha_composite(shadow_layer_grid, grid_layer)
    
    # Application de la rotation à -10°
    rotated_grid = grid_composite.rotate(TILT_ANGLE, resample=Image.Resampling.BILINEAR, expand=False)
    
    # Découpage chirurgical au format 1920x1080 centré
    offset_x = (grid_w - canvas_w) // 2
    offset_y = (grid_h - canvas_h) // 2
    crop_box = (offset_x, offset_y, offset_x + canvas_w, offset_y + canvas_h)
    final_grid_cropped = rotated_grid.crop(crop_box)
    
    # Application sur le fond dégradé diagonal
    background.paste(final_grid_cropped, (0, 0), final_grid_cropped)
    final_output = background.convert("RGB")
    
    # Sauvegardes finales nettoyées
    final_output.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
    final_output.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Génération Hebdomadaire Backdrops : {config['label']} ---")
        generate_grid_backdrop(genre_name, config)
    print("\n[SUCCESS] Vos grilles de backdrops pures sans texte sont générées, centrées et stabilisées.")

if __name__ == "__main__":
    main()
    

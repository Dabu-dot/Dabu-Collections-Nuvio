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

# Configuration des genres - Palette Premium bicolore cohérente pour dégradé diagonal
GENRES_CONFIG = {
    "action": {
        "label": "Action", 
        "color_dark": (110, 10, 15),     # Rouge Profond (Bas-Gauche)
        "color_light": (245, 75, 85),    # Corail Éclatant (Haut-Droite)
        "movie_genre": 28, "tv_genre": 10759, "extra": "&without_genres=16", 
        "scoring_keywords": [3930, 6054, 12993, 9951, 8440, 188955, 226499, 83, 312, 779, 4565, 14955, 853, 9665, 10044]
    },
    "animation-japonaise": {
        "label": "Animation Japonaise", 
        "color_dark": (50, 15, 110),     # Violet Nuit
        "color_light": (210, 120, 250),  # Mauve Électrique
        "movie_genre": 16, "tv_genre": 16, "extra": "&with_original_language=ja", "prefer_tv": True, "override_lang": True, 
        "scoring_keywords": [210024, 13141, 207826]
    },
    "animation": {
        "label": "Animation", 
        "color_dark": (10, 50, 140),     # Bleu Roi
        "color_light": (0, 220, 255),    # Cyan Lumineux
        "movie_genre": 16, "tv_genre": 16, 
        "extra": "&without_genres=99&without_original_language=ja|ko|zh&without_keywords=210024|287513",
        "min_popularity": 80,
        "scoring_keywords": [272909, 7376, 278823, 234183, 179411, 234662, 290589, 297442, 339048, 366485]
    },
    "aventure": {
        "label": "Aventure", 
        "color_dark": (10, 80, 50),      # Vert Émeraude
        "color_light": (245, 140, 25),   # Orange Ambré
        "movie_genre": 12, "tv_genre": 10759, "extra": "&without_genres=16", 
        "scoring_keywords": [195114, 161176, 818, 4152, 170362, 210246, 10364, 41586, 6956, 269233]
    },
    "comedie": {
        "label": "Comédie", 
        "color_dark": (140, 60, 10),     # Terre Cuite
        "color_light": (250, 205, 35),    # Jaune Solaire
        "movie_genre": 35, "tv_genre": 35, "extra": "&without_genres=16", 
        "scoring_keywords": [8201, 9755, 9964, 375047, 6241, 9253]
    },
    "crime": {
        "label": "Crime", 
        "color_dark": (40, 45, 60),      # Ardoise Sombre
        "color_light": (160, 175, 195),  # Gris Argenté Lumineux
        "movie_genre": 80, "tv_genre": 80, "extra": "&without_genres=16", 
        "scoring_keywords": [2095, 9748, 181644, 157241, 206958, 268067, 703, 5340, 6149, 9826, 155790, 207046]
    },
    "documentaire": {
        "label": "Documentaire", 
        "color_dark": (15, 80, 40),      # Vert Forêt
        "color_light": (80, 230, 135),    # Vert Menthe Éclatant
        "movie_genre": 99, "tv_genre": 99, "extra": "&without_genres=16", 
        "scoring_keywords": [221355, 305903, 343303, 284176]
    },
    "drame": {
        "label": "Drame", 
        "color_dark": (10, 60, 120),     # Bleu Nuit
        "color_light": (110, 200, 250),  # Bleu Horizon
        "movie_genre": 18, "tv_genre": 18, "extra": "&without_genres=16", 
        "scoring_keywords": []
    },
    "famille": {
        "label": "Famille", 
        "color_dark": (110, 20, 100),    # Byzantium Sombre
        "color_light": (250, 140, 220),  # Rose Orchidée
        "movie_genre": 10751, "tv_genre": 10751, "extra": "&without_genres=16", 
        "scoring_keywords": []
    },
    "fantastique": {
        "label": "Fantastique", 
        "color_dark": (80, 30, 140),     # Améthyste
        "color_light": (200, 135, 255),  # Mauve Lumineux
        "movie_genre": 14, "tv_genre": 10765, "extra": "&without_genres=16", 
        "scoring_keywords": []
    },
    "guerre": {
        "label": "Guerre", 
        "color_dark": (60, 55, 50),      # Kaki Foncé
        "color_light": (170, 165, 155),  # Pierre
        "movie_genre": 10752, "tv_genre": 10768, "extra": "&without_genres=16", 
        "scoring_keywords": []
    },
    "histoire": {
        "label": "Histoire", 
        "color_dark": (80, 45, 25),      # Bronze
        "color_light": (200, 150, 110),  # Sienne Dorée
        "movie_genre": 36, "tv_genre": 10768, "extra": "&without_genres=16", 
        "scoring_keywords": []
    },
    "horreur": {
        "label": "Horreur", 
        "color_dark": (50, 10, 10),      # Sang Profond
        "color_light": (240, 50, 50),     # Écarlate Vif
        "movie_genre": 27, "tv_genre": 27, "extra": "&without_genres=16&with_keywords=3358|9748|6152", 
        "scoring_keywords": []
    },
    "romance": {
        "label": "Romance", 
        "color_dark": (120, 25, 60),     # Rubis Sombre
        "color_light": (250, 140, 170),  # Rose Poudré
        "movie_genre": 10749, "tv_genre": 10749, "extra": "&without_genres=16&without_original_language=ko|ja|zh", 
        "scoring_keywords": []
    },
    "science-fiction": {
        "label": "Science-Fiction", 
        "color_dark": (10, 40, 110),     # Outremer Profond
        "color_light": (30, 215, 240),    # Turquoise Spatial
        "movie_genre": 878, "tv_genre": 10765, "extra": "&without_genres=16&with_keywords=4565|9882", 
        "scoring_keywords": []
    },
    "thriller": {
        "label": "Thriller", 
        "color_dark": (10, 65, 50),      # Sarcelle Sombre
        "color_light": (50, 215, 150),    # Néon Menthe
        "movie_genre": 53, "tv_genre": 80, "extra": "&without_genres=16&with_keywords=9826|10123", 
        "scoring_keywords": []
    },
    "western": {
        "label": "Western", 
        "color_dark": (110, 40, 15),     # Sienne Brûlée
        "color_light": (245, 145, 60),    # Ambre Crépuscule
        "movie_genre": 37, "tv_genre": 37, "extra": "&without_genres=16", 
        "scoring_keywords": []
    }
}

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
        
    print(f"   Pool éligible après filtrage : {len(filtered_pool)} œuvres.")
    
    if len(filtered_pool) > 50:
        return random.sample(filtered_pool, 50)
    return filtered_pool

def get_keyword_id_by_name(name):
    try:
        data = tmdb_api_call("/search/keyword", {"query": name})
        if data and "results" in data:
            for kw in data["results"]:
                if kw.get("name", "").lower() == name.lower():
                    return kw["id"]
    except Exception:
        pass
    return None

def get_media_keywords(media_type, media_id):
    try:
        endpoint = f"/{media_type}/{media_id}/keywords"
        data = tmdb_api_call(endpoint)
        if not data:
            return set()
        keyword_list = data.get("keywords") or data.get("results") or []
        return {kw["id"] for kw in keyword_list if "id" in kw}
    except Exception:
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

def analyze_and_score_backdrop(bg, item, downloaded_image=None):
    score = 40
    width = bg.get("width", 0)
    popularity = item.get("popularity", 0)
    vote_count = bg.get("vote_count", 0)
    vote_average = item.get("vote_average", 0) # Utilisation intelligente de la note communautaire globale du film
    
    # VALORISATION ACCENTUÉE DE LA NOTE COMMUNAUTAIRE (TMDB)
    if vote_count > 0 or vote_average > 0:
        score += int(vote_average * 5) # Une note de 8/10 donne +40 points immédiats pour faire remonter les chefs-d'œuvre
        if vote_count >= 10: score += 15
    else:
        score -= 20

    release_date_str = item.get("release_date") or item.get("first_air_date") or ""
    if release_date_str:
        try:
            year = datetime.strptime(release_date_str, "%Y-%m-%d").year
            if year >= 2022: score += 15
            elif year >= 2015: score += 5
            elif year < 2005: score -= 15
        except ValueError:
            pass

    if width >= 3840: score += 15
    elif width >= 1920: score += 10
    if popularity > 150: score += 10
        
    if downloaded_image:
        try:
            gray_img = downloaded_image.convert("L").resize((480, 270), Image.Resampling.BILINEAR)
            arr = np.array(gray_img, dtype=np.float32)
            grad_x = np.diff(arr, axis=1)
            grad_y = np.diff(arr, axis=0)
            edge_variance = np.var(grad_x) + np.var(grad_y)
            
            if edge_variance > 140: score += 15
            elif edge_variance < 55: score -= 20
        except Exception:
            pass
            
    return score

def generate_diagonal_gradient(width, height, color_dark, color_light):
    """Génère un dégradé parfait en diagonale (Bas-Gauche vers Haut-Droite)"""
    # Création d'un masque linéaire via numpy
    y_indices, x_indices = np.indices((height, width), dtype=np.float32)
    
    # Calcul de la projection diagonale : Bas-Gauche (0, height) vaut 0.0, Haut-Droite (width, 0) vaut 1.0
    diagonal_mask = (x_indices / float(width) + (1.0 - y_indices / float(height))) / 2.0
    diagonal_mask = np.clip(diagonal_mask, 0.0, 1.0)
    
    # Interpolation de la couleur sur les 3 canaux RVB
    gradient_arr = np.zeros((height, width, 3), dtype=np.uint8)
    for i in range(3):
        channel = color_dark[i] + diagonal_mask * (color_light[i] - color_dark[i])
        gradient_arr[..., i] = np.clip(channel, 0, 255).astype(np.uint8)
        
    return Image.fromarray(gradient_arr, "RGB")

def apply_apple_tv_duotone(img, color_dark, color_light):
    """Applique le dégradé diagonal sans détruire ni cramer l'image originale (Mode Incrustation/Luminosité)"""
    width, height = img.size
    
    # 1. Génération du fond avec le dégradé diagonal pur demandé (Bas-Gauche -> Haut-Droite)
    gradient_background = generate_diagonal_gradient(width, height, color_dark, color_light)
    
    # 2. Conversion de l'image de film d'origine en Niveaux de Gris (Luminance structurelle)
    # On adoucit légèrement le contraste pour éviter absolument l'effet "brûlé"
    gray_structure = ImageOps.autocontrast(img.convert("L"), cutoff=2)
    gray_structure = ImageEnhance.Contrast(gray_structure).enhance(0.95) # Lissage anti-burn
    
    # 3. FUSION PREMIUM NON DESTRUCTIVE (Hard Light / Luminosity blend equivalent)
    # On utilise l'image en niveaux de gris comme un masque de fusion au dessus de notre superbe dégradé.
    # Les zones claires laisseront passer la couleur claire, les ombres ancreront la couleur sombre.
    # L'image finale garde 100% de sa lisibilité sans aucune distorsion de pixel.
    final_duotone = Image.composite(gradient_background, img.convert("RGB"), gray_structure)
    
    # Un léger mélange (Blend) pour laisser transparaître un très léger pourcentage du teint d'origine (donne un aspect ultra-cinéma)
    result = Image.blend(gradient_background, final_duotone, alpha=0.82)
    return result

def finalize_landscape_banner(img, label, color_dark, color_light):
    img = ImageOps.fit(img, (1920, 1080), method=Image.Resampling.LANCZOS)
    img = apply_apple_tv_duotone(img, color_dark, color_light)
    
    img_rgba = img.convert("RGBA")
    
    # Dégradé progressif vers le noir sur le tiers inférieur pour assurer la lisibilité de la typo
    gradient = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(450, 1080):
        alpha = int(((y - 450) / 630) ** 1.6 * 245)
        g_draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
        
    img_with_gradient = Image.alpha_composite(img_rgba, gradient)

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
    
    final_img = Image.alpha_composite(img_with_gradient, shadow_layer)
    final_img = Image.alpha_composite(final_img, text_layer)
    
    return final_img.convert("RGB")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    history = load_and_clean_history()
    excluded_keys = set(history.keys())
    
    print(f"Chargement de l'historique : {len(excluded_keys)} œuvres verrouillées.")

    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Sélection pour le Genre : {config['label']} ---")
        
        candidates_pool = get_trending_media_for_genre(config, excluded_keys)
        if not candidates_pool:
            print(f" [CONSERVATION] Aucun candidat éligible trouvé pour {config['label']}.")
            continue
            
        scoring_keywords = set(config.get("scoring_keywords", []))
        scored_candidates = []
        
        for idx, item in enumerate(candidates_pool):
            media_type = item["media_type"]
            media_id = item["id"]
            keywords = get_media_keywords(media_type, media_id)
            matching_keywords = keywords.intersection(scoring_keywords)
            tag_score = len(matching_keywords) * 10
            
            scored_candidates.append({
                "item": item,
                "score": tag_score
            })
            
        if not scored_candidates:
            continue
            
        scored_candidates.sort(key=lambda x: (x["score"], x["item"].get("popularity", 0)), reverse=True)
        winner_data = scored_candidates[0]
        selected_media = winner_data["item"]
        
        media_id = selected_media["id"]
        media_type = selected_media["media_type"]
        composite_key = f"{media_type}_{media_id}"
        media_title = selected_media.get("title") or selected_media.get("name")
        
        print(f" -> Vainqueur sélectionné : {media_title}")
        
        backdrops_list = get_best_textless_backdrops(media_type, media_id, selected_media["backdrop_path"])
        
        scored_backdrops = []
        for bg in backdrops_list:
            img_url = f"https://image.tmdb.org/t/p/original{bg['file_path']}"
            try:
                res = requests.get(img_url, stream=True, timeout=10)
                if res.status_code == 200:
                    raw_img = Image.open(res.raw).convert("RGB")
                    score = analyze_and_score_backdrop(bg, selected_media, downloaded_image=raw_img)
                    scored_backdrops.append({"image": raw_img, "score": score, "path": bg["file_path"]})
            except Exception:
                continue
                
        if scored_backdrops:
            scored_backdrops.sort(key=lambda x: x["score"], reverse=True)
            winner_bg = scored_backdrops[0]
            
            final_banner = finalize_landscape_banner(winner_bg["image"], config["label"], config["color_dark"], config["color_light"])
            
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            RUN_PROCESSED_IDS.add(composite_key)
            history[composite_key] = {
                "title": media_title,
                "genre": genre_name,
                "date": datetime.now().strftime("%Y-%m-%d")
            }

    sorted_history = dict(sorted(history.items(), key=lambda item: item[1]['date'], reverse=True))
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_history, f, ensure_ascii=False, indent=4)
        
    print("\n[SUCCESS] Déploiement terminé. Nouveau modèle de fusion de dégradé diagonal sans perte actif.")

if __name__ == "__main__":
    main()

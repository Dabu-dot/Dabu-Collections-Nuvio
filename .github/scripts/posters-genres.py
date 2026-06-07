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

# Langues occidentales populaires autorisées (Coréen et Japonais isolés à leurs genres dédiés)
ALLOWED_LANGUAGES = {"fr", "en", "es", "de", "it"}

# Configuration chirurgicale des genres (Filtres Live-Action stricts, mots-clés et exclusions d'anime)
# ID Mots-clés TMDB utilisés : Anime (210024), Animation 3D (156157), Stylisé (296180)
GENRES_CONFIG = {
    "action": {"label": "Action", "color": (255, 90, 0), "movie_genre": 28, "tv_genre": 10759, "extra": "&without_genres=16&with_keywords=9715|9717|1556"},
    "animation-japonaise": {"label": "Animation Japonaise", "color": (255, 0, 128), "movie_genre": 16, "tv_genre": 16, "extra": "&with_original_language=ja", "prefer_tv": True, "override_lang": True},
    "animation": {
        "label": "Animation", 
        "color": (0, 200, 255), 
        "movie_genre": 16, 
        "tv_genre": 16, 
        # Exclusion totale des mots-clés liés aux productions/styles animés asiatiques et des langues d'Asie
        "extra": "&without_genres=99&without_original_language=ja|ko|zh&without_keywords=210024|287513",
        "min_popularity": 80 # Seuil haut pour chasser les petits projets indépendants ou d'importation
    },
    "aventure": {"label": "Aventure", "color": (245, 158, 11), "movie_genre": 12, "tv_genre": 10759, "extra": "&without_genres=16&with_keywords=4814|1563"},
    "comedie": {"label": "Comédie", "color": (250, 204, 21), "movie_genre": 35, "tv_genre": 35, "extra": "&without_genres=16"},
    "crime": {"label": "Crime", "color": (107, 114, 128), "movie_genre": 80, "tv_genre": 80, "extra": "&without_genres=16&with_keywords=9826|10331"},
    "documentaire": {
        "label": "Documentaire", 
        "color": (34, 197, 94), 
        "movie_genre": 99, 
        "tv_genre": 99,
        "extra": "&with_keywords=221355|305903|343303|284176&without_genres=16"
    },
    "drame": {"label": "Drame", "color": (14, 165, 233), "movie_genre": 18, "tv_genre": 18, "extra": "&without_genres=16"},
    "famille": {"label": "Famille", "color": (217, 70, 239), "movie_genre": 10751, "tv_genre": 10751, "extra": "&without_genres=16"},
    "fantastique": {"label": "Fantastique", "color": (168, 85, 247), "movie_genre": 14, "tv_genre": 10765, "extra": "&without_genres=16"},
    "guerre": {"label": "Guerre", "color": (120, 113, 108), "movie_genre": 10752, "tv_genre": 10768, "extra": "&without_genres=16"},
    "histoire": {"label": "Histoire", "color": (180, 83, 9), "movie_genre": 36, "tv_genre": 10768, "extra": "&without_genres=16"},
    "horreur": {"label": "Horreur", "color": (239, 68, 68), "movie_genre": 27, "tv_genre": 27, "extra": "&without_genres=16&with_keywords=3358|9748|6152"},
    "romance": {"label": "Romance", "color": (244, 63, 94), "movie_genre": 10749, "tv_genre": 10749, "extra": "&without_genres=16&without_original_language=ko|ja|zh"}, # Adieu la pollution de shows TV asiatiques non-textless
    "science-fiction": {"label": "Science-Fiction", "color": (6, 182, 212), "movie_genre": 878, "tv_genre": 10765, "extra": "&without_genres=16&with_keywords=4565|9882"},
    "thriller": {"label": "Thriller", "color": (29, 78, 216), "movie_genre": 53, "tv_genre": 80, "extra": "&without_genres=16&with_keywords=9826|10123"},
    "western": {"label": "Western", "color": (214, 100, 42), "movie_genre": 37, "tv_genre": 37, "extra": "&without_genres=16"}
}

RUN_PROCESSED_IDS = set()

def tmdb_api_call(endpoint, params=None):
    """Effectue un appel GET vers TMDB sécurisé avec politique de retries"""
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
    """Charge le JSON et nettoie les entrées plus vieilles que 14 jours"""
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
    """Récupère et filtre drastiquement le pool de candidats cinéma/série d'un genre"""
    movie_pool = []
    tv_pool = []
    
    # 1. Collecte de Films
    movie_url = f"/discover/movie?sort_by=popularity.desc&with_genres={config['movie_genre']}{config.get('extra', '')}"
    try:
        movie_data = tmdb_api_call(movie_url)
        for item in movie_data.get("results", []):
            if item.get("backdrop_path"):
                item["media_type"] = "movie"
                movie_pool.append(item)
    except Exception as e:
        print(f"      Alerte discover movie: {e}")

    # 2. Collecte de Séries (TV)
    tv_url = f"/discover/tv?sort_by=popularity.desc&with_genres={config['tv_genre']}{config.get('extra', '')}"
    try:
        tv_data = tmdb_api_call(tv_url)
        for item in tv_data.get("results", []):
            if item.get("backdrop_path"):
                item["media_type"] = "tv"
                tv_pool.append(item)
    except Exception as e:
        print(f"      Alerte discover tv: {e}")

    # Structuration du pool selon les préférences graphiques (ex: séries pour anime)
    combined_pool = tv_pool + movie_pool if config.get("prefer_tv", False) else movie_pool + tv_pool

    filtered_pool = []
    min_pop_threshold = config.get("min_popularity", 25) # Par défaut popularité min de 25

    for item in combined_pool:
        lang = item.get("original_language", "")
        composite_key = f"{item['media_type']}_{item['id']}"
        popularity = item.get("popularity", 0)
        
        if popularity < min_pop_threshold:
            continue
        if not config.get("override_lang", False) and lang not in ALLOWED_LANGUAGES:
            continue
        if composite_key in excluded_keys or composite_key in RUN_PROCESSED_IDS:
            continue
            
        filtered_pool.append(item)
        
    filtered_pool.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return filtered_pool[:20]

def get_best_textless_backdrops(media_type, media_id, fallback_path):
    """Interroge la section d'images TMDB. Filtre par vote_count pour éjecter les captures TV polluées de texte"""
    try:
        data = tmdb_api_call(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        backdrops = data.get("backdrops", [])
        if not backdrops:
            return [{"file_path": fallback_path, "width": 1920, "vote_count": 5, "vote_average": 5.0}]
            
        # Tri : On exige d'abord un volume de votes pour garantir la validation communautaire (Vrai Textless)
        backdrops.sort(key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)), reverse=True)
        return backdrops[:5]
    except Exception:
        return [{"file_path": fallback_path, "width": 1920, "vote_count": 5, "vote_average": 5.0}]

def analyze_and_score_backdrop(bg, item):
    """Calcule le score de qualité globale en favorisant la modernité et en pénalisant les images douteuses"""
    score = 40
    width = bg.get("width", 0)
    popularity = item.get("popularity", 0)
    vote_count = bg.get("vote_count", 0)
    
    # Élimination des fonds pollués (Captures d'écrans amateurs sans aucun vote communautaire)
    if vote_count == 0:
        score -= 30

    # Valorisation de la modernité (Élimine le rendu vieillot / daté)
    release_date_str = item.get("release_date") or item.get("first_air_date") or ""
    if release_date_str:
        try:
            year = datetime.strptime(release_date_str, "%Y-%m-%d").year
            if year >= 2022: score += 35      # Ultra récent / Blockbuster moderne
            elif year >= 2015: score += 15    # Propre
            elif year < 2005: score -= 20     # Malus rétro pour forcer le renouvellement moderne
        except ValueError:
            pass

    if width >= 3840: score += 15
    elif width >= 1920: score += 10
        
    if popularity > 150: score += 15
        
    return score

def apply_apple_tv_duotone(img, target_color):
    """Génère un filtre Duotone cinéma calqué sur le style Apple TV"""
    gray = img.convert("L")
    gray_np = np.array(gray)
    
    base_dark = np.array([10, 14, 22])  # Fond sombre d'interface épurée
    target_light = np.array(target_color)
    
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
        
    return Image.fromarray(duotone)

def finalize_landscape_banner(img, label, target_color):
    """Redimensionne en 16:9, applique le Duotone, le dégradé bas, l'ombre diffuse et le texte XXL espacé"""
    # Recadrage intelligent et forçage du format 16:9 paysage
    img = ImageOps.fit(img, (1920, 1080), method=Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.18)
    img = apply_apple_tv_duotone(img, target_color)
    
    # Création d'un dégradé de noir cinématique sur la moitié inférieure
    gradient = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(450, 1080):
        alpha = int(((y - 450) / 630) ** 2.0 * 250)
        g_draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), gradient)

    # Calques de dessin
    text_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    
    t_draw = ImageDraw.Draw(text_layer)
    s_draw = ImageDraw.Draw(shadow_layer)
    
    # Augmentation de la taille de police pour lisibilité TV/Mobile lointaine (135px)
    font_size = 135
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", font_size)
    except IOError:
        font = ImageFont.load_default()

    # Padding de sécurité pour décoller le texte des bordures physiques de l'image
    padding_left = 130
    padding_bottom = 140
    max_text_width = 1920 - (padding_left * 2) # Largeur max utile restante

    # Wrapping intelligent multi-lignes
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

    # Agencement des blocs de lignes et gestion de la hauteur totale
    line_spacing = 18
    line_height = font_size - 15
    total_text_height = (len(lines) * line_height) + ((len(lines) - 1) * line_spacing)
    
    # Calcul de la coordonnée de départ y (Le texte remonte proprement si multi-lignes)
    base_y = (1080 - padding_bottom - line_height) - (total_text_height - line_height)

    # Écriture sur les calques distincts
    current_y = base_y
    for line in lines:
        # Ombre portée douce (Léger décalage d'arrière-plan)
        s_draw.text((padding_left + 5, current_y + 8), line, fill=(0, 0, 0, 240), font=font)
        # Texte frontal blanc pur
        t_draw.text((padding_left, current_y), line, fill=(255, 255, 255, 255), font=font)
        current_y += line_height + line_spacing

    # Floutage gaussien de l'ombre pour créer un halo d'ombrage ergonomique et premium de loin
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(10))
    
    # Fusion finale
    final_img = Image.alpha_composite(img, shadow_layer)
    final_img = Image.alpha_composite(final_img, text_layer)
    
    return final_img.convert("RGB")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Purge complète du dossier cible avant écriture
    for file in os.listdir(OUTPUT_DIR):
        file_path = os.path.join(OUTPUT_DIR, file)
        if os.path.isfile(file_path):
            os.remove(file_path)
            
    history = load_and_clean_history()
    excluded_keys = set(history.keys())
    
    print(f"Chargement de l'historique : {len(excluded_keys)} œuvres verrouillées pour préservation.")

    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Sélection pour le Genre : {config['label']} ---")
        
        candidates_pool = get_trending_media_for_genre(config, excluded_keys)
        if not candidates_pool:
            print(f" /!\\ Aucun candidat éligible trouvé pour le genre {config['label']}")
            continue
            
        # Tirage parmi le top qualitatif
        selected_media = random.choice(candidates_pool)
        media_id = selected_media["id"]
        media_type = selected_media["media_type"]
        composite_key = f"{media_type}_{media_id}"
        media_title = selected_media.get("title") or selected_media.get("name")
        
        print(f" -> Œuvre validée : {media_title} ({media_type.upper()} - ID: {media_id})")
        
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
            
            # Export des fichiers maîtres
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            RUN_PROCESSED_IDS.add(composite_key)
            history[composite_key] = {
                "title": media_title,
                "genre": genre_name,
                "date": datetime.now().strftime("%Y-%m-%d")
            }
        else:
            print(f" /!\\ Échec : Aucun visuel n'a pu être extrait pour {media_title}")

    # Enregistrement du fichier de persistance JSON
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)
    print("\n[SUCCESS] Déploiement terminé. Règles de padding de sécurité et filtres d'ambiances appliqués.")

if __name__ == "__main__":
    main()

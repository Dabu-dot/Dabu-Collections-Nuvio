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

# Langues occidentales populaires autorisées + Coréen + Japonais
ALLOWED_LANGUAGES = {"fr", "en", "es", "de", "it", "ja", "ko"}

# Configuration des genres avec isolation stricte Animation vs Live-Action
GENRES_CONFIG = {
    "action": {"label": "Action", "color": (255, 90, 0), "movie_genre": 28, "tv_genre": 10759, "extra": "&without_genres=16"},
    "animation-japonaise": {"label": "Animation Japonaise", "color": (255, 0, 128), "movie_genre": 16, "tv_genre": 16, "extra": "&with_original_language=ja", "prefer_tv": True},
    "animation": {"label": "Animation", "color": (0, 200, 255), "movie_genre": 16, "tv_genre": 16, "extra": "&without_genres=99&without_original_language=ja|ko|zh"},
    "aventure": {"label": "Aventure", "color": (245, 158, 11), "movie_genre": 12, "tv_genre": 10759, "extra": "&without_genres=16"},
    "comedie": {"label": "Comédie", "color": (250, 204, 21), "movie_genre": 35, "tv_genre": 35, "extra": "&without_genres=16"},
    "crime": {"label": "Crime", "color": (107, 114, 128), "movie_genre": 80, "tv_genre": 80, "extra": "&without_genres=16"},
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
    "horreur": {"label": "Horreur", "color": (239, 68, 68), "movie_genre": 27, "tv_genre": 27, "extra": "&without_genres=16"},
    "romance": {"label": "Romance", "color": (244, 63, 94), "movie_genre": 10749, "tv_genre": 10749, "extra": "&without_genres=16"},
    "science-fiction": {"label": "Science-Fiction", "color": (6, 182, 212), "movie_genre": 878, "tv_genre": 10765, "extra": "&without_genres=16"},
    "thriller": {"label": "Thriller", "color": (29, 78, 216), "movie_genre": 53, "tv_genre": 80, "extra": "&without_genres=16"},
    "western": {"label": "Western", "color": (214, 100, 42), "movie_genre": 37, "tv_genre": 37, "extra": "&without_genres=16"}
}

RUN_PROCESSED_IDS = set()  # Évite les doublons inter-genres au sein du même run

def tmdb_api_call(endpoint, params=None):
    """Effectue un appel GET vers TMDB avec gestion des retries"""
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
    """Récupère les œuvres tendances associées au genre, triées et filtrées"""
    movie_pool = []
    tv_pool = []
    
    # 1. Collecte Films
    movie_url = f"/discover/movie?sort_by=popularity.desc&with_genres={config['movie_genre']}{config.get('extra', '')}"
    try:
        movie_data = tmdb_api_call(movie_url)
        for item in movie_data.get("results", []):
            if item.get("backdrop_path"):
                item["media_type"] = "movie"
                movie_pool.append(item)
    except Exception as e:
        print(f"      Alerte discover movie: {e}")

    # 2. Collecte Séries (TV)
    tv_url = f"/discover/tv?sort_by=popularity.desc&with_genres={config['tv_genre']}{config.get('extra', '')}"
    try:
        tv_data = tmdb_api_call(tv_url)
        for item in tv_data.get("results", []):
            if item.get("backdrop_path"):
                item["media_type"] = "tv"
                tv_pool.append(item)
    except Exception as e:
        print(f"      Alerte discover tv: {e}")

    # Fusion intelligente ou priorité structurelle (ex: Animation Japonaise)
    combined_pool = []
    if config.get("prefer_tv", False):
        combined_pool = tv_pool + movie_pool  # Les séries passent devant pour le tirage
    else:
        combined_pool = movie_pool + tv_pool

    # Filtrage linguistique, doublons et historique glissant
    filtered_pool = []
    for item in combined_pool:
        lang = item.get("original_language", "")
        composite_key = f"{item['media_type']}_{item['id']}"
        
        if lang not in ALLOWED_LANGUAGES:
            continue
        if composite_key in excluded_keys or composite_key in RUN_PROCESSED_IDS:
            continue
            
        filtered_pool.append(item)
        
    # Tri par popularité décroissante et isolation des 20 meilleurs candidats pour le tirage au sort
    filtered_pool.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return filtered_pool[:20]

def get_best_textless_backdrops(media_type, media_id, fallback_path):
    """Interroge la section d'images TMDB sans langue (null) pour garantir le textless strict"""
    try:
        data = tmdb_api_call(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        backdrops = data.get("backdrops", [])
        if not backdrops:
            return [{"file_path": fallback_path, "width": 1920}]
            
        backdrops.sort(key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)), reverse=True)
        return backdrops[:5]
    except Exception:
        return [{"file_path": fallback_path, "width": 1920}]

def analyze_and_score_backdrop(bg, item):
    """Calcule le score d'un asset basé sur sa définition native, la popularité, et favorise le récent"""
    score = 40
    width = bg.get("width", 0)
    popularity = item.get("popularity", 0)
    
    # Extraire l'année de sortie pour valoriser la modernité des visuels
    release_date_str = item.get("release_date") or item.get("first_air_date") or ""
    if release_date_str:
        try:
            year = datetime.strptime(release_date_str, "%Y-%m-%d").year
            if year >= 2020: score += 30      # Très récent, bonus maximum
            elif year >= 2012: score += 15    # Moderne
            elif year < 2000: score -= 15     # Malus sur les vieux contenus rétro ou datés
        except ValueError:
            pass

    if width >= 3840: score += 15
    elif width >= 1920: score += 10
        
    if popularity > 120: score += 15
    elif popularity > 40: score += 5
        
    return score

def apply_apple_tv_duotone(img, target_color):
    """Génère un rendu Duotone contrasté calqué sur l'identité Apple TV"""
    gray = img.convert("L")
    gray_np = np.array(gray)
    
    base_dark = np.array([12, 16, 26])  # Teinte de fond sombre d'interface
    target_light = np.array(target_color)
    
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
        
    return Image.fromarray(duotone)

def finalize_landscape_banner(img, label, target_color):
    """Force le cadrage 16:9, applique le style Apple TV, l'ombre portée douce et le texte XXL dynamique"""
    # Recadrage et redimensionnement strict en 1920x1080
    img = ImageOps.fit(img, (1920, 1080), method=Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = apply_apple_tv_duotone(img, target_color)
    
    # Dégradé cinématique inférieur
    gradient = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(500, 1080):
        alpha = int(((y - 500) / 580) ** 2.0 * 245)
        g_draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), gradient)

    # Préparation du calque de texte et d'ombre douce portée
    text_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    
    t_draw = ImageDraw.Draw(text_layer)
    s_draw = ImageDraw.Draw(shadow_layer)
    
    # Chargement de la police SF Pro Display Bold à taille augmentée (110px)
    font_size = 110
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", font_size)
    except IOError:
        font = ImageFont.load_default()

    # Découpage et wrapping intelligent multi-lignes si le titre est trop long (seuil à 1740px)
    max_text_width = 1740
    words = label.split(" ")
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        w = t_draw.textlength(test_line, font=font)
        if w <= max_text_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    # Calcul de la hauteur totale et remontée automatique du point de départ y si double ligne
    line_spacing = 15
    line_height = font_size - 10
    total_text_height = (len(lines) * line_height) + ((len(lines) - 1) * line_spacing)
    
    base_y = 930 - (total_text_height - line_height)
    margin_x = 95

    # Écriture des lignes sur leurs calques respectifs (Ombre douce floutée d'un côté, texte blanc de l'autre)
    current_y = base_y
    for line in lines:
        # Ombre portée structurelle (légèrement décalée vers le bas)
        s_draw.text((margin_x + 4, current_y + 6), line, fill=(0, 0, 0, 220), font=font)
        # Texte de face blanc épuré
        t_draw.text((margin_x, current_y), line, fill=(255, 255, 255, 255), font=font)
        current_y += line_height + line_spacing

    # Application d'un flou gaussien sur le calque d'ombre pour un effet diffus premium (pas de contours durs)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(8))
    
    # Assemblage final par transparence
    final_img = Image.alpha_composite(img, shadow_layer)
    final_img = Image.alpha_composite(final_img, text_layer)
    
    return final_img.convert("RGB")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Purge totale du dossier d'images avant de travailler
    for file in os.listdir(OUTPUT_DIR):
        file_path = os.path.join(OUTPUT_DIR, file)
        if os.path.isfile(file_path):
            os.remove(file_path)
            
    history = load_and_clean_history()
    excluded_keys = set(history.keys())
    
    print(f"Chargement de l'historique : {len(excluded_keys)} œuvres verrouillées pour préservation.")

    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Sélection pour le Genre : {config['label']} ---")
        
        # Identification des œuvres disponibles
        candidates_pool = get_trending_media_for_genre(config, excluded_keys)
        if not candidates_pool:
            print(f" /!\\ Aucun candidat disponible pour le genre {config['label']}")
            continue
            
        # Tirage au sort parmi les meilleurs candidats
        selected_media = random.choice(candidates_pool)
        media_id = selected_media["id"]
        media_type = selected_media["media_type"]
        composite_key = f"{media_type}_{media_id}"
        media_title = selected_media.get("title") or selected_media.get("name")
        
        print(f" -> Œuvre choisie : {media_title} ({media_type.upper()} - ID: {media_id})")
        
        # Récupération et notation des 5 meilleurs backdrops textless stricts
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
            # Élection du meilleur backdrop parmi les candidats testés
            scored_backdrops.sort(key=lambda x: x["score"], reverse=True)
            winner_bg = scored_backdrops[0]
            
            print(f"   ==> Gagnant sélectionné (Score: {winner_bg['score']}/100) | Image: {winner_bg['path']}")
            
            # Finalisation graphique
            final_banner = finalize_landscape_banner(winner_bg["image"], config["label"], config["color"])
            
            # Sauvegardes JPEG & WEBP
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            # Mise à jour des index d'exclusion pour bloquer l'œuvre pendant 14 jours
            RUN_PROCESSED_IDS.add(composite_key)
            history[composite_key] = {
                "title": media_title,
                "genre": genre_name,
                "date": datetime.now().strftime("%Y-%m-%d")
            }
        else:
            print(f" /!\\ Échec : Impossible de télécharger les visuels de {media_title}")

    # Écriture finale de l'historique mis à jour sur GitHub
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)
    print("\n[SUCCESS] Script exécuté avec succès. Prise en charge multi-lignes et filtres stricts appliqués.")

if __name__ == "__main__":
    main()

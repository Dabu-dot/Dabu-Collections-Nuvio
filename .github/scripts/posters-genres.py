import os
import sys
import time
import requests
from datetime import datetime, timedelta
from urllib.parse import parse_qsl
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

# Configuration hybride enrichie (Vague 1)
GENRES_CONFIG = {
    "action": {
        "label": "ACTION", 
        "color": (255, 90, 0),
        "requests": ["movie:with_genres=28&sort_by=popularity.desc", "tv:with_genres=10759&sort_by=popularity.desc"]
    },
    "animation-japonaise": {
        "label": "ANIMATION JAPONAISE", 
        "color": (255, 0, 128),
        "requests": ["movie:with_genres=16&with_keywords=210024,13141,207826&sort_by=popularity.desc", "tv:with_genres=16&with_keywords=210024,13141,207826&sort_by=popularity.desc"]
    }, 
    "animation": {
        "label": "ANIMATION", 
        "color": (0, 200, 255),
        "requests": ["movie:with_genres=16&without_genres=99&sort_by=popularity.desc", "tv:with_genres=16&without_genres=99&sort_by=popularity.desc"]
    }, 
    "aventure": {
        "label": "AVENTURE", 
        "color": (245, 158, 11),
        "requests": ["movie:with_genres=12&sort_by=popularity.desc", "tv:with_genres=10759&sort_by=popularity.desc"]
    },
    "comedie": {
        "label": "COMÉDIE", 
        "color": (250, 204, 21),
        "requests": ["movie:with_genres=35&sort_by=popularity.desc", "tv:with_genres=35&sort_by=popularity.desc"]
    },
    "crime": {
        "label": "CRIME", 
        "color": (107, 114, 128),
        "requests": ["movie:with_genres=80&sort_by=popularity.desc", "tv:with_genres=80&sort_by=popularity.desc"]
    },
    "drame": {"label": "DRAME", "color": (14, 165, 233), "requests": ["movie:with_genres=18&sort_by=popularity.desc", "tv:with_genres=18&sort_by=popularity.desc"]},
    "famille": {"label": "FAMILLE", "color": (217, 70, 239), "requests": ["movie:with_genres=10751&sort_by=popularity.desc", "tv:with_genres=10751&sort_by=popularity.desc"]},
    "fantastique": {"label": "FANTASTIQUE", "color": (168, 85, 247), "requests": ["movie:with_genres=14&sort_by=popularity.desc", "tv:with_genres=10765&sort_by=popularity.desc"]},
    "guerre": {"label": "GUERRE", "color": (120, 113, 108), "requests": ["movie:with_genres=10752&sort_by=popularity.desc", "tv:with_genres=10768&sort_by=popularity.desc"]},
    "histoire": {"label": "HISTOIRE", "color": (180, 83, 9), "requests": ["movie:with_genres=36&sort_by=popularity.desc", "tv:with_genres=10768&sort_by=popularity.desc"]},
    "horreur": {"label": "HORREUR", "color": (239, 68, 68), "requests": ["movie:with_genres=27&sort_by=popularity.desc", "tv:with_genres=27&sort_by=popularity.desc"]},
    "romance": {"label": "ROMANCE", "color": (244, 63, 94), "requests": ["movie:with_genres=10749&sort_by=popularity.desc", "tv:with_genres=10749&sort_by=popularity.desc"]},
    "science-fiction": {"label": "SCIENCE-FICTION", "color": (6, 182, 212), "requests": ["movie:with_genres=878&sort_by=popularity.desc", "tv:with_genres=10765&sort_by=popularity.desc"]},
    "thriller": {"label": "THRILLER", "color": (29, 78, 216), "requests": ["movie:with_genres=53&sort_by=popularity.desc", "tv:with_genres=80&sort_by=popularity.desc"]},
    "western": {"label": "WESTERN", "color": (214, 100, 42), "requests": ["movie:with_genres=37&sort_by=popularity.desc", "tv:with_genres=37&sort_by=popularity.desc"]},
    "documentaire": {
        "label": "DOCUMENTAIRE", 
        "color": (34, 197, 94),
        "requests": ["movie:with_genres=99&sort_by=popularity.desc", "tv:with_genres=99&sort_by=popularity.desc"]
    }
}

OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"
PROCESSED_MEDIA_IDS = set()

def tmdb_get(endpoint, params):
    """Effectue une requête GET sur TMDB avec gestion robuste des retries (anti-rate limit)"""
    query = dict(params)
    query["api_key"] = TMDB_API_KEY
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(f"{TMDB_BASE}{endpoint}", params=query, timeout=20)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code is None or status_code < 500 or attempt == 2:
                raise
            time.sleep(1 + attempt)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise last_error

def parse_request_spec(spec):
    """Découpe la spécification de la requête (ex: movie:with_genres=28...)"""
    try:
        raw_media_type, raw_request = spec.split(":", 1)
    except ValueError as exc:
        raise ValueError(f"Format invalide '{spec}'.") from exc

    media_type = "tv" if raw_media_type.strip() == "series" else raw_media_type.strip()
    raw_request = raw_request.strip()

    if raw_request.startswith("/"):
        path, _, query_string = raw_request.partition("?")
        params = dict(parse_qsl(query_string, keep_blank_values=True))
        return {"mode": "endpoint", "media_type": media_type, "path": path, "params": params}

    params = dict(parse_qsl(raw_request, keep_blank_values=True))
    return {"mode": "discover", "media_type": media_type, "params": params}

def fetch_titles_for_genres(tmdb_requests, count=30):
    """Récupère et entrelace intelligemment les résultats de films et de séries"""
    request_specs = [parse_request_spec(spec) for spec in tmdb_requests]
    per_spec_items = []

    for spec in request_specs:
        items = []
        endpoint = f"/discover/{spec['media_type']}" if spec["mode"] == "discover" else spec["path"]
        base_params = dict(spec["params"])

        for page in range(1, 3):
            try:
                data = tmdb_get(endpoint, {**base_params, "page": page})
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    if item.get("backdrop_path"):
                        items.append((spec["media_type"], item))
            except Exception:
                break
        per_spec_items.append(items)

    merged = []
    max_len = max((len(x) for x in per_spec_items), default=0)
    for index in range(max_len):
        for spec_items in per_spec_items:
            if index < len(spec_items):
                merged.append(spec_items[index])

    seen = set()
    unique_titles = []
    for media_type, item in merged:
        key = f"{media_type}_{item['id']}"
        if key not in seen:
            seen.add(key)
            unique_titles.append((media_type, item))
            if len(unique_titles) >= count:
                break
                
    return unique_titles

def select_best_textless_backdrop(media_type, media_id, fallback_path):
    """
    Parcourt la galerie TMDB pour extraire le meilleur fond strictement textless.
    Priorise les listes sans langue (null) pour garantir l'absence totale de logos.
    """
    try:
        data = tmdb_get(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        backdrops_list = data.get("backdrops", [])
        if not backdrops_list:
            return fallback_path

        # On prend le plus voté de la section sans texte (null)
        best_textless = max(backdrops_list, key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)))
        return best_textless.get("file_path")
    except Exception:
        return fallback_path

def calculate_landscape_score(backdrop_data, item, media_type):
    """Système de notation déterministe basé sur la qualité et la popularité de l'œuvre"""
    score = 50
    w = backdrop_data.get("width", 0)
    popularity = item.get("popularity", 0)
    
    if w >= 3840: score += 20
    elif w >= 1920: score += 10
        
    if popularity > 100: score += 20
    elif popularity > 30: score += 10
        
    if media_type == "movie": score += 10  # Léger avantage pour le cadrage cinéma natif
    return score

def apply_landscape_duotone(img, target_color):
    gray = img.convert("L")
    gray_np = np.array(gray)
    base_dark = np.array([12, 16, 26]) # Fond Apple TV
    target_light = np.array(target_color)
    
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
    return Image.fromarray(duotone)

def finalize_landscape_poster(img, label, target_color):
    img = img.resize((1920, 1080), Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = apply_landscape_duotone(img, target_color)
    
    draw = ImageDraw.Draw(img, "RGBA")
    
    # Dégradé cinématique linéaire bas
    for y in range(650, 1080):
        alpha = int(((y - 650) / 430) ** 2.0 * 230)
        draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
        
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", 72)
    except IOError:
        font = ImageFont.load_default()
        
    draw.text((90, 930), label, fill=(255, 255, 255, 255), font=font)
    return img

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- [BANNIÈRE LANDSCAPE] Traitement du genre : {config['label']} ---")
        
        try:
            titles_pool = fetch_titles_for_genres(config["requests"], count=15)
            time.sleep(0.5) # Anti rate-limit post discovery
            
            pool_candidates = []
            for media_type, item in titles_pool:
                media_id = item["id"]
                composite_key = f"{media_type}_{media_id}"
                
                if composite_key in PROCESSED_MEDIA_IDS: 
                    continue
                
                # Récupération stricte de l'asset sans texte
                best_path = select_best_textless_backdrop(media_type, media_id, item.get("backdrop_path"))
                time.sleep(0.2) # Respiration API
                
                if not best_path: 
                    continue
                    
                img_url = f"https://image.tmdb.org/t/p/original{best_path}"
                try:
                    img_res = requests.get(img_url, stream=True, timeout=8)
                    if img_res.status_code == 200:
                        raw_img = Image.open(img_res.raw).convert("RGB")
                        img = ImageOps.exif_transpose(raw_img)
                        
                        # Création d'un dictionnaire d'infos d'image minimal pour le score
                        bg_info = {"width": img.size[0], "file_path": best_path}
                        score = calculate_landscape_score(bg_info, item, media_type)
                        
                        pool_candidates.append({
                            "image": img,
                            "score": score,
                            "title": item.get("title") or item.get("name"),
                            "key": composite_key
                        })
                except Exception as img_err:
                    print(f"      [Alerte Download] Échec de l'asset {img_url}: {img_err}")
                    continue
                    
            if pool_candidates:
                pool_candidates.sort(key=lambda x: x["score"], reverse=True)
                winner = pool_candidates[0]
                
                print(f" ==> BANNIÈRE RETENUE : {winner['title']} (Score: {winner['score']}/100)")
                
                final_landscape = finalize_landscape_poster(winner["image"], config["label"], config["color"])
                
                # Sauvegarde finale synchronisée
                final_landscape.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
                final_landscape.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
                
                PROCESSED_MEDIA_IDS.add(winner["key"])
            else:
                print(f" /!\\ CONSERVATION : Aucun nouvel asset validé pour {config['label']}.")
                
        except Exception as genre_err:
            print(f" /!\\ [ERREUR CRITIQUE] Le traitement du genre {config['label']} a échoué : {genre_err}")
            print("Passage immédiat au genre suivant pour préserver le run...")
            continue

if __name__ == "__main__":
    main()

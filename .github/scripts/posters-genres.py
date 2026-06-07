import os
import sys
import requests
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps

TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

# Configuration de la Vague 1 + Genre Crime avec tes mots-clés exacts
GENRES_CONFIG = {
    "action": {
        "id": 28, 
        "tv_id": 10759, 
        "label": "ACTION", 
        "color": (255, 90, 0),
        "keywords": "3930,6054,12993,9951,8440,188955,226499,83,312,779,4565,14955,853,9665,10044",
        "exclude_genres": "16,99"
    },
    "animation-japonaise": {
        "id": 16, 
        "tv_id": 16, 
        "label": "ANIMATION JAPONAISE", 
        "color": (255, 0, 128),
        "keywords": "210024,13141,207826",
        "exclude_genres": "99"
    }, 
    "animation": {
        "id": 16, 
        "tv_id": 16, 
        "label": "ANIMATION", 
        "color": (0, 200, 255),
        "keywords": "272909,7376,278823,234183,179411,234662,290589,297442,339048,366485",
        "exclude_genres": "99"
    }, 
    "aventure": {
        "id": 12, 
        "tv_id": 10759, 
        "label": "AVENTURE", 
        "color": (245, 158, 11),
        "keywords": "195114,161176,818,4152,170362,210246,10364,41586,6956,269233",
        "exclude_genres": "16,99"
    },
    "comedie": {
        "id": 35, 
        "tv_id": 35, 
        "label": "COMÉDIE", 
        "color": (250, 204, 21),
        "keywords": "8201,9755,9964,375047,6241,9253",
        "exclude_genres": "16,99"
    },
    "crime": {
        "id": 80, 
        "tv_id": 80, 
        "label": "CRIME", 
        "color": (107, 114, 128),
        "keywords": "2095,9748,181644,157241,206958,268067,703,5340,6149,9826,155790,207046",
        "exclude_genres": "16,99"
    },
    "drame": {"id": 18, "tv_id": 18, "label": "DRAME", "color": (14, 165, 233)},
    "famille": {"id": 10751, "tv_id": 10751, "label": "FAMILLE", "color": (217, 70, 239)},
    "fantastique": {"id": 14, "tv_id": 10765, "label": "FANTASTIQUE", "color": (168, 85, 247)},
    "guerre": {"id": 10752, "tv_id": 10768, "label": "GUERRE", "color": (120, 113, 108)},
    "histoire": {"id": 36, "tv_id": 10768, "label": "HISTOIRE", "color": (180, 83, 9)},
    "horreur": {"id": 27, "tv_id": 27, "label": "HORREUR", "color": (239, 68, 68)},
    "romance": {"id": 10749, "tv_id": 10749, "label": "ROMANCE", "color": (244, 63, 94)},
    "science-fiction": {"id": 878, "tv_id": 10765, "label": "SCIENCE-FICTION", "color": (6, 182, 212)},
    "thriller": {"id": 53, "tv_id": 80, "label": "THRILLER", "color": (29, 78, 216)},
    "western": {"id": 37, "tv_id": 37, "label": "WESTERN", "color": (214, 100, 42)},
    "documentaire": {
        "id": 99, 
        "tv_id": 99, 
        "label": "DOCUMENTAIRE", 
        "color": (34, 197, 94),
        "keywords": "221355,305903,343303,284176",
        "exclude_genres": "28,14,878"
    }
}

OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"
PROCESSED_MEDIA_IDS = set()

def is_mature_release(date_str):
    if not date_str: return False
    try:
        release_date = datetime.strptime(date_str, "%Y-%m-%d")
        return release_date <= (datetime.now() - timedelta(days=14))
    except ValueError:
        return False

def get_media_year(item):
    date_str = item.get("release_date") or item.get("first_air_date")
    if not date_str: return 2000
    try: return datetime.strptime(date_str, "%Y-%m-%d").year
    except ValueError: return 2000

def get_balanced_trending_media(genre_key, config):
    if "keywords" in config:
        docs_movies, docs_tv = [], []
        target_genre_id = config["id"]
        target_tv_genre_id = config.get("tv_id", config["id"])
        keywords = config["keywords"]
        exclude = config.get("exclude_genres", "")
        
        url_movies = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={target_genre_id}&with_keywords={keywords}&without_genres={exclude}&sort_by=popularity.desc&language=fr-FR&page=1"
        url_tv = f"https://api.themoviedb.org/3/discover/tv?api_key={TMDB_API_KEY}&with_genres={target_tv_genre_id}&with_keywords={keywords}&without_genres={exclude}&sort_by=popularity.desc&language=fr-FR&page=1"
        
        try:
            res_m = requests.get(url_movies, timeout=10).json().get("results", [])
            for item in res_m:
                item["media_type"] = "movie"
                if genre_key == "animation-japonaise" and item.get("original_language", "") != "ja": continue
                if genre_key == "animation" and item.get("original_language", "") == "ja": continue
                docs_movies.append(item)
                
            res_t = requests.get(url_tv, timeout=10).json().get("results", [])
            for item in res_t:
                item["media_type"] = "tv"
                if genre_key == "animation-japonaise" and item.get("original_language", "") != "ja": continue
                if genre_key == "animation" and item.get("original_language", "") == "ja": continue
                docs_tv.append(item)
        except Exception as e:
            print(f"   [Erreur] Discover échec: {e}")
            
        return docs_movies[:6] + docs_tv[:6]

    # Mode Tendance de repli pour les autres genres
    trending_movies, trending_shows = [], []
    for page in [1, 2, 3]:
        url = f"https://api.themoviedb.org/3/trending/all/week?api_key={TMDB_API_KEY}&page={page}&language=fr-FR"
        try: res = requests.get(url, timeout=10).json().get("results", [])
        except Exception: continue
        for item in res:
            media_type = item.get("media_type")
            if media_type not in ["movie", "tv"]: continue
            date_str = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
            if not is_mature_release(date_str): continue
            target_id = config["id"] if media_type == "movie" else config.get("tv_id", config["id"])
            if target_id in item.get("genre_ids", []):
                if media_type == "movie" and len(trending_movies) < 5: trending_movies.append(item)
                elif media_type == "tv" and len(trending_shows) < 5: trending_shows.append(item)
    return trending_movies + trending_shows

def get_media_backdrops(media_id, media_type):
    endpoint = "movie" if media_type == "movie" else "tv"
    url = f"https://api.themoviedb.org/3/{endpoint}/{media_id}/images?api_key={TMDB_API_KEY}&include_image_language=null"
    try: res = requests.get(url, timeout=5).json()
    except Exception: return []
    backdrops = res.get("backdrops", [])
    backdrops.sort(key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)), reverse=True)
    return backdrops

def calculate_landscape_score(backdrop, release_year):
    # Système de notation simplifié et surpuissant basé sur tes règles de favorisation
    score = 50
    w = backdrop.get("width", 0)
    
    # Bonus Résolution : Valorisation immédiate de la HD / 4K natif
    if w >= 3840: score += 25     # Ultra HD Master
    elif w >= 1920: score += 15   # Full HD Standard
    
    # Bonus Modernité : Fraîcheur des assets
    if release_year >= 2020: score += 25
    elif release_year >= 2010: score += 10
    
    return score

def apply_landscape_duotone(img, target_color):
    gray = img.convert("L")
    gray_np = np.array(gray)
    base_dark = np.array([12, 16, 26]) # Ton sombre Apple TV
    target_light = np.array(target_color)
    
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
    return Image.fromarray(duotone)

def finalize_landscape_poster(img, label, target_color):
    # Redimensionnement propre au format standard Cinema/TV 16:9
    img = img.resize((1920, 1080), Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = apply_landscape_duotone(img, target_color)
    
    draw = ImageDraw.Draw(img, "RGBA")
    
    # Dégradé cinématique en cloche basse (Apple TV style) pour garantir la lisibilité du titre
    for y in range(650, 1080):
        alpha = int(((y - 650) / 430) ** 2.0 * 230)
        draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
        
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", 72)
    except IOError:
        font = ImageFont.load_default()
        
    # Positionnement élégant en bas à gauche avec marge de sécurité aéronautique/UI
    draw.text((90, 930), label, fill=(255, 255, 255, 255), font=font)
    return img

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- [BANNIÈRE LANDSCAPE] Traitement : {config['label']} ---")
        media_pool = get_balanced_trending_media(genre_name, config)
        
        pool_candidates = []
        for item in media_pool:
            media_id = item["id"]
            media_type = item["media_type"]
            composite_key = f"{media_type}_{media_id}"
            
            if composite_key in PROCESSED_MEDIA_IDS: continue
            
            release_year = get_media_year(item)
            backdrops = get_media_backdrops(media_id, media_type)
            if not backdrops: continue
            
            # On prend le meilleur backdrop textless disponible
            best_bg = backdrops[0] 
            img_url = f"https://image.tmdb.org/t/p/original{best_bg['file_path']}"
            
            try:
                img_res = requests.get(img_url, stream=True, timeout=5)
                if img_res.status_code == 200:
                    raw_img = Image.open(img_res.raw).convert("RGB")
                    img = ImageOps.exif_transpose(raw_img)
                    
                    score = calculate_landscape_score(best_bg, release_year)
                    pool_candidates.append({
                        "image": img,
                        "score": score,
                        "title": item.get("title") or item.get("name"),
                        "key": composite_key
                    })
            except Exception:
                continue
                
        if pool_candidates:
            # Le plus haut score (HD + Récent) l'emporte de manière déterministe
            pool_candidates.sort(key=lambda x: x["score"], reverse=True)
            winner = pool_candidates[0]
            
            print(f" ==> BANNIÈRE RETENUE : {winner['title']} (Score: {winner['score']}/100)")
            
            final_landscape = finalize_landscape_poster(winner["image"], config["label"], config["color"])
            
            # Sauvegarde propre dans ton arborescence standard
            final_landscape.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_landscape.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            # Blocage de l'ID pour empêcher les doublons sur les autres genres
            PROCESSED_MEDIA_IDS.add(winner["key"])
        else:
            print(f" /!\\ CONSERVATION : Aucun asset disponible pour {config['label']}.")

if __name__ == "__main__":
    main()

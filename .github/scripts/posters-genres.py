import os
import sys
import time
import requests
from datetime import datetime, timedelta
from urllib.parse import parse_qsl
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import cv2

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

# Configuration hybride enrichie (Vague 1) - Requêtes calquées sur ton fichier YAML
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

# Initialisation du cascade classifier pour l'analyse faciale d'origine
face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(face_cascade_path)

def tmdb_get(endpoint, params):
    """Effectue une requête GET sur TMDB avec gestion des retries (anti-rate limit de backdrop.py)"""
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
    """Découpe l'argument de requête (ex: 'movie:with_genres=28...')"""
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
    """Récupère et entrelace les résultats de films et de séries de manière équitable"""
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

def get_exclusive_textless_backdrops(media_type, media_id):
    """Récupère la galerie d'images filtrée strictement sur l'absence de texte (langue 'null')"""
    try:
        data = tmdb_get(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        backdrops = data.get("backdrops", [])
        backdrops.sort(key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)), reverse=True)
        return backdrops
    except Exception:
        return []

def analyze_image_layout(img):
    """Écarte les fonds noirs trop vides (teasers)"""
    gray = img.convert("L")
    gray_np = np.array(gray)
    h, w = gray_np.shape
    dark_pixels = np.sum(gray_np < 20)
    if (dark_pixels / (h * w)) > 0.60:
        return "teaser"
    return "ok"

def calculate_candidate_score(variance, num_faces, genre_name, layout_status, item):
    if layout_status == "teaser": return 5
    
    score = 50  
    score += min(20, int(variance / 8))
    
    # Bonus de popularité hérité de la logique d'importance globale
    popularity = item.get("popularity", 0)
    if popularity > 120: score += 10
    
    if genre_name in ["action", "science-fiction", "thriller", "romance", "aventure"]:
        if num_faces in [1, 2]: score += 20
        elif num_faces == 0: score += 5
    else:
        if num_faces <= 1: score += 20
        else: score += 5
        
    return max(0, score)

def find_best_crop_x(img, target_w, faces):
    W, H = img.size
    if len(faces) > 0:
        main_face = max(faces, key=lambda f: f[2] * f[3])
        fx, _, fw, fh = main_face
        if fh / H <= 0.35:
            best_x_start = (fx + (fw // 2)) - (target_w // 2)
            return max(0, min(best_x_start, W - target_w))

    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    lap_np = np.array(laplacian_img)

    best_x_start = (W - target_w) // 2
    max_detail_score = 0
    step = max(1, (W - target_w) // 10)
    
    for x_start in range(0, W - target_w + 1, step):
        window_lap = lap_np[:, x_start:x_start + target_w]
        detail_score = np.sum(window_lap > 45)
        if detail_score > max_detail_score:
            max_detail_score = detail_score
            best_x_start = x_start
            
    return best_x_start

def process_candidate(backdrop, genre_name, item):
    img_url = f"https://image.tmdb.org/t/p/original{backdrop['file_path']}"
    try:
        img_res = requests.get(img_url, stream=True, timeout=5)
        if img_res.status_code != 200: return None
        raw_img = Image.open(img_res.raw).convert("RGB")
    except Exception:
        return None
        
    img = ImageOps.exif_transpose(raw_img)
    W, H = img.size
    if W < 1000 or H < 600: return None
    
    layout_status = analyze_image_layout(img)
    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    variance = np.array(laplacian_img, dtype=np.float32).var()
    
    if variance < 35: return None
    
    img_np = np.array(img)
    gray_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    try:
        faces = face_cascade.detectMultiScale(gray_np, scaleFactor=1.1, minNeighbors=5, minSize=(35, 35))
    except Exception:
        faces = []
        
    num_faces = len(faces)
    if num_faces > 3: return None
    
    target_w = int(H * (2/3))
    if target_w > W: return None
    
    best_x_start = find_best_crop_x(img, target_w, faces)
    if best_x_start is None: return None
    cropped = img.crop((best_x_start, 0, best_x_start + target_w, H))

    final_img = cropped.resize((800, 1200), Image.Resampling.LANCZOS)
    score = calculate_candidate_score(variance, num_faces, genre_name, layout_status, item)
    
    return final_img, score, backdrop['file_path']

def apply_duotone(img, target_color):
    gray = img.convert("L")
    gray_np = np.array(gray)
    base_dark = np.array([12, 16, 26])
    target_light = np.array(target_color)
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
    return Image.fromarray(duotone)

def finalize_poster(img, label, target_color):
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = apply_duotone(img, target_color)
    
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(750, 1200):
        alpha = int(((y - 750) / 450) ** 2.3 * 245)
        draw.line([(0, y), (800, y)], fill=(0, 0, 0, alpha))
        
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", 54)
    except IOError:
        font = ImageFont.load_default()
        
    words = label.split()
    lines = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        if draw.textlength(test, font=font) <= 680: current_line = test
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)
    
    font_box = font.getbbox("A")
    fh = font_box[3] - font_box[1]
    
    if len(lines) <= 1:
        draw.text((60, 1070), label, fill=(255, 255, 255, 255), font=font)
    else:
        ay = 1070 - fh - 12
        for line in lines[:2]:
            draw.text((60, ay), line, fill=(255, 255, 255, 255), font=font)
            ay += fh + 12
            
    return img

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- [TOURNOI PREMIUM TEXTLESS] Genre : {config['label']} ---")
        
        try:
            balanced_pool = fetch_titles_for_genres(config["requests"], count=15)
            time.sleep(0.4) # Respiration API post-discovery
            
            pool_candidates = []
            for media_type, item in balanced_pool:
                media_id = item["id"]
                composite_key = f"{media_type}_{media_id}"
                if composite_key in PROCESSED_MEDIA_IDS: continue
                
                # Isolation stricte des backdrops communautaires tagués sans texte (langue = null)
                backdrops = get_exclusive_textless_backdrops(media_type, media_id)
                time.sleep(0.15) # Pause réglementaire anti-rate limit
                if not backdrops: continue
                
                for bg in backdrops[:3]:
                    result = process_candidate(bg, genre_name, item)
                    if result:
                        processed_img, score, file_path = result
                        pool_candidates.append({
                            "image": processed_img,
                            "score": score,
                            "title": item.get("title") or item.get("name"),
                            "key": composite_key,
                            "path": file_path,
                            "type": media_type
                        })
            
            if pool_candidates:
                pool_candidates.sort(key=lambda x: x["score"], reverse=True)
                winner = pool_candidates[0]
                
                print(f" ==> VAINQUEUR ASSURÉ SANS LOGO : {winner['type'].upper()} '{winner['title']}' (Score: {winner['score']}/100)")
                
                final_poster = finalize_poster(winner["image"], config["label"], config["color"])
                final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
                final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
                
                PROCESSED_MEDIA_IDS.add(winner["key"])
            else:
                print(f" /!\\ CONSERVATION : Aucun asset textless validé pour {config['label']}.")
                
        except Exception as genre_err:
            print(f" /!\\ [ALERTE GENRE] Échec sur le genre {config['label']}: {genre_err}")
            print("Passage au genre suivant pour ne pas bloquer le déploiement Git.")
            continue

if __name__ == "__main__":
    main()

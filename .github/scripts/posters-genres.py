import os
import random
import sys
import requests
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import cv2

# Récupération de la clé API via les secrets GitHub
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

# Configuration des 17 genres avec alignement des IDs Films et Séries
GENRES_CONFIG = {
    "action": {"id": 28, "tv_id": 10759, "label": "ACTION", "color": (255, 90, 0)},
    "animation-japonaise": {"id": 16, "tv_id": 16, "label": "ANIMATION JAPONAISE", "color": (255, 0, 128)}, 
    "animation": {"id": 16, "tv_id": 16, "label": "ANIMATION", "color": (0, 200, 255)}, 
    "aventure": {"id": 12, "tv_id": 10759, "label": "AVENTURE", "color": (245, 158, 11)},
    "comedie": {"id": 35, "tv_id": 35, "label": "COMÉDIE", "color": (250, 204, 21)},
    "crime": {"id": 80, "tv_id": 80, "label": "CRIME", "color": (107, 114, 128)},
    "documentaire": {"id": 99, "tv_id": 99, "label": "DOCUMENTAIRE", "color": (34, 197, 94)},
    "drame": {"id": 18, "tv_id": 18, "label": "DRAME", "color": (14, 165, 233)},
    "famille": {"id": 10751, "tv_id": 10751, "label": "FAMILLE", "color": (217, 70, 239)},
    "fantastique": {"id": 14, "tv_id": 10765, "label": "FANTASTIQUE", "color": (168, 85, 247)},
    "guerre": {"id": 10752, "tv_id": 10768, "label": "GUERRE", "color": (120, 113, 108)},
    "histoire": {"id": 36, "tv_id": 10768, "label": "HISTOIRE", "color": (180, 83, 9)},
    "horreur": {"id": 27, "tv_id": 27, "label": "HORREUR", "color": (239, 68, 68)},
    "romance": {"id": 10749, "tv_id": 10749, "label": "ROMANCE", "color": (244, 63, 94)},
    "science-fiction": {"id": 878, "tv_id": 10765, "label": "SCIENCE-FICTION", "color": (6, 182, 212)},
    "thriller": {"id": 53, "tv_id": 80, "label": "THRILLER", "color": (29, 78, 216)},
    "western": {"id": 37, "tv_id": 37, "label": "WESTERN", "color": (214, 100, 42)}
}

OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"
PROCESSED_MEDIA_IDS = set()

# Chargement du classificateur de visages OpenCV (fourni nativement avec cv2)
face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(face_cascade_path)

def is_mature_release(date_str):
    """Vérifie si le média est sorti depuis au moins 14 jours (évite les coquilles vides)."""
    if not date_str:
        return False
    try:
        release_date = datetime.strptime(date_str, "%Y-%m-%d")
        safety_threshold = datetime.now() - timedelta(days=14)
        return release_date <= safety_threshold
    except ValueError:
        return False

def get_balanced_trending_media(genre_key, config):
    """Récolte équitablement 5 films et 5 séries tendances de la semaine pour le genre."""
    trending_movies = []
    trending_shows = []
    
    for page in [1, 2, 3, 4, 5]:
        if len(trending_movies) >= 5 and len(trending_shows) >= 5:
            break
            
        url = f"https://api.themoviedb.org/3/trending/all/week?api_key={TMDB_API_KEY}&page={page}&language=fr-FR"
        try:
            res = requests.get(url, timeout=10).json()
            results = res.get("results", [])
        except Exception:
            continue
            
        for item in results:
            media_type = item.get("media_type")
            genre_ids = item.get("genre_ids", [])
            org_lang = item.get("original_language", "")
            
            date_str = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
            if not is_mature_release(date_str):
                continue
                
            target_genre_id = config["id"] if media_type == "movie" else config.get("tv_id", config["id"])
            
            if target_genre_id in genre_ids:
                if genre_key == "animation-japonaise" and (16 not in genre_ids or org_lang != "ja"):
                    continue
                if genre_key == "animation" and (16 not in genre_ids or org_lang == "ja"):
                    continue
                
                if media_type == "movie" and len(trending_movies) < 5 and item not in trending_movies:
                    trending_movies.append(item)
                elif media_type == "tv" and len(trending_shows) < 5 and item not in trending_shows:
                    trending_shows.append(item)
                    
    return trending_movies + trending_shows

def get_media_artworks(media_id, media_type):
    endpoint = "movie" if media_type == "movie" else "tv"
    url = f"https://api.themoviedb.org/3/{endpoint}/{media_id}/images?api_key={TMDB_API_KEY}&include_image_language=null"
    
    try:
        res = requests.get(url, timeout=5).json()
    except Exception:
        return []
        
    backdrops = res.get("backdrops", [])
    posters = res.get("posters", [])
    
    for b in backdrops: b['artwork_type'] = 'backdrop'
    for p in posters: p['artwork_type'] = 'poster'
    
    return posters + backdrops

def analyze_grid_emptiness(img):
    gray = img.convert("L")
    gray_np = np.array(gray)
    h, w = gray_np.shape
    bh, bw = h // 3, w // 3
    empty_blocks = 0
    
    for i in range(3):
        for j in range(3):
            block = gray_np[i*bh:(i+1)*bh, j*bw:(j+1)*bw]
            if block.var() < 12.0:
                empty_blocks += 1
                
    return empty_blocks >= 6

def calculate_candidate_score(artwork_type, variance, num_faces, genre_name, is_teaser):
    score = 0
    if is_teaser: return 5
    if artwork_type == 'poster': score += 35
    
    score += min(25, int(variance / 7))
    
    if genre_name in ["action", "science-fiction", "thriller", "romance", "aventure"]:
        if num_faces in [1, 2]: score += 40
        elif num_faces == 0: score += 10
        else: score += 5
    else:
        if num_faces <= 1: score += 40
        else: score += 15
        
    return score

def find_best_crop_x(img, target_w, faces):
    W, H = img.size
    if len(faces) > 0:
        # Trouver le plus grand visage détecté par OpenCV (w * h)
        main_face = max(faces, key=lambda f: f[2] * f[3])
        fx, _, fw, _ = main_face
        best_x_start = (fx + (fw // 2)) - (target_w // 2)
        return max(0, min(best_x_start, W - target_w))

    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    lap_np = np.array(laplacian_img)

    best_x_start = (W - target_w) // 2
    max_detail_score = 0
    step = max(1, (W - target_w) // 8)
    
    for x_start in range(0, W - target_w + 1, step):
        window_lap = lap_np[:, x_start:x_start + target_w]
        detail_score = np.sum(window_lap > 50)
        if detail_score > max_detail_score:
            max_detail_score = detail_score
            best_x_start = x_start
            
    return best_x_start

def apply_duotone(img, target_color):
    gray = img.convert("L")
    gray_np = np.array(gray)
    base_dark = np.array([12, 16, 26])
    target_light = np.array(target_color)
    
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
        
    return Image.fromarray(duotone)

def process_candidate(artwork, genre_name):
    img_url = f"https://image.tmdb.org/t/p/original{artwork['file_path']}"
    artwork_type = artwork['artwork_type']
    
    try:
        img_res = requests.get(img_url, stream=True, timeout=5)
        if img_res.status_code != 200: return None
        raw_img = Image.open(img_res.raw).convert("RGB")
    except Exception:
        return None
        
    img = ImageOps.exif_transpose(raw_img)
    W, H = img.size
    if W < 800 or H < 600: return None
    
    is_teaser = analyze_grid_emptiness(img)
    
    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    variance = np.array(laplacian_img, dtype=np.float32).var()
    
    if variance < 45: return None
    
    # Détection de visages ultra-rapide avec OpenCV
    img_np = np.array(img)
    gray_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    try:
        # scaleFactor=1.1, minNeighbors=5 balancent bien précision/vitesse
        faces = face_cascade.detectMultiScale(gray_np, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    except Exception:
        faces = []
        
    num_faces = len(faces)
    if artwork_type == 'poster' and num_faces > 4: return None
    if artwork_type == 'backdrop' and num_faces > 2: return None
    
    if artwork_type == 'backdrop':
        target_w = int(H * (2/3))
        if target_w > W: return None
        best_x_start = find_best_crop_x(img, target_w, faces)
        if best_x_start is None: return None
        cropped = img.crop((best_x_start, 0, best_x_start + target_w, H))
    else:
        current_ratio = W / H
        if abs(current_ratio - (2/3)) > 0.02:
            target_w = int(H * (2/3))
            if target_w <= W:
                start_x = (W - target_w) // 2
                cropped = img.crop((start_x, 0, start_x + target_w, H))
            else: cropped = img
        else: cropped = img

    final_img = cropped.resize((800, 1200), Image.Resampling.LANCZOS)
    score = calculate_candidate_score(artwork_type, variance, num_faces, genre_name, is_teaser)
    
    return final_img, score, artwork['file_path']

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
        print(f"\n--- [TOURNOI PARITAIRE TENDANCES] Collecte équitable pour : {config['label']} ---")
        balanced_pool = get_balanced_trending_media(genre_name, config)
        
        pool_candidates = []
        for item in balanced_pool:
            media_id = item["id"]
            media_type = item.get("media_type")
            
            composite_key = f"{media_type}_{media_id}"
            if composite_key in PROCESSED_MEDIA_IDS: continue
            
            artworks = get_media_artworks(media_id, media_type)
            if not artworks: continue
            
            for art in artworks[:4]:
                result = process_candidate(art, genre_name)
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
            
            print(f" -> Tournoi validé : {len(pool_candidates)} images filtrées et notées.")
            print(f" ==> VAINQUEUR : {winner['type'].upper()} '{winner['title']}' (Score: {winner['score']}/100) - Asset: {winner['path']}")
            
            final_poster = finalize_poster(winner["image"], config["label"], config["color"])
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            PROCESSED_MEDIA_IDS.add(winner["key"])
        else:
            print(f" /!\\ CONSERVATION : Aucun asset mature et qualitatif trouvé pour {genre_name}.")

if __name__ == "__main__":
    main()

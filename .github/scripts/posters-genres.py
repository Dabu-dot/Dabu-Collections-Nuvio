import os
import random
import sys
import requests
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import cv2

TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

# Configuration hybride enrichie grâce à ta Vague 1 de terrain
GENRES_CONFIG = {
    "action": {
        "id": 28, 
        "tv_id": 10759, 
        "label": "ACTION", 
        "color": (255, 90, 0),
        "keywords": "3930,6054,12993,9951,8440,188955,226499,83,312,779,4565,14955,853,9665,10044",
        "exclude_genres": "16,99" # Exclut l'animation et le documentaire pour garder du live-action
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
    "documentaire": {
        "id": 99, 
        "tv_id": 99, 
        "label": "DOCUMENTAIRE", 
        "color": (34, 197, 94),
        "keywords": "221355,305903,343303,284176",
        "exclude_genres": "28,14,878" # Sécurité renforcée anti-blockbusters
    },
    # Mode de repli temporaire pour les autres genres en attendant la Vague 2
    "crime": {"id": 80, "tv_id": 80, "label": "CRIME", "color": (107, 114, 128)},
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

face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(face_cascade_path)

def is_mature_release(date_str):
    if not date_str: return False
    try:
        release_date = datetime.strptime(date_str, "%Y-%m-%d")
        safety_threshold = datetime.now() - timedelta(days=14)
        return release_date <= safety_threshold
    except ValueError:
        return False

def get_balanced_trending_media(genre_key, config):
    """Filtre de manière chirurgicale via l'endpoint discover si les mots-clés existent, sinon utilise les tendances."""
    if "keywords" in config:
        docs_movies = []
        docs_tv = []
        
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
                org_lang = item.get("original_language", "")
                if genre_key == "animation-japonaise" and org_lang != "ja": continue
                if genre_key == "animation" and org_lang == "ja": continue
                docs_movies.append(item)
                
            res_t = requests.get(url_tv, timeout=10).json().get("results", [])
            for item in res_t: 
                item["media_type"] = "tv"
                org_lang = item.get("original_language", "")
                if genre_key == "animation-japonaise" and org_lang != "ja": continue
                if genre_key == "animation" and org_lang == "ja": continue
                docs_tv.append(item)
        except Exception as e:
            print(f"   [Erreur Collecte] Erreur lors du discover pour {genre_key}: {e}")
            
        return docs_movies[:6] + docs_tv[:6]

    # --- Mode de repli global pour les genres n'ayant pas encore de mots-clés ---
    trending_movies = []
    trending_shows = []
    
    for page in [1, 2, 3, 4, 5]:
        if len(trending_movies) >= 5 and len(trending_shows) >= 5: break
            
        url = f"https://api.themoviedb.org/3/trending/all/week?api_key={TMDB_API_KEY}&page={page}&language=fr-FR"
        try:
            res = requests.get(url, timeout=10).json()
            results = res.get("results", [])
        except Exception:
            continue
            
        for item in results:
            media_type = item.get("media_type")
            genre_ids = item.get("genre_ids", [])
            
            date_str = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
            if not is_mature_release(date_str): continue
                
            target_id = config["id"] if media_type == "movie" else config.get("tv_id", config["id"])
            
            if target_id in genre_ids:
                if media_type == "movie" and len(trending_movies) < 5 and item not in trending_movies:
                    trending_movies.append(item)
                elif media_type == "tv" and len(trending_shows) < 5 and item not in trending_shows:
                    trending_shows.append(item)
                    
    return trending_movies + trending_shows

def get_media_backdrops(media_id, media_type):
    """Récupère exclusivement les backdrops textless validés par votes communautaires."""
    endpoint = "movie" if media_type == "movie" else "tv"
    # include_image_language=null isole les images taguées comme strictes sans texte par la communauté
    url = f"https://api.themoviedb.org/3/{endpoint}/{media_id}/images?api_key={TMDB_API_KEY}&include_image_language=null"
    try:
        res = requests.get(url, timeout=5).json()
    except Exception:
        return []
    
    backdrops = res.get("backdrops", [])
    # Tri d'élite : d'abord le volume de votes, puis la note moyenne
    backdrops.sort(key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)), reverse=True)
    return backdrops

def analyze_image_layout(img):
    """Analyse la répartition lumineuse pour écarter les fonds noirs vides (teasers)."""
    gray = img.convert("L")
    gray_np = np.array(gray)
    h, w = gray_np.shape
    
    dark_pixels = np.sum(gray_np < 20)
    if (dark_pixels / (h * w)) > 0.60:
        return "teaser"
        
    return "ok"

def calculate_candidate_score(variance, num_faces, genre_name, layout_status):
    if layout_status == "teaser": return 5
    
    score = 50  # Base solide pour les backdrops textless de haute qualité
    score += min(20, int(variance / 8))
    
    if genre_name in ["action", "science-fiction", "thriller", "romance", "aventure"]:
        if num_faces in [1, 2]: score += 30
        elif num_faces == 0: score += 10
    else:
        if num_faces <= 1: score += 30
        else: score += 10
        
    return max(0, score)

def find_best_crop_x(img, target_w, faces):
    W, H = img.size
    if len(faces) > 0:
        main_face = max(faces, key=lambda f: f[2] * f[3])
        fx, _, fw, fh = main_face
        
        if fh / H > 0.35:
            pass  # Visage trop massif (gros plan extrême), repli sur l'analyse de texture
        else:
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

def apply_duotone(img, target_color):
    gray = img.convert("L")
    gray_np = np.array(gray)
    base_dark = np.array([12, 16, 26])
    target_light = np.array(target_color)
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
    return Image.fromarray(duotone)

def process_candidate(backdrop, genre_name):
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
    score = calculate_candidate_score(variance, num_faces, genre_name, layout_status)
    
    return final_img, score, backdrop['file_path']

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
        print(f"\n--- [TOURNOI PREMIUM] Traitement du genre : {config['label']} ---")
        balanced_pool = get_balanced_trending_media(genre_name, config)
        
        pool_candidates = []
        for item in balanced_pool:
            media_id = item["id"]
            media_type = item.get("media_type")
            
            composite_key = f"{media_type}_{media_id}"
            if composite_key in PROCESSED_MEDIA_IDS: continue
            
            # Récupère exclusivement les versions paysages textless de TMDB
            backdrops = get_media_backdrops(media_id, media_type)
            if not backdrops: continue
            
            for bg in backdrops[:3]:
                result = process_candidate(bg, genre_name)
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
            
            print(f" ==> VAINQUEUR SANS TEXTE : {winner['type'].upper()} '{winner['title']}' (Score: {winner['score']}/100)")
            
            final_poster = finalize_poster(winner["image"], config["label"], config["color"])
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            PROCESSED_MEDIA_IDS.add(winner["key"])
        else:
            print(f" /!\\ CONSERVATION : Aucun asset textless validé pour {genre_name}.")

if __name__ == "__main__":
    main()

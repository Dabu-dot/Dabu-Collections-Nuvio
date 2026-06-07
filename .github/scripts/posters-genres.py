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

def get_pure_documentaries():
    """Endpoint spécifique pour éviter l'infiltration de blockbusters de fiction dans Documentaire."""
    docs = []
    # 1. Récupération des films documentaires populaires (sans SF, Fantastique ni Action)
    url_movies = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres=99&without_genres=28,14,878&sort_by=popularity.desc&language=fr-FR&page=1"
    # 2. Récupération des séries documentaires populaires
    url_tv = f"https://api.themoviedb.org/3/discover/tv?api_key={TMDB_API_KEY}&with_genres=99&sort_by=popularity.desc&language=fr-FR&page=1"
    
    try:
        res_m = requests.get(url_movies, timeout=10).json().get("results", [])
        for item in res_m: 
            item["media_type"] = "movie"
            docs.append(item)
        res_t = requests.get(url_tv, timeout=10).json().get("results", [])
        for item in res_t: 
            item["media_type"] = "tv"
            docs.append(item)
    except Exception:
        pass
    return docs[:10]

def get_balanced_trending_media(genre_key, config):
    if genre_key == "documentaire":
        return get_pure_documentaries()
        
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
            org_lang = item.get("original_language", "")
            
            date_str = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
            if not is_mature_release(date_str): continue
                
            target_genre_id = config["id"] if media_type == "movie" else config.get("tv_id", config["id"])
            
            if target_genre_id in genre_ids:
                if genre_key == "animation-japonaise" and (16 not in genre_ids or org_lang != "ja"): continue
                if genre_key == "animation" and (16 not in genre_ids or org_lang == "ja"): continue
                
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

def analyze_image_layout(img):
    """Analyse fine de la répartition lumineuse et des vides (Détection Teaser et Centre Vide)."""
    gray = img.convert("L")
    gray_np = np.array(gray)
    h, w = gray_np.shape
    
    # 1. Sécurité anti-teaser noir (Mortal Kombat)
    # Si plus de 55% des pixels de l'affiche complète sont très sombres (< 25)
    dark_pixels = np.sum(gray_np < 25)
    if (dark_pixels / (h * w)) > 0.55:
        return "teaser"

    # 2. Sécurité anti-centre vide en couronne (Vice-Versa 2)
    bh, bw = h // 3, w // 3
    blocks_variance = []
    for i in range(3):
        for j in range(3):
            block = gray_np[i*bh:(i+1)*bh, j*bw:(j+1)*bw]
            blocks_variance.append(block.var())
            
    center_var = blocks_variance[4] # Bloc du milieu
    avg_outer_var = np.mean([blocks_variance[i] for i in [0,1,2,3,5,6,7,8]])
    
    # Si le centre est super lisse/vide alors que les bords débordent d'éléments
    if center_var < 15.0 and avg_outer_var > 45.0:
        return "center_empty"
        
    # Test classique de la grille vide générale
    empty_blocks = sum(1 for v in blocks_variance if v < 12.0)
    if empty_blocks >= 6:
        return "teaser"
        
    return "ok"

def calculate_candidate_score(artwork_type, variance, num_faces, genre_name, layout_status):
    if layout_status == "teaser": return 5
    
    score = 0
    if artwork_type == 'poster': score += 35
    
    score += min(25, int(variance / 7))
    
    # Pénalité si la composition isole le centre (évite le texte sur les visages extérieurs)
    if layout_status == "center_empty":
        score -= 40

    if genre_name in ["action", "science-fiction", "thriller", "romance", "aventure"]:
        if num_faces in [1, 2]: score += 40
        elif num_faces == 0: score += 10
        else: score += 5
    else:
        if num_faces <= 1: score += 40
        else: score += 15
        
    return max(0, score)

def find_best_crop_x(img, target_w, faces):
    W, H = img.size
    if len(faces) > 0:
        main_face = max(faces, key=lambda f: f[2] * f[3])
        fx, _, fw, fh = main_face
        
        # SÉCURITÉ ANTI-GROS PLAN ZOOMÉ (Crime / The Batman)
        # Si le visage prend plus de 30% de la hauteur de l'image originale, on refuse le cadrage dessus
        if fh / H > 0.30:
            print("   [Cadrage] Visage trop grand (gros plan détecté), repli sur l'analyse par détails.")
        else:
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
    
    layout_status = analyze_image_layout(img)
    
    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    variance = np.array(laplacian_img, dtype=np.float32).var()
    
    if variance < 45: return None
    
    img_np = np.array(img)
    gray_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    try:
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
    score = calculate_candidate_score(artwork_type, variance, num_faces, genre_name, layout_status)
    
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
        print(f"\n--- [TOURNOI] Traitement du genre : {config['label']} ---")
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
            
            print(f" ==> GAGNANT : {winner['type'].upper()} '{winner['title']}' (Score: {winner['score']}/100)")
            
            final_poster = finalize_poster(winner["image"], config["label"], config["color"])
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            PROCESSED_MEDIA_IDS.add(winner["key"])
        else:
            print(f" /!\\ CONSERVATION : Aucun asset validé pour {genre_name}.")

if __name__ == "__main__":
    main()

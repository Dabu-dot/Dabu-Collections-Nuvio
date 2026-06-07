import os
import random
import sys
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
from mtcnn import MTCNN

# Récupération de la clé API via les secrets GitHub
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

GENRES_CONFIG = {
    "action": {"id": 28, "label": "ACTION", "color": (255, 90, 0)},
    "animation-japonaise": {"id": 16, "label": "ANIMATION JAPONAISE", "color": (255, 0, 128)}, 
    "animation": {"id": 16, "label": "ANIMATION", "color": (0, 200, 255)}, 
    "aventure": {"id": 12, "label": "AVENTURE", "color": (245, 158, 11)},
    "comedie": {"id": 35, "label": "COMÉDIE", "color": (250, 204, 21)},
    "crime": {"id": 80, "label": "CRIME", "color": (107, 114, 128)},
    "documentaire": {"id": 99, "label": "DOCUMENTAIRE", "color": (34, 197, 94)},
    "drame": {"id": 18, "label": "DRAME", "color": (14, 165, 233)},
    "famille": {"id": 10751, "label": "FAMILLE", "color": (217, 70, 239)},
    "fantastique": {"id": 14, "label": "FANTASTIQUE", "color": (168, 85, 247)},
    "guerre": {"id": 10752, "label": "GUERRE", "color": (120, 113, 108)},
    "histoire": {"id": 36, "label": "HISTOIRE", "color": (180, 83, 9)},
    "horreur": {"id": 27, "label": "HORREUR", "color": (239, 68, 68)},
    "romance": {"id": 10749, "label": "ROMANCE", "color": (244, 63, 94)},
    "science-fiction": {"id": 878, "label": "SCIENCE-FICTION", "color": (6, 182, 212)},
    "thriller": {"id": 53, "label": "THRILLER", "color": (29, 78, 216)},
    "western": {"id": 37, "label": "WESTERN", "color": (214, 100, 42)}
}

OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"
detector = MTCNN()
PROCESSED_MOVIE_IDS = set()

def get_popular_movies_by_genre(genre_key, config):
    """Découverte des films avec requêtes normalisées et nettoyées pour TMDB."""
    movies = []
    genre_id = config["id"]
    
    global_genres = ["action", "aventure", "comedie", "crime", "drame", "famille", "fantastique", "horreur", "romance", "science-fiction", "thriller"]
    geo_filter = "&with_origin_country=US|FR|GB|CA|ES|DE|IT" if genre_key in global_genres else ""

    for page in [1, 2, 3]:
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page={page}&language=fr-FR{geo_filter}"
        
        if genre_key == "animation-japonaise":
            url += "&with_original_language=ja&vote_count.gte=100"
        elif genre_key == "animation":
            url += "&without_original_language=ja|ko|zh&vote_count.gte=100"
        elif genre_key == "aventure":
            url += "&without_genres=16&vote_count.gte=100"
        elif genre_key == "drame":
            url += "&primary_release_date.gte=2000-01-01&vote_count.gte=500"
        elif genre_key == "documentaire":
            # FIX DOCUMENTAIRE : Syntaxe simplifiée et robuste pour éviter le crash de l'URL
            url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres=99&with_keywords=209386&sort_by=vote_average.desc&vote_count.gte=20&page={page}"
        else:
            url += "&vote_count.gte=100"
            
        try:
            res = requests.get(url, timeout=10).json()
            if "results" in res and res["results"]:
                movies.extend(res["results"])
        except Exception:
            continue
            
    return movies

def get_movie_artworks(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={TMDB_API_KEY}&include_image_language=null"
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
    """Analyse si l'image est un immense aplat vide (Teaser / Logo)."""
    gray = img.convert("L")
    gray_np = np.array(gray)
    h, w = gray_np.shape
    
    # Découpage en une grille de 3x3 blocs
    bh, bw = h // 3, w // 3
    empty_blocks = 0
    
    for i in range(3):
        for j in range(3):
            block = gray_np[i*bh:(i+1)*bh, j*bw:(j+1)*bw]
            if block.var() < 12.0:  # Bloc très uniforme / plat
                empty_blocks += 1
                
    return empty_blocks >= 6  # Vrai si les 2/3 de l'image sont totalement vides

def calculate_candidate_score(artwork_type, variance, faces, genre_name, is_teaser):
    """Système de scoring prédictif pour élire la meilleure mise en page."""
    score = 0
    
    if is_teaser:
        return 5  # Pénalité quasi-éliminatoire pour les fonds noirs ou logos uniques
        
    if artwork_type == 'poster':
        score += 35
        
    # Évaluation de la netteté globale
    score += min(25, int(variance / 7))
    
    num_faces = len(faces)
    # Règle d'incarnation par genre
    if genre_name in ["action", "science-fiction", "thriller", "romance", "aventure"]:
        if num_faces in [1, 2]:
            score += 40  # Parfait pour l'identification du film
        elif num_faces == 0:
            score += 10  # Sanction si paysage trop anonyme pour de l'action
        else:
            score += 5
    else:
        # Pour le documentaire, l'histoire ou l'animation, les paysages ou structures sont bienvenus
        if num_faces <= 1:
            score += 40
        else:
            score += 15
            
    return score

def find_best_crop_x(img, target_w, faces):
    W, H = img.size
    if faces:
        main_face = max(faces, key=lambda f: f['box'][2] * f['box'][3])
        fx, _, fw, _ = main_face['box']
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
    
    # Détection des arrières-plans vides ou teaser posters
    is_teaser = analyze_grid_emptiness(img)
    
    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    variance = np.array(laplacian_img, dtype=np.float32).var()
    
    if variance < 45: return None
    
    # Analyse MTCNN des sujets principaux
    img_np = np.array(img)
    try:
        faces = detector.detect_faces(img_np)
    except Exception:
        faces = []
        
    if artwork_type == 'poster' and len(faces) > 4: return None
    if artwork_type == 'backdrop' and len(faces) > 2: return None
    
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
    score = calculate_candidate_score(artwork_type, variance, faces, genre_name, is_teaser)
    
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
        print(f"\n--- [TOURNOI FILTRÉ] Sélection intelligente pour : {config['label']} ---")
        movies = get_popular_movies_by_genre(genre_name, config)
        
        candidate_movies = movies[:8]
        pool_candidates = []
        
        for movie in candidate_movies:
            movie_id = movie["id"]
            if movie_id in PROCESSED_MOVIE_IDS: continue
            
            artworks = get_movie_artworks(movie_id)
            if not artworks: continue
            
            for art in artworks[:4]:
                result = process_candidate(art, genre_name)
                if result:
                    processed_img, score, file_path = result
                    pool_candidates.append({
                        "image": processed_img,
                        "score": score,
                        "movie_title": movie.get("title"),
                        "movie_id": movie_id,
                        "path": file_path
                    })
        
        if pool_candidates:
            pool_candidates.sort(key=lambda x: x["score"], reverse=True)
            winner = pool_candidates[0]
            
            print(f" -> {len(pool_candidates)} candidats analysés avec la grille de contraste.")
            print(f" ==> ÉLU : '{winner['movie_title']}' avec un score de {winner['score']}/100. (Asset: {winner['path']})")
            
            final_poster = finalize_poster(winner["image"], config["label"], config["color"])
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
            final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
            
            PROCESSED_MOVIE_IDS.add(winner["movie_id"])
        else:
            print(f" /!\\ CONSERVATION : Aucun candidat idéal validé pour {genre_name}.")

if __name__ == "__main__":
    main()

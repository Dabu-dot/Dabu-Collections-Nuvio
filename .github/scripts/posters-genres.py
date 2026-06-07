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

# Liste RESTRICTIVE des 17 genres demandés avec IDs TMDB et Couleurs Nuvio
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

# Registre global anti-doublons inter-genres
PROCESSED_MOVIE_IDS = set()

def get_popular_movies_by_genre(genre_key, config):
    """Récupère les films populaires avec les filtres de requêtes optimisés."""
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
            url += "&with_keywords=9827|209386&vote_count.gte=30"
        else:
            url += "&vote_count.gte=100"
            
        res = requests.get(url).json()
        if "results" in res and res["results"]:
            movies.extend(res["results"])
            
    return movies

def get_movie_artworks(movie_id):
    """Débloque la mine d'or en ciblant spécifiquement le catalogue Textless (language=null)."""
    # Utilisation du paramètre include_image_language=null pour cibler les versions sans texte
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={TMDB_API_KEY}&include_image_language=null"
    res = requests.get(url).json()
    
    backdrops = res.get("backdrops", [])
    posters = res.get("posters", [])
    
    for b in backdrops: b['artwork_type'] = 'backdrop'
    for p in posters: p['artwork_type'] = 'poster'
    
    # On met les posters natifs en priorité absolue puisqu'ils sont déjà au format vertical
    candidates = posters + backdrops
    return candidates

def evaluate_image_quality(img, artwork_type):
    """Vérification basique de la netteté de l'image source."""
    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    variance_laplacian = np.array(laplacian_img, dtype=np.float32).var()
    
    # Les posters d'origine ou d'animation peuvent être lisses (dessin), on se montre tolérant
    min_sharpness = 60 if artwork_type == 'poster' else 100
    if variance_laplacian < min_sharpness:
        print(f"   -> [REJET] Image trop floue ou plate (Variance: {variance_laplacian:.1f})")
        return False
    return True

def find_best_crop_x(img, target_w, faces):
    """Trouve la zone de coupe idéale pour transformer un backdrop horizontal en poster vertical."""
    W, H = img.size
    
    if faces:
        # Si un seul visage, focus centré dessus
        if len(faces) == 1:
            fx, _, fw, _ = faces[0]['box']
            face_center_x = fx + (fw // 2)
            best_x_start = face_center_x - (target_w // 2)
        else:
            # Si plusieurs visages, on prend le centre du visage principal (le plus grand à l'écran)
            main_face = max(faces, key=lambda f: f['box'][2] * f['box'][3])
            fx, _, fw, _ = main_face['box']
            best_x_start = (fx + (fw // 2)) - (target_w // 2)
            
        best_x_start = max(0, min(best_x_start, W - target_w))
        return best_x_start

    # Fallback par analyse de détails (Laplacien)
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

def draw_multiline_text_left(draw, label, font, max_width, start_x, base_y, line_spacing=12):
    words = label.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        if draw.textlength(test_line, font=font) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
        
    font_box = font.getbbox("A")
    font_height = font_box[3] - font_box[1]
    
    if len(lines) <= 1:
        draw.text((start_x, base_y), label, fill=(255, 255, 255, 255), font=font)
    else:
        adjusted_y = base_y - font_height - line_spacing
        for line in lines[:2]:
            draw.text((start_x, adjusted_y), line, fill=(255, 255, 255, 255), font=font)
            adjusted_y += font_height + line_spacing

def process_and_crop(artwork, label, target_color):
    img_url = f"https://image.tmdb.org/t/p/original{artwork['file_path']}"
    artwork_type = artwork['artwork_type']
    
    img_res = requests.get(img_url, stream=True)
    if img_res.status_code != 200:
        return None
        
    raw_img = Image.open(img_res.raw).convert("RGB")
    
    # FIX AUTO-ORIENTATION : Corrige l'orientation EXIF (évite l'effet de l'affiche inversée)
    img = ImageOps.exif_transpose(raw_img)
    W, H = img.size
    
    if W < 800 or H < 600:
        return None
        
    if not evaluate_image_quality(img, artwork_type):
        return None
        
    # Analyse IA des visages
    img_np = np.array(img)
    faces = detector.detect_faces(img_np)
    
    # RÈGLES DE VALIDATION DIFFÉRENCIÉES (Posters vs Backdrops)
    if artwork_type == 'poster':
        # On fait confiance aux posters natifs de la section Textless : on autorise les petits groupes (ex: 1 à 4 visages)
        # Mais on rejette si c'est une foule immense (> 4 visages détectés d'un coup)
        if len(faces) > 4:
            print(f"   -> [REJET POSTER] Trop de personnages/Foule détectée ({len(faces)} visages).")
            return None
    else:
        # Pour les paysages horizontaux (backdrops), on reste strict pour s'assurer d'un sujet isolable et propre
        if len(faces) > 2:
            print(f"   -> [REJET BACKDROP] Composition horizontale trop complexe ({len(faces)} visages).")
            return None

    # Découpage au format vertical
    if artwork_type == 'backdrop':
        target_w = int(H * (2/3))
        if target_w > W:
            return None
        best_x_start = find_best_crop_x(img, target_w, faces)
        if best_x_start is None:
            return None
        cropped_img = img.crop((best_x_start, 0, best_x_start + target_w, H))
    else:
        # Si c'est un poster natif, on ajuste juste les bandes latérales au ratio 2:3 en se calant sur le HAUT (Y=0)
        current_ratio = W / H
        if abs(current_ratio - (2/3)) > 0.02:
            target_w = int(H * (2/3))
            if target_w <= W:
                start_x = (W - target_w) // 2
                cropped_img = img.crop((start_x, 0, start_x + target_w, H))
            else:
                cropped_img = img
        else:
            cropped_img = img

    # Finalisation graphique standardisée Nuvio
    final_img = cropped_img.resize((800, 1200), Image.Resampling.LANCZOS)
    final_img = ImageEnhance.Contrast(final_img).enhance(1.15)
    final_img = apply_duotone(final_img, target_color)
    
    draw = ImageDraw.Draw(final_img, "RGBA")
    for y in range(750, 1200):
        alpha = int(((y - 750) / 450) ** 2.3 * 245)
        draw.line([(0, y), (800, y)], fill=(0, 0, 0, alpha))
        
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", 54)
    except IOError:
        font = ImageFont.load_default()
        
    margin_left = 60
    max_text_width = 800 - (margin_left * 2)
    target_base_y = 1070
    
    draw_multiline_text_left(draw, label, font, max_text_width, margin_left, target_base_y)
    return final_img

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- [PHASE 4] Traitement de la mine d'or Textless pour : {config['label']} ---")
        movies = get_popular_movies_by_genre(genre_name, config)
        
        top_movies = movies[:8]
        random.shuffle(top_movies)
        ordered_movies = top_movies + movies[8:]
        
        poster_created = False
        
        for movie in ordered_movies:
            movie_id = movie["id"]
            
            # Anti-doublons strict
            if movie_id in PROCESSED_MOVIE_IDS:
                continue
                
            print(f" -> Analyse du catalogue Textless de : {movie.get('title')} (ID: {movie_id})")
            artworks = get_movie_artworks(movie_id)
            
            if not artworks:
                continue
                
            # On parcourt les 12 meilleures images de la section Textless (priorité absolue aux posters d'origine)
            for art in artworks[:12]:
                final_poster = process_and_crop(art, config["label"], config["color"])
                
                if final_poster:
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
                    print(f"==> [SUCCÈS] Poster généré avec {movie.get('title')} ({art['artwork_type']}).")
                    
                    PROCESSED_MOVIE_IDS.add(movie_id)
                    poster_created = True
                    break
            if poster_created:
                break
                
        if not poster_created:
            print(f" /!\\ REPLI : Aucun artwork strict validé pour {genre_name}. Conservation de l'existant.")

if __name__ == "__main__":
    main()

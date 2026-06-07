import os
import random
import sys
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
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

def get_popular_movies_by_genre(genre_key, config):
    """Récupère les films populaires avec filtres géographiques, linguistiques et de genres croisés."""
    movies = []
    genre_id = config["id"]
    
    global_genres = ["action", "aventure", "comedie", "crime", "drame", "famille", "fantastique", "horreur", "romance", "science-fiction", "thriller"]
    geo_filter = "&with_origin_country=US|FR|GB|CA|ES|DE|IT" if genre_key in global_genres else ""

    for page in [1, 2, 3]:
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page={page}&language=fr-FR{geo_filter}&vote_count.gte=100"
        
        if genre_key == "animation-japonaise":
            url += "&with_original_language=ja"
        elif genre_key == "animation":
            url += "&without_original_language=ja|ko|zh"
        elif genre_key == "aventure":
            url += "&without_genres=16"
            
        res = requests.get(url).json()
        if "results" in res and res["results"]:
            movies.extend(res["results"])
            
    if genre_key == "aventure" and not movies:
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page=1&language=fr-FR"
        res = requests.get(url).json()
        movies = res.get("results", [])

    return movies

def get_movie_artworks(movie_id):
    """Récupère les backdrops ET les posters natifs textless, puis les trie par pertinence."""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={TMDB_API_KEY}"
    res = requests.get(url).json()
    
    backdrops = res.get("backdrops", [])
    posters = res.get("posters", [])
    
    # Filtrer strictement les images labellisées sans texte (iso_639_1 à None)
    valid_backdrops = [b for b in backdrops if b.get("iso_639_1") is None]
    valid_posters = [p for p in posters if p.get("iso_639_1") is None]
    
    # Marquage pour adapter la logique de découpe plus tard
    for b in valid_backdrops: b['artwork_type'] = 'backdrop'
    for p in valid_posters: p['artwork_type'] = 'poster'
    
    # Fusion (on explore les posters natifs en premier car ils sont déjà au bon format)
    candidates = valid_posters + valid_backdrops
    
    # Tri qualitatif TMDB (Moyenne des votes * Nombre de votes)
    candidates.sort(key=lambda x: x.get("vote_average", 0) * x.get("vote_count", 0), reverse=True)
    return candidates

def evaluate_image_quality(img, artwork_type):
    """Analyse la netteté et rejette les images avec logos incrustés ou textes résiduels."""
    gray = img.convert("L")
    
    # 1. Calcul de la variance du Laplacien (Netteté globale)
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    variance_laplacian = np.array(laplacian_img, dtype=np.float32).var()
    
    # Rejet si l'image est floue (seuil plus tolérant pour les posters d'origine souvent plus lisses)
    min_sharpness = 90 if artwork_type == 'poster' else 120
    if variance_laplacian < min_sharpness:
        print(f"   -> [REJET] Image trop floue ou plate (Variance: {variance_laplacian:.1f})")
        return False
        
    # 2. Détecteur anti-logo / anti-texte par densité de contours durs
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges_np = np.array(edges)
    edge_density = np.sum(edges_np > 180) / edges_np.size
    
    # Plus de 5% de contours vifs indique la présence de texte vectoriel ou de logos
    if edge_density > 0.05:
        print(f"   -> [REJET] Texte résiduel ou logo détecté par analyse ({edge_density*100:.2f}%)")
        return False

    return True

def find_best_crop_x(img, target_w, faces):
    """Trouve la zone de rognage horizontale optimale (visages IA ou détails Laplacien)."""
    W, H = img.size
    
    if faces:
        main_face = max(faces, key=lambda f: f['box'][2] * f['box'][3])
        fx, fy, fw, fh = main_face['box']
        face_center_x = fx + (fw // 2)
        
        best_x_start = face_center_x - (target_w // 2)
        best_x_start = max(0, min(best_x_start, W - target_w))
        
        # Règle d'exclusion latérale stricte
        crop_left = best_x_start
        crop_right = best_x_start + target_w
        for face in faces:
            x, y, w, h = face['box']
            if (x < crop_left < x + w) or (x < crop_right < x + w):
                return None
        return best_x_start

    # Analyse fréquentielle par fenêtre glissante si pas de visage humain
    gray = img.convert("L")
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    lap_np = np.array(laplacian_img)

    best_x_start = (W - target_w) // 2
    max_detail_score = 0
    step = max(1, (W - target_w) // 10)
    
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
    
    base_dark = np.array([12, 16, 26]) # Fond bleu-noir mat organique
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

def process_and_crop(artwork, label, target_color, force_subject=True):
    img_url = f"https://image.tmdb.org/t/p/original{artwork['file_path']}"
    artwork_type = artwork['artwork_type']
    
    img_res = requests.get(img_url, stream=True)
    if img_res.status_code != 200:
        return None
        
    img = Image.open(img_res.raw).convert("RGB")
    W, H = img.size
    
    # Élimination des sources trop petites pour éviter le flou
    if W < 1000 or H < 720:
        return None
        
    # Validation de la qualité intrinsèque (flou & logos)
    if not evaluate_image_quality(img, artwork_type):
        return None
        
    img_np = np.array(img)
    faces = detector.detect_faces(img_np)
    
    # 1. RÈGLE ANTI-COLLAGE (Type Star Wars / Marvel à visages multiples)
    if len(faces) > 2:
        print(f"   -> [REJET] Composition surchargée ({len(faces)} visages détectés).")
        return None
        
    # 2. RÈGLE ANTI-COMPOSITION COMPLEXE (Analyse de texture globale pour les posters natifs)
    if artwork_type == 'poster':
        edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
        edge_density = np.sum(np.array(edges) > 150) / np.array(edges).size
        if edge_density > 0.08: # Plus de 8% de contours durs sur l'image entière = surcharge visuelle
            print(f"   -> [REJET] Poster natif trop bruité ou complexe ({edge_density*100:.2f}%)")
            return None

    # Exclure les paysages vides sur les catégories clés
    if force_subject and not faces:
        if np.array(img.convert("L")).var() < 40:
            print("   -> [REJET] Absence de sujet ou contraste trop plat.")
            return None

    # Découpage adaptatif selon le format initial
    if artwork_type == 'backdrop':
        target_w = int(H * (2/3))
        if target_w > W:
            return None
        best_x_start = find_best_crop_x(img, target_w, faces)
        if best_x_start is None:
            print("   -> [REJET] Un sujet capital chevauche la ligne de coupe.")
            return None
        cropped_img = img.crop((best_x_start, 0, best_x_start + target_w, H))
    else:
        # Si c'est déjà un poster en portrait, on applique une légère découpe latérale
        # pour forcer le ratio parfait 2:3 (800x1200) sans étirer l'image
        current_ratio = W / H
        if abs(current_ratio - (2/3)) > 0.05:
            target_w = int(H * (2/3))
            if target_w <= W:
                start_x = (W - target_w) // 2
                cropped_img = img.crop((start_x, 0, start_x + target_w, H))
            else:
                cropped_img = img
        else:
            cropped_img = img

    # Redimensionnement final standardisé Nuvio
    final_img = cropped_img.resize((800, 1200), Image.Resampling.LANCZOS)
    final_img = ImageEnhance.Contrast(final_img).enhance(1.20)
    
    # Application de l'effet Duotone et de la typographie
    final_img = apply_duotone(final_img, target_color)
    draw = ImageDraw.Draw(final_img, "RGBA")
    
    # Scrim dégradé
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
        print(f"\n--- [PHASE 2.5] Traitement des Artworks pour : {config['label']} ---")
        movies = get_popular_movies_by_genre(genre_name, config)
        
        top_movies = movies[:6]
        random.shuffle(top_movies)
        ordered_movies = top_movies + movies[6:]
        
        poster_created = False
        
        for movie in ordered_movies:
            print(f" -> Analyse du catalogue de : {movie.get('title')}")
            artworks = get_movie_artworks(movie["id"])
            
            if not artworks:
                continue
                
            force_subj = False if genre_name in ["documentaire", "histoire"] else True
            
            # Analyse des 8 meilleures images filtrées par la communauté (posters + backdrops)
            for art in artworks[:8]:
                final_poster = process_and_crop(art, config["label"], config["color"], force_subject=force_subj)
                
                if final_poster:
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
                    print(f"==> [SUCCÈS] Poster généré ({art['artwork_type']}) avec le film : {movie.get('title')}.")
                    poster_created = True
                    break
            if poster_created:
                break
                
        if not poster_created:
            print(f" /!\\ ÉCHEC : Aucun artwork n'a validé les filtres d'épuration pour {genre_name}.")

if __name__ == "__main__":
    main()

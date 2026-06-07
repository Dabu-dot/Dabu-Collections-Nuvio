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

# Registre global anti-doublons (permet de ne jamais répéter un film d'un genre à un autre)
PROCESSED_MOVIE_IDS = set()

def get_popular_movies_by_genre(genre_key, config):
    """Récupère les films populaires avec requêtes chirurgicales par genre pour éviter les niches."""
    movies = []
    genre_id = config["id"]
    
    global_genres = ["action", "aventure", "comedie", "crime", "drame", "famille", "fantastique", "horreur", "romance", "science-fiction", "thriller"]
    geo_filter = "&with_origin_country=US|FR|GB|CA|ES|DE|IT" if genre_key in global_genres else ""

    for page in [1, 2, 3]:
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page={page}&language=fr-FR{geo_filter}"
        
        # Ajustement des filtres spécifiques selon les retours d'expérience
        if genre_key == "animation-japonaise":
            url += "&with_original_language=ja&vote_count.gte=100"
        elif genre_key == "animation":
            url += "&without_original_language=ja|ko|zh&vote_count.gte=100"
        elif genre_key == "aventure":
            url += "&without_genres=16&vote_count.gte=100"
        elif genre_key == "drame":
            # Pour le Drame : Uniquement des films modernes et ultra-populaires (Culte)
            url += "&primary_release_date.gte=2000-01-01&vote_count.gte=1000"
        elif genre_key == "documentaire":
            # Pour le Documentaire : Ciblage par mots-clés Nature (9827) ou Vie Sauvage (209386)
            url += "&with_keywords=9827|209386&vote_count.gte=50"
        else:
            url += "&vote_count.gte=100"
            
        res = requests.get(url).json()
        if "results" in res and res["results"]:
            movies.extend(res["results"])
            
    # Sécurité Aventure : si aucun film live-action n'est trouvé, on élargit
    if genre_key == "aventure" and not movies:
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page=1&language=fr-FR"
        res = requests.get(url).json()
        movies = res.get("results", [])

    return movies

def get_movie_artworks(movie_id):
    """Récupère les backdrops et les posters natifs textless, puis les trie par pertinence."""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={TMDB_API_KEY}"
    res = requests.get(url).json()
    
    backdrops = res.get("backdrops", [])
    posters = res.get("posters", [])
    
    valid_backdrops = [b for b in backdrops if b.get("iso_639_1") is None]
    valid_posters = [p for p in posters if p.get("iso_639_1") is None]
    
    for b in valid_backdrops: b['artwork_type'] = 'backdrop'
    for p in valid_posters: p['artwork_type'] = 'poster'
    
    candidates = valid_posters + valid_backdrops
    candidates.sort(key=lambda x: x.get("vote_average", 0) * x.get("vote_count", 0), reverse=True)
    return candidates

def evaluate_image_quality(img, artwork_type):
    """Analyse la netteté et rejette les images contenant des logos ou du texte vectoriel."""
    gray = img.convert("L")
    
    # 1. Calcul de la variance du Laplacien (Netteté globale)
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    laplacian_img = gray.filter(ImageFilter.Kernel((3, 3), kernel.flatten(), scale=1, offset=0))
    variance_laplacian = np.array(laplacian_img, dtype=np.float32).var()
    
    min_sharpness = 90 if artwork_type == 'poster' else 120
    if variance_laplacian < min_sharpness:
        print(f"   -> [REJET] Image trop floue ou plate (Variance: {variance_laplacian:.1f})")
        return False
        
    # 2. Détecteur anti-logo / anti-texte par densité de contours durs
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges_np = np.array(edges)
    edge_density = np.sum(edges_np > 180) / edges_np.size
    
    if edge_density > 0.05:
        print(f"   -> [REJET] Texte résiduel ou logo détecté par analyse ({edge_density*100:.2f}%)")
        return False

    return True

def find_best_crop_x(img, target_w, faces):
    """Calcule le point de rognage optimal. Gère le barycentre des groupes pour éviter les coupures (Option B)."""
    W, H = img.size
    
    if faces:
        # Récupération des centres X de tous les visages détectés
        centers_x = []
        for f in faces:
            fx, _, fw, _ = f['box']
            centers_x.append(fx + (fw // 2))
            
        # Option B améliorée : On calcule le milieu parfait entre le visage le plus à gauche et le plus à droite
        min_x = min(centers_x)
        max_x = max(centers_x)
        group_center_x = (min_x + max_x) // 2
        
        # Point de départ théorique centré sur le groupe
        best_x_start = group_center_x - (target_w // 2)
        best_x_start = max(0, min(best_x_start, W - target_w))
        
        # Vérification de sécurité : Est-ce qu'un des visages essentiels se fait couper avec ce point de vue ?
        crop_left = best_x_start
        crop_right = best_x_start + target_w
        
        for f in faces:
            x, _, w, _ = f['box']
            # Si une tête est coupée par la bordure gauche ou droite, on applique un ajustement dynamique (glissement)
            if x < crop_left < x + w:
                best_x_start = x - 20  # On décale un peu vers la gauche pour faire rentrer le personnage
            if x < crop_right < x + w:
                best_x_start = (x + w) - target_w + 20  # On décale vers la droite
                
        # Double sécurité après ajustement glissant
        best_x_start = max(0, min(best_x_start, W - target_w))
        crop_left = best_x_start
        crop_right = best_x_start + target_w
        
        for f in faces:
            x, _, w, _ = f['box']
            if (x < crop_left < x + w) or (x < crop_right < x + w):
                return None  # Trop large pour rentrer dans le cadre vertical, rejet.
                
        return best_x_start

    # Balayage Laplacien si pas de visage humain (Créatures, Paysages)
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

def process_and_crop(artwork, label, target_color, force_subject=True):
    img_url = f"https://image.tmdb.org/t/p/original{artwork['file_path']}"
    artwork_type = artwork['artwork_type']
    
    img_res = requests.get(img_url, stream=True)
    if img_res.status_code != 200:
        return None
        
    img = Image.open(img_res.raw).convert("RGB")
    W, H = img.size
    
    if W < 1000 or H < 720:
        return None
        
    if not evaluate_image_quality(img, artwork_type):
        return None
        
    img_np = np.array(img)
    faces = detector.detect_faces(img_np)
    
    # RÈGLE ANTI-COLLAGE (Sensibilité accrue pour rejeter les surcharges de personnages type Avengers/Mario)
    if len(faces) > 2:
        print(f"   -> [REJET] Composition surchargée ({len(faces)} visages détectés).")
        return None
        
    # RÈGLE ANTI-COMPOSITION BRUITÉE (Pour les affiches d'animation ou de synthèse complexes)
    if artwork_type == 'poster':
        edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
        edge_density = np.sum(np.array(edges) > 150) / np.array(edges).size
        if edge_density > 0.07: # Abaissement de 0.08 à 0.07 pour éliminer plus de collages complexes
            print(f"   -> [REJET] Poster natif trop dense ou surchargé ({edge_density*100:.2f}%)")
            return None

    if force_subject and not faces:
        if np.array(img.convert("L")).var() < 40:
            print("   -> [REJET] Absence de sujet ou contraste trop plat.")
            return None

    # Découpage adaptatif selon la source d'origine
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
        # CORRECTION TYPE MORTAL KOMBAT : Pour un poster vertical d'origine,
        # l'ajustement du ratio doit impérativement se caler par le HAUT (Y=0) pour éviter de couper les têtes !
        current_ratio = W / H
        if abs(current_ratio - (2/3)) > 0.02:
            target_w = int(H * (2/3))
            if target_w <= W:
                start_x = (W - target_w) // 2
                # Rognage latéral centré, mais verrouillage vertical strict en haut (0) jusqu'à H
                cropped_img = img.crop((start_x, 0, start_x + target_w, H))
            else:
                cropped_img = img
        else:
            cropped_img = img

    # Redimensionnement standardisé Nuvio
    final_img = cropped_img.resize((800, 1200), Image.Resampling.LANCZOS)
    final_img = ImageEnhance.Contrast(final_img).enhance(1.20)
    
    # Effet Duotone et Scrim
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
        print(f"\n--- [PHASE 3] Analyse des Artworks pour : {config['label']} ---")
        movies = get_popular_movies_by_genre(genre_name, config)
        
        top_movies = movies[:6]
        random.shuffle(top_movies)
        ordered_movies = top_movies + movies[6:]
        
        poster_created = False
        
        for movie in ordered_movies:
            movie_id = movie["id"]
            
            # FILTRE ANTI-DOUBLONS INTER-GENRES : On vérifie si ce film a déjà été sélectionné
            if movie_id in PROCESSED_MOVIE_IDS:
                print(f" -> [IGNORÉ] {movie.get('title')} ignoré car déjà utilisé dans une autre catégorie.")
                continue
                
            print(f" -> Analyse du catalogue de : {movie.get('title')} (ID: {movie_id})")
            artworks = get_movie_artworks(movie_id)
            
            if not artworks:
                continue
                
            force_subj = False if genre_name in ["documentaire", "histoire"] else True
            
            for art in artworks[:8]:
                final_poster = process_and_crop(art, config["label"], config["color"], force_subject=force_subj)
                
                if final_poster:
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
                    print(f"==> [SUCCÈS] Poster généré avec le film : {movie.get('title')}.")
                    
                    # Enregistrement de l'ID du film pour le blacklister des genres suivants
                    PROCESSED_MOVIE_IDS.add(movie_id)
                    poster_created = True
                    break
            if poster_created:
                break
                
        if not poster_created:
            print(f" /!\\ ÉCHEC : Aucun artwork n'a validé la charte graphique de la Phase 3 pour {genre_name}.")

if __name__ == "__main__":
    main()
            

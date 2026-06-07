import os
import random
import sys
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from mtcnn import MTCNN

# Récupération de la clé API via les secrets GitHub
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

# Liste RESTRICTIVE des 17 genres demandés avec IDs TMDB et Couleurs Nuvio
GENRES_CONFIG = {
    "action": {"id": 28, "label": "ACTION", "color": (255, 90, 0)},
    "animation-japonaise": {"id": 16, "label": "ANIMATION JAPONAISE", "color": (255, 0, 128)}, # Filtré sur pays d'origine 'ja'
    "animation": {"id": 16, "label": "ANIMATION", "color": (0, 200, 255)}, # Exclut le pays d'origine 'ja'
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

# Dossier d'exportation cible
OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"

# Initialisation du détecteur de visages (MTCNN)
detector = MTCNN()

def get_popular_movies_by_genre(genre_key, config):
    """Récupère les films populaires d'un genre, gère l'isolation Japonime."""
    movies = []
    genre_id = config["id"]
    
    for page in [1, 2, 3]:
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page={page}&language=fr-FR"
        
        if genre_key == "animation-japonaise":
            url += "&with_original_language=ja"
        elif genre_key == "animation":
            url += "&without_original_language=ja"
            
        res = requests.get(url).json()
        if "results" in res:
            movies.extend(res["results"])
    return movies

def get_movie_backdrops(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={TMDB_API_KEY}"
    res = requests.get(url).json()
    backdrops = res.get("backdrops", [])
    textless = [b for b in backdrops if b.get("iso_639_1") is None]
    return textless if textless else backdrops

def apply_duotone(img, target_color):
    gray = img.convert("L")
    gray_np = np.array(gray)
    
    base_dark = np.array([12, 16, 26]) # Fond bleu-noir cinéma mat
    target_light = np.array(target_color)
    
    duotone = np.zeros((gray_np.shape[0], gray_np.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        duotone[..., i] = base_dark[i] + (gray_np / 255.0) * (target_light[i] - base_dark[i])
        
    return Image.fromarray(duotone)

def draw_multiline_text_left(draw, label, font, max_width, start_x, base_y, line_spacing=12):
    """Ajuste le texte à gauche et le sépare sur 2 lignes si nécessaire en le remontant."""
    words = label.split()
    lines = []
    current_line = ""
    
    # Découpage logique des mots selon la largeur disponible
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
        
    # Calcul de la hauteur de la police
    font_box = font.getbbox("A")
    font_height = font_box[3] - font_box[1]
    
    # Si le texte tient sur 1 seule ligne, on applique la position standard en bas
    if len(lines) <= 1:
        draw.text((start_x, base_y), label, fill=(255, 255, 255, 255), font=font)
    else:
        # Si 2 lignes : on remonte le point de départ de la hauteur d'une ligne + espacement
        adjusted_y = base_y - font_height - line_spacing
        for line in lines[:2]: # Sécurité max 2 lignes
            draw.text((start_x, adjusted_y), line, fill=(255, 255, 255, 255), font=font)
            adjusted_y += font_height + line_spacing

def process_and_crop(img_url, label, target_color):
    img_res = requests.get(img_url, stream=True)
    if img_res.status_code != 200:
        return None
        
    img = Image.open(img_res.raw).convert("RGB")
    W, H = img.size
    
    target_w = int(H * (2/3))
    if target_w > W:
        return None
        
    img_np = np.array(img)
    faces = detector.detect_faces(img_np)
    
    best_x_start = (W - target_w) // 2
    
    if faces:
        main_face = max(faces, key=lambda f: f['box'][2] * f['box'][3])
        fx, fy, fw, fh = main_face['box']
        face_center_x = fx + (fw // 2)
        
        best_x_start = face_center_x - (target_w // 2)
        best_x_start = max(0, min(best_x_start, W - target_w))
        
        crop_left = best_x_start
        crop_right = best_x_start + target_w
        
        for face in faces:
            x, y, w, h = face['box']
            if (x < crop_left < x + w) or (x < crop_right < x + w):
                print(" -> Image rejetée : un sujet important chevauche la bordure.")
                return None

    cropped_img = img.crop((best_x_start, 0, best_x_start + target_w, H))
    cropped_img = cropped_img.resize((800, 1200), Image.Resampling.LANCZOS)
    
    enhancer = ImageEnhance.Contrast(cropped_img)
    cropped_img = enhancer.enhance(1.15)
    
    final_img = apply_duotone(cropped_img, target_color)
    draw = ImageDraw.Draw(final_img, "RGBA")
    
    # Application du fondu dégradé noir
    for y in range(750, 1200):
        alpha = int(((y - 750) / 450) ** 2.2 * 245)
        draw.line([(0, y), (800, y)], fill=(0, 0, 0, alpha))
        
    # Essai de chargement de la police OpenType demandée
    try:
        font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", 54)
    except IOError:
        font = ImageFont.load_default()
        
    # Marges et dimensions pour l'alignement à gauche
    margin_left = 60
    max_text_width = 800 - (margin_left * 2) # 680px d'espace d'écriture
    target_base_y = 1070 # Alignement vertical de la ligne du bas
    
    # Appel de l'écriture dynamique alignée à gauche
    draw_multiline_text_left(draw, label, font, max_text_width, margin_left, target_base_y)
    
    return final_img

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Recherche pour la catégorie : {config['label']} ---")
        movies = get_popular_movies_by_genre(genre_name, config)
        
        random.shuffle(movies)
        poster_created = False
        
        for movie in movies:
            print(f" Test du film : {movie.get('title')}")
            backdrops = get_movie_backdrops(movie["id"])
            
            if not backdrops:
                continue
                
            for b in backdrops[:4]:
                img_url = f"https://image.tmdb.org/t/p/original{b['file_path']}"
                final_poster = process_and_crop(img_url, config["label"], config["color"])
                
                if final_poster:
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=92)
                    final_poster.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=92)
                    print(f"-> [OK] Poster mis à jour pour '{genre_name}' avec {movie.get('title')}.")
                    poster_created = True
                    break
            if poster_created:
                break
                
        if not poster_created:
            print(f" /!\\ Aucun artwork valide trouvé aujourd'hui pour {genre_name}.")

if __name__ == "__main__":
    main()
        

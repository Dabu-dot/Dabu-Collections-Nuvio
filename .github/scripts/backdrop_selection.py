import os
import sys
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from io import BytesIO

# ==============================================================================
# GESTION DYNAMIQUE DES CHEMINS (Zéro dépendance au dossier d'exécution)
# ==============================================================================
# On détecte où est le script (.github/scripts/) et on remonte à la racine du dépôt
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

OUTPUT_DIR = os.path.join(REPO_ROOT, "Ressources", "backdrops")
FONT_PATH = os.path.join(REPO_ROOT, ".github", "assets", "fonts", "SF-Pro-Display-Bold.otf")
FONT_URL = "https://github.com/AndrewFontenot/SF-Pro-Fonts/raw/master/SF-Pro-Display-Bold.otf"

# ==============================================================================
# CONFIGURATION DES SELECTIONS
# ==============================================================================
SELECTIONS = [
    {
        "output_name": "backdrop_films.jpg",
        "url": os.getenv("BINGECAT_FILMS_URL", "https://bingecat.com/stremio/d2913855-e481-452f-8f1e-3e26410c73e5/nuvio/catalog/movie/aicat_list_19309.json?bcv=483"),
        "default_title": "Parce que vous\navez regardé..."
    }
]

def ensure_font_exists():
    """Garantit la présence de la police d'écriture, peu importe le contexte."""
    if not os.path.exists(FONT_PATH):
        print(f"Téléchargement de la police San Francisco vers : {FONT_PATH}")
        os.makedirs(os.path.dirname(FONT_PATH), exist_ok=True)
        try:
            res = requests.get(FONT_URL, timeout=15)
            res.raise_for_status()
            with open(FONT_PATH, "wb") as f:
                f.write(res.content)
            print("Police téléchargée avec succès.")
        except Exception as e:
            print(f"❌ Impossible de télécharger la police : {e}")

def create_rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), size], radius, fill=255)
    return mask

def paste_poster_with_shadow(base_canvas, poster_img, position, size, radius=28):
    """Applique un redimensionnement de précision, des coins arrondis et une ombre diffuse premium."""
    poster_resized = ImageOps.fit(poster_img, size, method=Image.Resampling.LANCZOS)
    
    # Configuration d'une ombre portée très douce et diffuse (style Apple TV)
    shadow_offset = (8, 16)
    shadow_blur = 35
    shadow_size = (size[0] + shadow_blur * 2, size[1] + shadow_blur * 2)
    
    shadow_mask = Image.new("L", shadow_size, 0)
    shadow_draw = ImageDraw.Draw(shadow_mask)
    shadow_draw.rounded_rectangle(
        [(shadow_blur, shadow_blur), (shadow_blur + size[0], shadow_blur + size[1])], 
        radius, 
        fill=150  # Ombre douce
    )
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(shadow_blur))
    shadow_layer = Image.new("RGBA", shadow_size, (0, 0, 0, 255))
    
    shadow_pos = (position[0] - shadow_blur + shadow_offset[0], position[1] - shadow_blur + shadow_offset[1])
    base_canvas.paste(shadow_layer, shadow_pos, mask=shadow_mask)
    
    # Collage du poster
    mask = create_rounded_mask(size, radius)
    base_canvas.paste(poster_resized, position, mask=mask)

def process_selection(selection_config):
    url = selection_config["url"]
    output_path = os.path.join(OUTPUT_DIR, selection_config["output_name"])
    
    print(f"\nTraitement de la sélection -> {selection_config['output_name']}...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"❌ Erreur d'accès au catalogue pour {selection_config['output_name']} : {e}")
        return
        
    metas = data.get("metas", [])
    total_items = len(metas)
    
    if total_items == 0:
        print("⚠️ Aucun média trouvé dans ce catalogue.")
        return

    media_type = "médias"
    if "/movie/" in url or "movie" in url:
        media_type = "Films"
    elif "/series/" in url or "series" in url:
        media_type = "Séries"

    title_text = selection_config["default_title"]
    footer_text = f"{total_items} {media_type.lower() if total_items > 1 else media_type[:-1].lower()}"

    top_3_items = metas[:3]
    poster_images = []
    
    for item in top_3_items:
        poster_url = item.get("poster")
        try:
            img_res = requests.get(poster_url, headers=headers, timeout=10)
            if img_res.status_code == 200:
                poster_images.append(Image.open(BytesIO(img_res.content)).convert("RGBA"))
        except Exception as e:
            print(f"Impossible de charger l'affiche {poster_url} : {e}")

    if not poster_images:
        print("❌ Impossible de récupérer les affiches nécessaires.")
        return

    # Fond avec l'effet Glow Radial Apple
    canvas_w, canvas_h = 1920, 1080
    base_canvas = Image.new("RGBA", (canvas_w, canvas_h), (13, 15, 19, 255))
    
    glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for r in range(canvas_w, 0, -5):
        alpha = int((1 - (r / canvas_w) ** 1.6) * 50)
        glow_draw.ellipse(
            [(canvas_w // 2 - r, canvas_h // 2 - r), (canvas_w // 2 + r, canvas_h // 2 + r)], 
            fill=(38, 48, 64, alpha)
        )
    base_canvas = Image.alpha_composite(base_canvas, glow)
    draw = ImageDraw.Draw(base_canvas)

    # Chargement de la police depuis son chemin absolu sécurisé
    try:
        font_title = ImageFont.truetype(FONT_PATH, 115)
        font_footer = ImageFont.truetype(FONT_PATH, 55)
        print("-> Police San Francisco chargée avec succès.")
    except Exception as e:
        print(f"⚠️ Échec chargement SF Pro ({e}), repli sur les polices système...")
        try:
            font_title = ImageFont.truetype("LiberationSans-Bold.ttf", 115)
            font_footer = ImageFont.truetype("LiberationSans-Regular.ttf", 55)
        except:
            font_title = font_footer = ImageFont.load_default()

    # Dessin des textes
    draw.text((120, 240), title_text, fill=(255, 255, 255, 255), font=font_title, spacing=25)
    draw.text((120, 850), footer_text, fill=(175, 185, 200, 220), font=font_footer)

    # Superposition des posters (Du fond vers le premier plan)
    total_loaded = len(poster_images)
    if total_loaded >= 3:
        render_queue = [
            (2, (440, 660), (1440, 210)),  # N°3 : Fond droit
            (1, (500, 750), (1240, 165)),  # N°2 : Milieu
            (0, (560, 840), (1020, 120))   # N°1 : Devant gauche (Le plus grand)
        ]
    elif total_loaded == 2:
        render_queue = [
            (1, (480, 720), (1300, 180)),
            (0, (540, 810), (1060, 135))
        ]
    else:
        render_queue = [
            (0, (560, 840), (1150, 120))
        ]

    for idx, size, pos in render_queue:
        if idx < total_loaded:
            paste_poster_with_shadow(base_canvas, poster_images[idx], pos, size)

    # Finalisation de l'image
    final_backdrop = base_canvas.convert("RGB")
    final_backdrop.save(output_path, "JPEG", quality=95)
    print(f"✨ Image sauvegardée : {output_path}")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ensure_font_exists()
    for selection in SELECTIONS:
        process_selection(selection)
    print("\n🎉 Traitement terminé.")

if __name__ == "__main__":
    main()
    

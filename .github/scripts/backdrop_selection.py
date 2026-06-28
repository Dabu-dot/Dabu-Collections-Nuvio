import os
import sys
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from io import BytesIO

# URL de votre catalogue BingeCat (par défaut vos Films recommandés)
CATALOG_URL = os.getenv("BINGECAT_CATALOG_URL", "https://bingecat.com/stremio/d2913855-e481-452f-8f1e-3e26410c73e5/nuvio/catalog/movie/aicat_list_19309.json?bcv=483")
OUTPUT_PATH = "Ressources/backdrops/backdrop_selection.jpg"
FONT_PATH = ".github/assets/fonts/SF-Pro-Display-Bold.otf"

def create_rounded_mask(size, radius):
    """Crée un masque pour obtenir des coins arrondis parfaits."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), size], radius, fill=255)
    return mask

def paste_poster_with_shadow(base_canvas, poster_img, position, size, radius=24):
    """Redimensionne un poster, applique des coins arrondis et une ombre portée type Apple TV."""
    # 1. Ajustement de la taille du poster
    poster_resized = ImageOps.fit(poster_img, size, method=Image.Resampling.LANCZOS)
    
    # 2. Conception de l'ombre portée
    shadow_offset = (10, 15)
    shadow_blur = 25
    shadow_size = (size[0] + shadow_blur * 2, size[1] + shadow_blur * 2)
    
    shadow_mask = Image.new("L", shadow_size, 0)
    shadow_draw = ImageDraw.Draw(shadow_mask)
    shadow_draw.rounded_rectangle(
        [(shadow_blur, shadow_blur), (shadow_blur + size[0], shadow_blur + size[1])], 
        radius, 
        fill=200
    )
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(shadow_blur))
    shadow_layer = Image.new("RGBA", shadow_size, (0, 0, 0, 255))
    
    # Application de l'ombre sur le canvas
    shadow_pos = (position[0] - shadow_blur + shadow_offset[0], position[1] - shadow_blur + shadow_offset[1])
    base_canvas.paste(shadow_layer, shadow_pos, mask=shadow_mask)
    
    # 3. Masquage des coins arrondis et collage du poster
    mask = create_rounded_mask(size, radius)
    base_canvas.paste(poster_resized, position, mask=mask)

def generate_backdrop():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    print("Connexion à l'API BingeCat...")
    try:
        res = requests.get(CATALOG_URL, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"Erreur lors de la récupération du catalogue : {e}")
        sys.exit(1)
        
    metas = data.get("metas", [])
    total_items = len(metas)
    
    if total_items == 0:
        print("Aucun média trouvé dans ce catalogue.")
        return

    # Détection dynamique du type de contenu et du titre
    media_type = "médias"
    title_text = "Votre Sélection\nPersonnalisée"
    
    if "/movie/" in CATALOG_URL or "movie" in CATALOG_URL:
        media_type = "Films"
        title_text = "Parce que vous\navez regardé..."
    elif "/series/" in CATALOG_URL or "series" in CATALOG_URL:
        media_type = "Séries"
        title_text = "Parce que vous\navez regardé..."

    footer_text = f"{total_items} {media_type.lower() if total_items > 1 else media_type[:-1].lower()}"

    # Extraction et téléchargement du Top 3 Better Posters
    top_3_items = metas[:3]
    poster_images = []
    
    print(f"Téléchargement du Top 3 des affiches ({total_items} éléments détectés)...")
    for item in top_3_items:
        url = item.get("poster")
        try:
            img_res = requests.get(url, timeout=10)
            if img_res.status_code == 200:
                poster_images.append(Image.open(BytesIO(img_res.content)).convert("RGBA"))
        except Exception as e:
            print(f"Impossible de charger l'affiche {url} : {e}")

    if not poster_images:
        print("Erreur critique : Aucun poster n'a pu être téléchargement.")
        return

    # Configuration du Canvas avec Dégradé Premium Sombre
    canvas_w, canvas_h = 1920, 1080
    base_canvas = Image.new("RGBA", (canvas_w, canvas_h), (15, 17, 22, 255))
    
    # Effet Glow Radial Premium en arrière-plan
    glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for r in range(canvas_w, 0, -4):
        alpha = int((1 - (r / canvas_w) ** 1.5) * 45)
        glow_draw.ellipse(
            [(canvas_w // 2 - r, canvas_h // 2 - r), (canvas_w // 2 + r, canvas_h // 2 + r)], 
            fill=(35, 43, 56, alpha)
        )
    base_canvas = Image.alpha_composite(base_canvas, glow)
    draw = ImageDraw.Draw(base_canvas)

    # Intégration des textes (Police Apple San Francisco)
    try:
        font_title = ImageFont.truetype(FONT_PATH, 115)
        font_footer = ImageFont.truetype(FONT_PATH, 55)
    except:
        print("Police San Francisco introuvable, utilisation de la police système par défaut.")
        font_title = font_footer = ImageFont.load_default()

    draw.text((120, 220), title_text, fill=(255, 255, 255, 255), font=font_title, spacing=25)
    draw.text((120, 840), footer_text, fill=(180, 188, 201, 220), font=font_footer)

    # Positionnement des posters en cascade (Arrière vers Avant)
    total_loaded = len(poster_images)
    
    if total_loaded >= 3:
        configs = [
            (2, (360, 540), (1450, 270)), # Poster de fond (Droit)
            (1, (410, 615), (1240, 232)), # Poster du milieu
            (0, (460, 690), (1020, 195))  # Poster de devant (Gauche)
        ]
    elif total_loaded == 2:
        configs = [
            (1, (420, 630), (1300, 225)),
            (0, (470, 705), (1050, 187))
        ]
    else:
        configs = [
            (0, (500, 750), (1150, 165))
        ]

    for idx, size, pos in reversed(configs):
        if idx < total_loaded:
            paste_poster_with_shadow(base_canvas, poster_images[idx], pos, size)

    # Finalisation et export
    final_backdrop = base_canvas.convert("RGB")
    final_backdrop.save(OUTPUT_PATH, "JPEG", quality=95)
    print(f"🎉 Nouveau visuel sauvegardé avec succès dans : {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_backdrop()

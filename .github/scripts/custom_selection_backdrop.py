import os
import sys
import math
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from io import BytesIO

# URL par défaut (votre liste d'options 1 : Films recommandés)
CATALOG_URL = os.getenv("BINGECAT_CATALOG_URL", "https://bingecat.com/stremio/d2913855-e481-452f-8f1e-3e26410c73e5/nuvio/catalog/movie/aicat_list_19309.json?bcv=483")
OUTPUT_PATH = "Ressources/backdrops/backdrop_du_jour.jpg"
FONT_PATH = ".github/assets/fonts/SF-Pro-Display-Bold.otf"

def create_rounded_mask(size, radius):
    """Crée un masque pour obtenir des coins arrondis parfaits."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), size], radius, fill=255)
    return mask

def paste_poster_with_shadow(base_canvas, poster_img, position, size, radius=24):
    """Redimensionne un poster, lui applique des coins arrondis et une ombre portée Apple TV."""
    # 1. Redimensionnement du poster
    poster_resized = ImageOps.fit(poster_img, size, method=Image.Resampling.LANCZOS)
    
    # 2. Création de l'ombre portée
    shadow_offset = (10, 15)
    shadow_blur = 25
    shadow_size = (size[0] + shadow_blur * 2, size[1] + shadow_blur * 2)
    
    shadow_mask = Image.new("L", shadow_size, 0)
    shadow_draw = ImageDraw.Draw(shadow_mask)
    shadow_draw.rounded_rectangle(
        [(shadow_blur, shadow_blur), (shadow_blur + size[0], shadow_blur + size[1])], 
        radius, 
        fill=200 # Intensité de l'ombre
    )
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(shadow_blur))
    
    shadow_layer = Image.new("RGBA", shadow_size, (0, 0, 0, 255))
    
    # Coller l'ombre sur le canvas global
    shadow_pos = (position[0] - shadow_blur + shadow_offset[0], position[1] - shadow_blur + shadow_offset[1])
    base_canvas.paste(shadow_layer, shadow_pos, mask=shadow_mask)
    
    # 3. Application des coins arrondis au poster et collage
    mask = create_rounded_mask(size, radius)
    base_canvas.paste(poster_resized, position, mask=mask)

def generate_backdrop():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    # Étape 1 : Récupération du catalogue BingeCat
    print("Connexion à l'API BingeCat...")
    try:
        res = requests.get(CATALOG_URL, timeout=15)
        res.raise_for_status()
        data = response_data = res.json()
    except Exception as e:
        print(f"Erreur lors de la récupération du catalogue : {e}")
        sys.exit(1)
        
    metas = data.get("metas", [])
    total_items = len(metas)
    
    if total_items == 0:
        print("Aucun média trouvé dans ce catalogue.")
        return

    # Détection dynamique du type de média et titre
    media_type = "médias"
    title_text = "Votre Sélection\nPersonnalisée"
    
    if "/movie/" in CATALOG_URL or "movie" in CATALOG_URL:
        media_type = "Films"
        title_text = "Parce que vous\navez regardé..."
    elif "/series/" in CATALOG_URL or "series" in CATALOG_URL:
        media_type = "Séries"
        title_text = "Parce que vous\navez regardé..."

    footer_text = f"{total_items} {media_type.lower() if total_items > 1 else media_type[:-1].lower()}"

    # Étape 2 : Téléchargement du Top 3 des posters (Better Posters)
    top_3_items = metas[:3]
    poster_images = []
    
    print(f"Téléchargement du Top 3 des affiches ({total_items} éléments au total)...")
    for item in top_3_items:
        url = item.get("poster")
        try:
            img_res = requests.get(url, timeout=10)
            if img_res.status_code == 200:
                poster_images.append(Image.open(BytesIO(img_res.content)).convert("RGBA"))
        except Exception as e:
            print(f"Impossible de télécharger l'affiche {url} : {e}")

    if not poster_images:
        print("Erreur : Aucun poster n'a pu être récupéré.")
        return

    # Étape 3 : Création du Canvas avec Dégradé Premium (Fond Sombre)
    canvas_w, canvas_h = 1920, 1080
    base_canvas = Image.new("RGBA", (canvas_w, canvas_h), (15, 17, 22, 255))
    
    # Génération d'un dégradé radial subtil pour le côté premium
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

    # Étape 4 : Dessiner les Textes (Style Apple TV avec San Francisco Font)
    try:
        font_title = ImageFont.truetype(FONT_PATH, 115)
        font_footer = ImageFont.truetype(FONT_PATH, 55)
    except:
        print("Police San Francisco introuvable, utilisation de la police par défaut.")
        font_title = font_footer = ImageFont.load_default()

    # Alignement à gauche
    draw.text((120, 220), title_text, fill=(255, 255, 255, 255), font=font_title, spacing=25)
    draw.text((120, 840), footer_text, fill=(180, 188, 201, 220), font=font_footer)

    # Étape 5 : Superposition en cascade des 3 posters (Rendu conforme à file `1000344457.webp`)
    # Structure de l'empilement (Arrière-plan vers Avant-plan)
    # Poster 3 (Petit, tout au fond à droite) -> Poster 2 (Moyen, milieu) -> Poster 1 (Grand, devant à gauche)
    
    configurations = [
        # {"index": 2, "size": (350, 525), "pos": (1480, 277)},  # Troisième plan (Droit)
        # {"index": 1, "size": (400, 600), "pos": (1260, 240)},  # Second plan (Milieu)
        # {"index": 0, "size": (450, 675), "pos": (1020, 202)}   # Premier plan (Gauche - Pleine visibilité)
    ]
    
    # On inverse l'ordre dans la boucle pour coller du fond vers l'avant (Back to Front)
    total_loaded = len(poster_images)
    
    # Définition des tailles et positions relatives adaptées dynamiquement au nombre d'images dispos
    if total_loaded >= 3:
        configs = [
            (2, (360, 540), (1450, 270)), # Fond
            (1, (410, 615), (1240, 232)), # Milieu
            (0, (460, 690), (1020, 195))  # Devant
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

    # Étape 6 : Exportation finale
    final_backdrop = base_canvas.convert("RGB")
    final_backdrop.save(OUTPUT_PATH, "JPEG", quality=95)
    print(f"🎉 Rendu Apple TV généré avec succès dans : {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_backdrop()

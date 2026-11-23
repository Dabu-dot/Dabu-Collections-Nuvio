#!/usr/bin/env python3
"""
Backdrop "Tendances cette semaine" - Concept : Podium de la semaine (finition premium).

Le top 3 de /trending/all/week est posé sur un podium de verre (2 - 1 - 3), le numéro 1 au
centre et plus haut. Le podium est décalé à droite pour laisser la zone gauche libre, comme
dans les backdrops de streaming (titre de la collection affiché par l'application).

Rendu : lueur ambiante tirée du poster n°1, faisceau de lumière, marches en verre avec reflet
diagonal et liseré lumineux, posters avec lumière de bord, ombres portées et reflet au sol,
chiffres de rang en dégradé.

Usage :
    python3 backdrop-tendances.py --api-key "$TMDB_API_KEY" --output "chemin/trending.jpg"
    python3 backdrop-tendances.py --demo --output "apercu.jpg"   # sans clé, posters factices
"""

import argparse
import io
import random
import shutil
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"
POSTER_SIZE = "w780"
TRENDING_LANGUAGE = "fr-FR"
TRENDING_MAX_PAGES = 3

QUALITY_PRESETS = {
    "compressed": {"quality": 95, "progressive": True}
}

SIZE_PRESETS = {
    "1080p": (1920, 1080, 1.0),
    "4k": (3840, 2160, 2.0),
}

# --- PALETTE (même structure que BRAND_PALETTES du script streaming) ---
PALETTE = {"base": (22, 8, 2), "mid": (120, 42, 6), "light": (242, 112, 32)}

# --- GÉOMÉTRIE DU PODIUM (valeurs en pixels pour du 1080p, multipliées par `scale`) ---
CARD_RADIUS = 24
PODIUM_CENTER_X = 1290       # centre horizontal du podium (la zone gauche reste libre)
STEP_W = 350
STEP_GAP = 28
STEP_TOPS = {1: 640, 2: 722, 3: 790}          # ordonnée du haut de chaque marche
POSTER_SIZES = {1: (360, 540), 2: (320, 480), 3: (320, 480)}
DISPLAY_ORDER = (2, 1, 3)    # de gauche à droite

# --- RÉGLAGES DE FINITION ---
SIDE_DIM = 0.10              # assombrissement des posters 2 et 3 (le n°1 reste le point focal)
REFLECTION_H = 120           # hauteur du reflet sous chaque poster
REFLECTION_ALPHA = 85        # opacité du reflet à la base du poster (0-255)
RANK_FONT_SIZE = 170
RANK_CENTER_Y = 195          # centre du chiffre, mesuré depuis le haut de la marche
AMBIENT_ALPHA = 110          # intensité de la lueur tirée du poster n°1 (0-255)
GLOW_ALPHA = 120             # halo chaud derrière le poster n°1 (0-255)
BEAM_ALPHA = 34              # faisceau de lumière vertical (0-255)

# --- SÉCURITÉ DE CONTENU (identique au script streaming) ---
BANNED_IDS = {12361, 219416, 156096, 12543, 193204, 230113, 195669}
BANNED_WORDS = ["ecchi", "harem", "fan service", "fanservice", "soft-core", "suggestive",
                "sinful", "nudity", "erotic", "sensual"]

FONT_CANDIDATES = [
    str(REPO_ROOT / ".github" / "assets" / "fonts" / "SF-Pro-Display-Bold.otf"),  # police du dépôt
    "LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def cleanup_pycache():
    shutil.rmtree(SCRIPT_DIR / "__pycache__", ignore_errors=True)


# ==============================================================================
# TMDB
# ==============================================================================
def tmdb_get(endpoint, params, api_key):
    query = dict(params)
    query["api_key"] = api_key
    for attempt in range(3):
        try:
            response = requests.get(f"{TMDB_BASE}{endpoint}", params=query, timeout=20)
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def is_clean_content(media_type, item, api_key):
    title = (item.get("name") or item.get("title") or "").lower()
    overview = (item.get("overview") or "").lower()

    for word in BANNED_WORDS:
        if word in title or word in overview:
            return False

    try:
        item_id = item["id"]
        endpoint = f"/tv/{item_id}/keywords" if media_type == "tv" else f"/movie/{item_id}/keywords"
        data = tmdb_get(endpoint, {}, api_key)
        keywords = data.get("keywords", []) if media_type == "movie" else data.get("results", [])

        for kw in keywords:
            kw_id = kw.get("id")
            kw_name = kw.get("name", "").lower()
            if kw_id in BANNED_IDS or any(w in kw_name for w in BANNED_WORDS):
                return False
    except Exception:
        pass
    return True


def iter_trending_candidates(api_key):
    """Génère les titres tendance de la semaine, dans l'ordre TMDB, déjà filtrés."""
    seen = set()
    for page in range(1, TRENDING_MAX_PAGES + 1):
        data = tmdb_get("/trending/all/week", {"language": TRENDING_LANGUAGE, "page": page}, api_key)
        results = data.get("results", [])
        if not results:
            return
        for item in results:
            media_type = item.get("media_type")
            if media_type not in ("movie", "tv"):
                continue
            key = (media_type, item.get("id"))
            if key in seen or item.get("adult") or not item.get("poster_path"):
                continue
            seen.add(key)
            if is_clean_content(media_type, item, api_key):
                yield item


def download_image_url(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except Exception:
        return None


def fetch_top_posters(api_key, count=3):
    """Retourne `count` posters téléchargés (rang 1 en premier)."""
    posters = []
    for item in iter_trending_candidates(api_key):
        img = download_image_url(f"{TMDB_IMG_BASE}/{POSTER_SIZE}{item['poster_path']}")
        if img is None:
            continue
        title = item.get("title") or item.get("name") or "?"
        print(f" -> #{len(posters) + 1} : {title} ({item['media_type']})")
        posters.append(img)
        if len(posters) == count:
            break
    return posters


def make_demo_posters(count=3):
    """Posters factices (dégradés colorés) pour prévisualiser la mise en page sans API."""
    rng = random.Random(42)
    font = load_font(120)
    posters = []
    for rank in range(1, count + 1):
        c1 = tuple(rng.randint(30, 220) for _ in range(3))
        c2 = tuple(rng.randint(10, 120) for _ in range(3))
        img = Image.new("RGBA", (780, 1170))
        px = img.load()
        for y in range(1170):
            t = y / 1169
            col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,)
            for x in range(780):
                px[x, y] = col
        ImageDraw.Draw(img).text((390, 585), f"DEMO {rank}", font=font, fill=(255, 255, 255, 200), anchor="mm")
        posters.append(img)
    return posters


# ==============================================================================
# OUTILS DE RENDU
# ==============================================================================
def load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default(size=size)


def composite_at(dst, src, x, y):
    """Compose `src` sur `dst` en (x, y) avec un vrai alpha-blending, découpé aux bords."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.width, x + src.width), min(dst.height, y + src.height)
    if x0 >= x1 or y0 >= y1:
        return
    part = src.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    region = dst.crop((x0, y0, x1, y1))
    dst.paste(Image.alpha_composite(region, part), (x0, y0))


def vertical_fade(width, height, top_value, bottom_value):
    """Image 'L' en dégradé vertical, de `top_value` (haut) à `bottom_value` (bas)."""
    grad = Image.linear_gradient("L").resize((width, height))
    return grad.point(lambda v: int(top_value + (bottom_value - top_value) * v / 255))


def generate_diagonal_gradient(width, height, palette):
    """Même dégradé que le script streaming (clair en bas à gauche), calculé en basse
    résolution puis agrandi : visuellement identique, bien plus rapide."""
    sw, sh = max(2, width // 8), max(2, height // 8)
    small = Image.new("RGBA", (sw, sh))
    pixels = small.load()
    c_dark, c_mid, c_light = palette["base"], palette["mid"], palette["light"]

    for y in range(sh):
        for x in range(sw):
            factor = (x / sw + (sh - y) / sh) / 2.0
            factor = max(0.0, min(1.0, factor))
            if factor < 0.5:
                t, a, b = factor * 2.0, c_light, c_mid
            else:
                t, a, b = (factor - 0.5) * 2.0, c_mid, c_dark
            pixels[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)

    return small.resize((width, height), Image.BICUBIC)


def add_grain(image):
    """Grain très léger pour casser le banding des grands aplats sombres."""
    noise = Image.effect_noise(image.size, 40).point(lambda v: max(0, min(8, (v - 128) // 8 + 4)))
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    rgb = ImageChops.add(image.convert("RGB"), noise_rgb, scale=1.0, offset=-4)
    return rgb.convert("RGBA")


# ==============================================================================
# ÉCLAIRAGE
# ==============================================================================
def make_ambient(hero, canvas_size, center, scale):
    """Lueur douce aux couleurs du poster n°1 (principe des fonds d'Apple TV)."""
    w, h = int(1100 * scale), int(1300 * scale)
    art = hero.convert("RGB").resize((32, 48), Image.LANCZOS)
    art = ImageEnhance.Color(art).enhance(1.5).resize((w, h), Image.BICUBIC)
    art = art.filter(ImageFilter.GaussianBlur(int(90 * scale)))
    # Ellipse floutée qui s'éteint bien avant les bords (radial_gradient n'atteint pas 0 sur les côtés)
    falloff = Image.new("L", (w, h), 0)
    ImageDraw.Draw(falloff).ellipse([int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)], fill=AMBIENT_ALPHA)
    falloff = falloff.filter(ImageFilter.GaussianBlur(int(110 * scale)))
    layer = art.convert("RGBA")
    layer.putalpha(falloff)
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    composite_at(out, layer, center[0] - w // 2, center[1] - h // 2)
    return out


def make_glow(canvas_size, center, radius, color, alpha):
    """Halo lumineux doux derrière le poster n°1."""
    mask = Image.new("L", canvas_size, 0)
    cx, cy = center
    ImageDraw.Draw(mask).ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=radius // 2))
    layer = Image.new("RGBA", canvas_size, color + (0,))
    layer.putalpha(mask)
    return layer


def make_beam(canvas_size, cx, bottom_y, scale):
    """Faisceau de lumière qui descend du haut de l'image jusqu'au podium."""
    mask = Image.new("L", canvas_size, 0)
    half_top, half_bottom = int(70 * scale), int(400 * scale)
    ImageDraw.Draw(mask).polygon(
        [(cx - half_top, 0), (cx + half_top, 0), (cx + half_bottom, bottom_y), (cx - half_bottom, bottom_y)],
        fill=BEAM_ALPHA,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(int(70 * scale)))
    layer = Image.new("RGBA", canvas_size, (255, 214, 170, 0))
    layer.putalpha(mask)
    return layer


# ==============================================================================
# POSTERS
# ==============================================================================
def make_poster_card(image, tile_width, tile_height, scale, dim=0.0):
    """Poster recadré, coins arrondis, lumière de bord (plus vive en haut)."""
    src_w, src_h = image.size
    target_ratio = tile_width / tile_height

    if src_w / src_h > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        image = image.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        image = image.crop((0, top, src_w, top + new_h))

    image = image.resize((tile_width, tile_height), Image.LANCZOS).convert("RGB")
    if dim:
        image = ImageEnhance.Brightness(image).enhance(1.0 - dim)

    radius = max(14, int(CARD_RADIUS * scale))
    mask = Image.new("L", (tile_width, tile_height), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tile_width - 1, tile_height - 1], radius=radius, fill=255)

    card = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    card.paste(image, mask=mask)

    outline = Image.new("L", (tile_width, tile_height), 0)
    ImageDraw.Draw(outline).rounded_rectangle(
        [0, 0, tile_width - 1, tile_height - 1], radius=radius, outline=255, width=max(2, int(2 * scale))
    )
    rim_alpha = ImageChops.multiply(outline, vertical_fade(tile_width, tile_height, 190, 40))
    rim = Image.new("RGBA", (tile_width, tile_height), (255, 255, 255, 0))
    rim.putalpha(rim_alpha)
    return Image.alpha_composite(card, rim)


def make_poster_tile(card, scale):
    """Poster + ombre portée en deux couches (large et diffuse + serrée au contact)."""
    pad = int(80 * scale)
    w, h = card.size
    radius = max(14, int(CARD_RADIUS * scale))
    tile = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))

    for blur, offset, alpha in ((30, 26, 150), (8, 7, 130)):
        shadow = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [pad, pad + int(offset * scale), pad + w - 1, pad + int(offset * scale) + h - 1],
            radius=radius,
            fill=(0, 0, 0, alpha),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(int(blur * scale)))
        tile = Image.alpha_composite(tile, shadow)

    tile.alpha_composite(card, dest=(pad, pad))
    return tile, pad


def make_reflection(card, scale):
    """Reflet du poster sur le verre : image retournée, estompée vers le bas."""
    w, h = card.size
    rh = int(REFLECTION_H * scale)
    flipped = card.transpose(Image.FLIP_TOP_BOTTOM).crop((0, 0, w, rh))
    fade = Image.linear_gradient("L").resize((w, rh)).point(
        lambda v: int(REFLECTION_ALPHA * (1 - v / 255) ** 1.6)
    )
    flipped.putalpha(ImageChops.multiply(flipped.getchannel("A"), fade))
    return flipped


# ==============================================================================
# PODIUM
# ==============================================================================
def make_step(width, height, scale):
    """Marche de verre : corps dégradé, reflet diagonal, liseré lumineux qui s'estompe vers le bas."""
    radius = max(14, int(CARD_RADIUS * scale))
    corners = (True, True, False, False)

    shape = Image.new("L", (width, height), 0)
    ImageDraw.Draw(shape).rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=255, corners=corners)

    gloss = Image.new("L", (width, height), 0)
    ImageDraw.Draw(gloss).polygon(
        [(0, 0), (int(width * 0.62), 0), (int(width * 0.18), int(height * 0.8)), (0, int(height * 0.8))], fill=26
    )
    gloss = gloss.filter(ImageFilter.GaussianBlur(int(18 * scale)))

    alpha = ImageChops.add(vertical_fade(width, height, 74, 12), gloss)
    body = Image.new("RGBA", (width, height), (255, 238, 226, 0))
    body.putalpha(ImageChops.multiply(alpha, shape))

    edge = Image.new("L", (width, height), 0)
    ImageDraw.Draw(edge).rounded_rectangle(
        [0, 0, width - 1, height - 1], radius=radius, outline=255, width=max(2, int(2 * scale)), corners=corners
    )
    edge = ImageChops.multiply(edge, vertical_fade(width, height, 215, 25))
    rim = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    rim.putalpha(edge)
    return Image.alpha_composite(body, rim)


def make_step_shadow(width, height, scale):
    """Ombre portée diffuse de la marche sur le fond."""
    pad = int(60 * scale)
    radius = max(14, int(CARD_RADIUS * scale))
    shadow = Image.new("RGBA", (width + 2 * pad, height + pad), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [pad, pad, pad + width - 1, pad + height + pad], radius=radius, fill=(0, 0, 0, 120)
    )
    return shadow.filter(ImageFilter.GaussianBlur(int(30 * scale))), pad


def make_rank_numeral(rank, scale):
    """Chiffre de rang rempli d'un dégradé vertical blanc, plus lumineux en haut."""
    font = load_font(int(RANK_FONT_SIZE * scale))
    left, top, right, bottom = font.getbbox(str(rank))
    w, h = right - left + 8, bottom - top + 8
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((w // 2, h // 2), str(rank), font=font, fill=255, anchor="mm")
    alpha = ImageChops.multiply(mask, vertical_fade(w, h, 215, 35))
    numeral = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    numeral.putalpha(alpha)
    return numeral


def build_podium(posters, width, height, scale):
    """Assemble : lumière, ombres des marches, marches, reflets, chiffres, puis posters."""
    canvas_size = (width, height)
    step_w = int(STEP_W * scale)
    gap = int(STEP_GAP * scale)
    total_w = 3 * step_w + 2 * gap
    left = int(PODIUM_CENTER_X * scale) - total_w // 2

    steps_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    posters_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    light_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

    slots = []
    for slot, rank in enumerate(DISPLAY_ORDER):
        if rank > len(posters):
            continue
        step_x = left + slot * (step_w + gap)
        step_top = int(STEP_TOPS[rank] * scale)
        pw, ph = (int(v * scale) for v in POSTER_SIZES[rank])
        slots.append((rank, step_x, step_top, pw, ph))

    # 1) lumière derrière le poster n°1
    for rank, step_x, step_top, pw, ph in slots:
        if rank == 1:
            cx = step_x + step_w // 2
            light_layer = Image.alpha_composite(light_layer, make_beam(canvas_size, cx, step_top, scale))
            light_layer = Image.alpha_composite(
                light_layer,
                make_glow(canvas_size, (cx, step_top - ph // 2), int(420 * scale), PALETTE["light"], GLOW_ALPHA),
            )

    # 2) ombres portées de toutes les marches (avant les corps, pour ne pas empiéter sur les voisines)
    for rank, step_x, step_top, pw, ph in slots:
        step_h = height - step_top + int(CARD_RADIUS * scale)
        shadow, spad = make_step_shadow(step_w, step_h, scale)
        composite_at(steps_layer, shadow, step_x - spad, step_top - spad + int(10 * scale))

    # 3) marches, chiffres, reflets, puis posters
    for rank, step_x, step_top, pw, ph in slots:
        step_h = height - step_top + int(CARD_RADIUS * scale)
        composite_at(steps_layer, make_step(step_w, step_h, scale), step_x, step_top)

        numeral = make_rank_numeral(rank, scale)
        composite_at(
            steps_layer, numeral,
            step_x + (step_w - numeral.width) // 2,
            step_top + int(RANK_CENTER_Y * scale) - numeral.height // 2,
        )

        card = make_poster_card(posters[rank - 1], pw, ph, scale, dim=0.0 if rank == 1 else SIDE_DIM)
        px = step_x + (step_w - pw) // 2
        py = step_top - ph

        contact = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        ImageDraw.Draw(contact).rounded_rectangle(
            [px + int(pw * 0.05), step_top - int(5 * scale), px + int(pw * 0.95), step_top + int(7 * scale)],
            radius=int(6 * scale), fill=(0, 0, 0, 170),
        )
        steps_layer = Image.alpha_composite(steps_layer, contact.filter(ImageFilter.GaussianBlur(int(6 * scale))))
        composite_at(steps_layer, make_reflection(card, scale), px, step_top + int(2 * scale))

        tile, tpad = make_poster_tile(card, scale)
        composite_at(posters_layer, tile, px - tpad, py - tpad)

    return Image.alpha_composite(Image.alpha_composite(light_layer, steps_layer), posters_layer), slots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", help="TMDB API key (inutile avec --demo)")
    parser.add_argument("--output", required=True, help="Output target path (.jpg)")
    parser.add_argument("--size", default="1080p", choices=SIZE_PRESETS.keys(), help="Output size preset")
    parser.add_argument("--demo", action="store_true", help="Posters factices, sans appel TMDB")
    args = parser.parse_args()

    if args.demo:
        posters = make_demo_posters()
    else:
        if not args.api_key:
            print("Error: --api-key est requis sans --demo.")
            sys.exit(1)
        print("Compiling Podium 'Tendances cette semaine'")
        posters = fetch_top_posters(args.api_key, count=3)

    render_and_save(posters, args.output, args.size)


def render_and_save(posters, output, size="1080p"):
    if len(posters) < 3:
        print(f"Error: {len(posters)}/3 posters récupérés, podium incomplet. Aucun fichier écrit.")
        sys.exit(1)

    width, height, scale = SIZE_PRESETS[size]
    podium, slots = build_podium(posters, width, height, scale)

    hero_slot = next(s for s in slots if s[0] == 1)
    hero_center = (hero_slot[1] + int(STEP_W * scale) // 2, hero_slot[2] - hero_slot[4] // 2)

    background = generate_diagonal_gradient(width, height, PALETTE)
    background = Image.alpha_composite(background, make_ambient(posters[0], (width, height), hero_center, scale))
    background = add_grain(background)
    final = Image.alpha_composite(background, podium).convert("RGB")

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    settings = QUALITY_PRESETS["compressed"]
    final.save(out_path, "JPEG", quality=settings["quality"], optimize=True, progressive=settings["progressive"])
    final.save(out_path.with_suffix(".webp"), "WEBP", quality=settings["quality"], method=6)
    print(f"Successfully rendered podium backdrop: {out_path}")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_pycache()

#!/usr/bin/env python3
"""
Backdrop "Tendances cette semaine" - Concept : Podium de la semaine.

Le top 3 de /trending/all/week est posé sur un podium (2 - 1 - 3), le numéro 1 au centre
et plus haut. Le podium est décalé à droite pour laisser la zone gauche libre, comme dans
les backdrops de streaming (titre de la collection affiché par l'application).

Usage :
    python3 backdrop-tendances.py --api-key "$TMDB_API_KEY" --output "chemin/tendances.jpg"
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
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
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
CARD_RADIUS = 22
PODIUM_CENTER_X = 1300       # centre horizontal du podium (la zone gauche reste libre)
STEP_W = 340
STEP_GAP = 24
STEP_TOPS = {1: 650, 2: 730, 3: 790}          # ordonnée du haut de chaque marche
POSTER_SIZES = {1: (336, 504), 2: (300, 450), 3: (300, 450)}
POSTER_MARGIN = 18           # espace entre le poster et sa marche
RANK_FONT_SIZE = 150
DISPLAY_ORDER = (2, 1, 3)    # de gauche à droite

# --- SÉCURITÉ DE CONTENU (identique au script streaming) ---
BANNED_IDS = {12361, 219416, 156096, 12543, 193204, 230113, 195669}
BANNED_WORDS = ["ecchi", "harem", "fan service", "fanservice", "soft-core", "suggestive",
                "sinful", "nudity", "erotic", "sensual"]

REPO_ROOT = SCRIPT_DIR.parent.parent
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
# RENDU
# ==============================================================================
def load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default(size=size)


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


def make_premium_tile(image, tile_width, tile_height, scale):
    """Poster recadré, coins arrondis et ombre portée (identique au script streaming)."""
    src_w, src_h = image.size
    target_ratio = tile_width / tile_height
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        image = image.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        image = image.crop((0, top, src_w, top + new_h))

    image = image.resize((tile_width, tile_height), Image.LANCZOS)

    radius = max(14, int(CARD_RADIUS * scale))
    mask = Image.new("L", (tile_width, tile_height), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tile_width - 1, tile_height - 1], radius=radius, fill=255)

    poster_card = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    poster_card.paste(image, mask=mask)

    shadow_padding = int(36 * scale)
    shadow_w = tile_width + (shadow_padding * 2)
    shadow_h = tile_height + (shadow_padding * 2)

    shadow_layer = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).rounded_rectangle(
        [shadow_padding, shadow_padding, shadow_padding + tile_width - 1, shadow_padding + tile_height - 1],
        radius=radius,
        fill=(0, 0, 0, 210),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(14 * scale)))

    tile_container = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    tile_container.paste(shadow_layer, (0, int(8 * scale)))
    tile_container.paste(poster_card, (shadow_padding, shadow_padding), poster_card)
    return tile_container


def make_glow(canvas_size, center, radius, color, alpha):
    """Halo lumineux doux derrière le poster n°1."""
    mask = Image.new("L", canvas_size, 0)
    cx, cy = center
    ImageDraw.Draw(mask).ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=radius // 2))
    layer = Image.new("RGBA", canvas_size, color + (0,))
    layer.putalpha(mask)
    return layer


def draw_step(layer, x, top, width, rank, scale):
    """Marche translucide à coins supérieurs arrondis, qui se prolonge sous le canevas."""
    canvas_h = layer.size[1]
    radius = max(14, int(CARD_RADIUS * scale))
    height = canvas_h - top + radius

    fade = Image.linear_gradient("L").resize((width, height))
    alpha = fade.point(lambda v: int(100 - 84 * v / 255))
    corners = Image.new("L", (width, height), 0)
    ImageDraw.Draw(corners).rounded_rectangle(
        [0, 0, width - 1, height - 1], radius=radius, fill=255, corners=(True, True, False, False)
    )
    alpha = ImageChops.multiply(alpha, corners)

    step = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    step.putalpha(alpha)
    layer.paste(step, (x, top), step)

    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        [x, top, x + width - 1, top + height - 1],
        radius=radius,
        outline=(255, 255, 255, 80),
        width=max(1, int(2 * scale)),
        corners=(True, True, False, False),
    )
    draw.text(
        (x + width // 2, top + int(130 * scale)),
        str(rank),
        font=load_font(int(RANK_FONT_SIZE * scale)),
        fill=(255, 255, 255, 90),
        anchor="mm",
    )


def build_podium(posters, width, height, scale):
    """Assemble le podium : halo, marches, puis posters (avec leur ombre)."""
    canvas_size = (width, height)
    step_w = int(STEP_W * scale)
    gap = int(STEP_GAP * scale)
    total_w = 3 * step_w + 2 * gap
    left = int(PODIUM_CENTER_X * scale) - total_w // 2

    steps_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    posters_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    glow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    shadow_padding = int(36 * scale)

    for slot, rank in enumerate(DISPLAY_ORDER):
        if rank > len(posters):
            continue
        step_x = left + slot * (step_w + gap)
        step_top = int(STEP_TOPS[rank] * scale)
        draw_step(steps_layer, step_x, step_top, step_w, rank, scale)

        pw, ph = (int(v * scale) for v in POSTER_SIZES[rank])
        px = step_x + (step_w - pw) // 2
        py = step_top - int(POSTER_MARGIN * scale) - ph

        tile = make_premium_tile(posters[rank - 1], pw, ph, scale)
        posters_layer.paste(tile, (px - shadow_padding, py - shadow_padding), tile)

        if rank == 1:
            glow_layer = make_glow(canvas_size, (px + pw // 2, py + ph // 2), int(380 * scale),
                                   PALETTE["light"], 120)

    return Image.alpha_composite(Image.alpha_composite(glow_layer, steps_layer), posters_layer)


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

    if len(posters) < 3:
        print(f"Error: {len(posters)}/3 posters récupérés, podium incomplet. Aucun fichier écrit.")
        sys.exit(1)

    width, height, scale = SIZE_PRESETS[args.size]
    background = add_grain(generate_diagonal_gradient(width, height, PALETTE))
    podium = build_podium(posters, width, height, scale)
    final = Image.alpha_composite(background, podium).convert("RGB")

    out_path = Path(args.output)
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

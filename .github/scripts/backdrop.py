#!/usr/bin/env python3
"""
Backdrop generator driven entirely by explicit TMDB request parameters.
Modified: Prioritizes backdrops WITH local logos (FR > EN) and de-emphasizes 4K resolution.
"""

import argparse
import colorsys
import contextlib
import io
import itertools
import math
import os
import shutil
import sys
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qsl

import requests
from PIL import Image, ImageDraw, ImageFilter

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"
BACKDROP_SIZE = "w1280"
FANART_BASE = "https://webservice.fanart.tv/v3"
QUALITY_PRESETS = {
    "compressed": {"quality": 82, "progressive": True, "subsampling": "4:2:0"},
    "high": {"quality": 95, "progressive": False, "subsampling": 0},
}

CARD_RADIUS = 9
TILT_DEG = 10
TILE_W = 372
TILE_H = 210
GAP = 9
ROWS = 10
COLS = 10
STAGGER = 0.5
FOCUS_X = 0.5
FOCUS_Y = 0.53

FOCUS_PRESETS = {
    "center": (0.50, 0.50),
    "top-right": (0.72, 0.28),
    "center-right": (0.65, 0.45),
    "top-center": (0.52, 0.30),
}

SIZE_PRESETS = {
    "4k": (3840, 2160, 3840 / 1920),
    "1080p": (1920, 1080, 1.0),
}

WESTERN_LANGUAGES = {"fr", "en", "es", "de", "it"}
BANNED_KEYWORDS = {
    195669, 155477, 198385, 256466, 155716, 190340, 156201, 291195, 
    242216, 33998, 190370, 186107, 10053, 910, 348517, 9835, 18321, 
    267122, 356759
}
FAMILY_BANNED_KEYWORDS = {3036, 11001, 192947, 273060, 282071, 243261, 279473}


def cleanup_pycache():
    shutil.rmtree(SCRIPT_DIR / "__pycache__", ignore_errors=True)


def normalize_media_type(value):
    if value == "series":
        return "tv"
    if value in {"movie", "tv"}:
        return value
    raise ValueError(f"Unsupported media type '{value}'.")


def default_accent_for_label(label):
    seed = sum((index + 1) * ord(char) for index, char in enumerate(label or "Backdrop"))
    hue = (seed % 360) / 360.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.65, 0.88)
    return (int(red * 255), int(green * 255), int(blue * 255))


def parse_accent_color(value):
    if not value:
        return None
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
        if len(value) != 6:
            raise ValueError("Hex accent colors must use 6 digits, like #2299aa.")
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))

    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError("Accent colors must be '#RRGGBB' or 'R,G,B'.")
    rgb = tuple(int(part) for part in parts)
    if any(part < 0 or part > 255 for part in rgb):
        raise ValueError("Accent color channels must be between 0 and 255.")
    return rgb


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


def parse_request_spec(spec):
    try:
        raw_media_type, raw_request = spec.split(":", 1)
    except ValueError as exc:
        raise ValueError(f"Invalid request '{spec}'. Use 'movie:key=value...'") from exc

    media_type = normalize_media_type(raw_media_type.strip())
    raw_request = raw_request.strip()
    if not raw_request:
        raise ValueError(f"Invalid request '{spec}': missing path or query string.")

    if raw_request.startswith("/"):
        path, _, query_string = raw_request.partition("?")
        params = dict(parse_qsl(query_string, keep_blank_values=True))
        if path.startswith("/discover/"):
            return {"mode": "discover", "media_type": media_type, "params": params}
        return {"mode": "endpoint", "media_type": media_type, "path": path, "params": params}

    params = dict(parse_qsl(raw_request, keep_blank_values=True))
    return {"mode": "discover", "media_type": media_type, "params": params}


def fetch_titles_for_spec(spec, api_key, max_pages=3):
    items = []
    if spec["mode"] == "discover":
        endpoint = f"/discover/{spec['media_type']}"
        base_params = dict(spec["params"])
    else:
        endpoint = spec["path"]
        base_params = dict(spec.get("params", {}))

    for page in range(1, max_pages + 1):
        data = tmdb_get(endpoint, {**base_params, "page": page}, api_key)
        page_results = data.get("results", [])
        if not page_results:
            break
        for item in page_results:
            if item.get("backdrop_path"):
                items.append((spec["media_type"], item))
        total_pages = data.get("total_pages") or max_pages
        if page >= total_pages:
            break
    return items


def get_media_keywords(media_type, media_id, api_key):
    try:
        res = tmdb_get(f"/{media_type}/{media_id}/keywords", {}, api_key)
        kw = res.get("keywords") or res.get("results") or []
        return {k["id"] for k in kw if "id" in k}
    except:
        return set()


def fetch_titles(request_specs, api_key, label, count=60):
    per_spec_items = [fetch_titles_for_spec(spec, api_key) for spec in request_specs]
    merged = []
    max_len = max((len(spec_items) for spec_items in per_spec_items), default=0)
    for index in range(max_len):
        for spec_items in per_spec_items:
            if index < len(spec_items):
                merged.append(spec_items[index])

    seen = set()
    scored_unique = []
    current_year = datetime.now().year
    norm_label = label.lower().strip()

    for media_type, item in merged:
        key = (media_type, item["id"])
        if key in seen:
            continue
        seen.add(key)

        if item.get("adult") or item.get("popularity", 0) < 15:
            continue

        if "animation" in norm_label and "japonaise" not in norm_label:
            if item.get("original_language", "") not in WESTERN_LANGUAGES:
                continue

        media_keywords = get_media_keywords(media_type, item["id"], api_key)
        if media_keywords.intersection(BANNED_KEYWORDS):
            continue

        if ("famille" in norm_label or "family" in norm_label) and media_keywords.intersection(FAMILY_BANNED_KEYWORDS):
            continue

        pop_score = min(item.get("popularity", 0) / 2.5, 140)
        total_score = pop_score

        release_date_str = item.get("release_date") or item.get("first_air_date") or ""
        if release_date_str and len(release_date_str) >= 4 and release_date_str[:4].isdigit():
            if int(release_date_str[:4]) >= (current_year - 10):
                total_score += 150
            else:
                total_score -= 100
        else:
            total_score -= 50

        if "japonaise" not in norm_label and item.get("original_language", "") in WESTERN_LANGUAGES:
            total_score += 75

        scored_unique.append((total_score, (media_type, item)))

    scored_unique.sort(key=lambda x: x[0], reverse=True)
    return [data for score, data in scored_unique[:count]]


def get_tmdb_external_ids(kind, tmdb_id, api_key):
    try:
        return tmdb_get(f"/{kind}/{tmdb_id}/external_ids", {}, api_key)
    except Exception:
        return {}


def fanart_get_tv(tvdb_id, fanart_key):
    try:
        res = requests.get(f"{FANART_BASE}/tv/{tvdb_id}", params={"api_key": fanart_key}, timeout=15)
        res.raise_for_status()
        return res.json()
    except:
        return None


def fanart_get_movie(tmdb_id, fanart_key):
    try:
        res = requests.get(f"{FANART_BASE}/movies/{tmdb_id}", params={"api_key": fanart_key}, timeout=15)
        res.raise_for_status()
        return res.json()
    except:
        return None


def fanart_candidate_groups(fanart_data, kind):
    if not fanart_data:
        return []
    if kind == "tv":
        return [("thumb", fanart_data.get("tvthumb") or []), ("background", fanart_data.get("showbackground") or [])]
    return [("thumb", fanart_data.get("moviethumb") or []), ("background", fanart_data.get("moviebackground") or [])]


def normalize_fanart_lang(value):
    if value is None:
        return None
    value = str(value).strip().lower()
    if value in {"", "00", "none", "null"}:
        return None
    return value


def pick_fanart_url(fanart_data, kind, preferred_language, original_language):
    """
    Filtre Fanart.tv modifié : Ignore volontairement le textless.
    Priorise l'existence de logos textuels en FR, puis EN.
    """
    ranked_groups = {"fr": [], "en": [], "other": []}

    for group_rank, (_, candidates) in enumerate(fanart_candidate_groups(fanart_data, kind)):
        if not candidates:
            continue
        for candidate in candidates:
            lang = normalize_fanart_lang(candidate.get("lang"))
            entry = {"candidate": candidate, "group_rank": group_rank}
            
            if lang == "fr":
                ranked_groups["fr"].append(entry)
            elif lang == "en":
                ranked_groups["en"].append(entry)
            elif lang is not None: # Exclusion du textless (on veut du texte !)
                ranked_groups["other"].append(entry)

    for bucket in ("fr", "en", "other"):
        if ranked_groups[bucket]:
            best = sorted(ranked_groups[bucket], key=lambda entry: (entry["group_rank"], -int(entry["candidate"].get("likes", 0))))[0]["candidate"]
            if best.get("url"):
                return best["url"], bucket
    return None, None


def download_image_url(url, retries=2):
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content)).convert("RGBA")
        except Exception:
            if attempt == retries:
                return None
            time.sleep(1)


def download_tmdb_backdrop(path, retries=2):
    return download_image_url(f"{TMDB_IMG_BASE}/{BACKDROP_SIZE}{path}", retries=retries)


def select_best_tmdb_backdrop(kind, tmdb_id, api_key, fallback_path):
    """
    Algorithme révisé : Recherche de logos textuels (FR puis EN).
    Sensibilité à la résolution abaissée au profit de la pertinence du logo et des votes.
    """
    try:
        # On demande explicitement les langues à texte (fr,en)
        data = tmdb_get(f"/{kind}/{tmdb_id}/images", {"include_image_language": "fr,en"}, api_key)
        backdrops_list = data.get("backdrops", [])
        if not backdrops_list:
            return fallback_path

        scored_images = []
        for bg in backdrops_list:
            file_path = bg.get("file_path")
            if not file_path:
                continue
            width = bg.get("width", 0)
            height = bg.get("height", 0)
            votes = bg.get("vote_count", 0)
            vote_avg = bg.get("vote_average", 5.0)
            lang = bg.get("iso_639_1")

            # Le poids des votes communautaires compte beaucoup ici
            base_score = (votes * 5) + (vote_avg * 20)
            
            # Priorisation absolue de la langue du logo
            if lang == "fr":
                base_score += 600
            elif lang == "en":
                base_score += 300
            else:
                base_score -= 150

            # Respect du ratio 16:9 pour éviter les déformations du damier
            aspect_ratio = width / height if height > 0 else 0
            if abs(aspect_ratio - 1.777) > 0.04:
                base_score -= 200

            # Bonus de résolutions fortement diminués (la présence du logo prime)
            if width >= 1920 or height >= 1080:
                base_score += 100
            elif width >= 1280 or height >= 720:
                base_score += 50
            else:
                base_score -= 100

            scored_images.append((base_score, file_path))

        if scored_images:
            scored_images.sort(key=lambda x: x[0], reverse=True)
            return scored_images[0][1]
        return fallback_path
    except Exception:
        return fallback_path


def fetch_tile_image(kind, item, api_key, fanart_key, preferred_language):
    tmdb_id = item["id"]
    original_language = item.get("original_language")
    preferred_url = None
    last_resort_url = None

    if fanart_key:
        if kind == "tv":
            external_ids = get_tmdb_external_ids("tv", tmdb_id, api_key)
            tvdb_id = external_ids.get("tvdb_id")
            if tvdb_id:
                candidate_url, bucket = pick_fanart_url(fanart_get_tv(tvdb_id, fanart_key), "tv", preferred_language, original_language)
                if bucket == "other": last_resort_url = candidate_url
                else: preferred_url = candidate_url
        else:
            candidate_url, bucket = pick_fanart_url(fanart_get_movie(tmdb_id, fanart_key), "movie", preferred_language, original_language)
            if bucket == "other": last_resort_url = candidate_url
            else: preferred_url = candidate_url

    if preferred_url:
        image = download_image_url(preferred_url)
        if image:
            return image, "fanart"

    # Extraction du meilleur backdrop TMDB à texte via l'algorithme FR > EN
    best_backdrop_path = select_best_tmdb_backdrop(kind, tmdb_id, api_key, item["backdrop_path"])
    tmdb_image = download_tmdb_backdrop(best_backdrop_path)
    if tmdb_image:
        return tmdb_image, "tmdb"

    if last_resort_url:
        image = download_image_url(last_resort_url)
        if image: return image, "fanart_other_language"

    return None, "missing"


def rounded_rect_mask(width, height, radius=CARD_RADIUS):
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=255)
    return mask


def make_tile(image, tile_width, tile_height):
    source_width, source_height = image.size
    target_ratio = tile_width / tile_height
    current_ratio = source_width / source_height
    if current_ratio > target_ratio:
        new_width = int(source_height * target_ratio)
        left = (source_width - new_width) // 2
        image = image.crop((left, 0, left + new_width, source_height))
    else:
        new_height = int(source_width / target_ratio)
        top = (source_height - new_height) // 2
        image = image.crop((0, top, source_width, top + new_height))
    image = image.resize((tile_width, tile_height), Image.LANCZOS)
    scaled_radius = max(8, int(CARD_RADIUS * tile_width / TILE_W))
    mask = rounded_rect_mask(tile_width, tile_height, radius=scaled_radius)
    result = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    result.paste(image, mask=mask)
    return result


def build_tilted_grid(tiles, canvas_width, canvas_height, scale=1.0, focus_x=None, focus_y=None):
    fx = FOCUS_X if focus_x is None else focus_x
    fy = FOCUS_Y if focus_y is None else focus_y

    tile_width = int(TILE_W * scale)
    tile_height = int(TILE_H * scale)
    gap = int(GAP * scale)

    cols = COLS + 3
    rows = ROWS + 3
    needed = rows * cols
    tile_list = (tiles * (needed // len(tiles) + 1))[:needed]
    stagger_px = int(STAGGER * (tile_width + gap))

    grid_width = cols * (tile_width + gap) + rows * stagger_px
    grid_height = rows * (tile_height + gap)
    grid = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))

    focal_x = fx * grid_width
    focal_y = fy * grid_height
    focal_row = max(0, min(rows - 1, int(focal_y / (tile_height + gap))))
    focal_col = max(0, min(cols - 1, int((focal_x - focal_row * stagger_px) / (tile_width + gap))))

    cells = [(row, col) for row in range(rows) for col in range(cols)]
    cells.sort(key=lambda pos: abs(pos[0] - focal_row) + abs(pos[1] - focal_col))

    for index, (row, col) in enumerate(cells):
        if index >= len(tile_list): break
        x = row * stagger_px + col * (tile_width + gap)
        y = row * (tile_height + gap)
        tile = make_tile(tile_list[index], tile_width, tile_height)
        grid.paste(tile, (x, y), tile)

    rotated = grid.rotate(TILT_DEG, expand=True, resample=Image.BICUBIC)
    rotated_width, rotated_height = rotated.size

    angle_rad = math.radians(-TILT_DEG)
    pre_center_x = fx * grid_width - grid_width / 2
    pre_center_y = fy * grid_height - grid_height / 2
    rot_center_x = pre_center_x * math.cos(angle_rad) - pre_center_y * math.sin(angle_rad)
    rot_center_y = pre_center_x * math.sin(angle_rad) + pre_center_y * math.cos(angle_rad)

    focus_in_rot_x = rotated_width / 2 + rot_center_x
    focus_in_rot_y = rotated_height / 2 + rot_center_y

    paste_x = int(canvas_width / 2 - focus_in_rot_x)
    paste_y = int(canvas_height / 2 - focus_in_rot_y)

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (10, 10, 12, 255))
    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas


def ensure_minimum_tiles(tile_images, minimum_count):
    if len(tile_images) >= minimum_count or not tile_images:
        return tile_images
    padded_tiles = list(tile_images)
    for tile in itertools.cycle(tile_images):
        if len(padded_tiles) >= minimum_count: break
        padded_tiles.append(tile.copy())
    return padded_tiles


def apply_gradient(canvas, accent):
    width, height = canvas.size

    def make_linear_gradient(grad_width, grad_height, direction):
        image = Image.new("RGBA", (grad_width, grad_height), (0, 0, 0, 0))
        pixels = image.load()

        if direction == "left":
            for x in range(grad_width):
                mix = max(0.0, 1.0 - x / (grad_width * 0.45))
                alpha = int(200 * mix ** 1.6)
                if alpha:
                    color = (6, 6, 8, alpha)
                    for y in range(grad_height): pixels[x, y] = color

        elif direction == "bottom":
            for y in range(grad_height):
                mix = max(0.0, (y - grad_height * 0.50) / (grad_height * 0.50))
                alpha = int(200 * mix ** 1.4)
                if alpha:
                    color = (6, 6, 8, alpha)
                    for x in range(grad_width): pixels[x, y] = color

        elif direction == "corner_bl":
            max_diag = math.hypot(grad_width, grad_height)
            for x in range(grad_width):
                for y in range(grad_height):
                    distance = math.hypot(x, grad_height - y)
                    mix = distance / max_diag
                    base = max(0.0, 1.0 - mix / 0.60)
                    alpha = int(230 * base ** 2.2)
                    if alpha: pixels[x, y] = (6, 6, 8, min(255, alpha))

        elif direction == "corner_tr_color":
            max_diag = math.hypot(grad_width, grad_height)
            red, green, blue = accent
            for x in range(grad_width):
                for y in range(grad_height):
                    distance = math.hypot(grad_width - x, y)
                    mix = distance / max_diag
                    base = max(0.0, 1.0 - mix / 0.72)
                    alpha = int(118 * base ** 1.9)
                    if alpha: pixels[x, y] = (red, green, blue, min(255, alpha))

        return image

    left_grad = make_linear_gradient(width, height, "left")
    bottom_grad = make_linear_gradient(width, height, "bottom")
    small_corner = make_linear_gradient(width // 4, height // 4, "corner_bl")
    corner_grad = small_corner.resize((width, height), Image.BILINEAR)
    accent_small = make_linear_gradient(width // 4, height // 4, "corner_tr_color")
    accent_grad = accent_small.resize((width, height), Image.BILINEAR)

    result = Image.alpha_composite(canvas, corner_grad)
    result = Image.alpha_composite(result, left_grad)
    result = Image.alpha_composite(result, bottom_grad)
    accent_grad = accent_grad.filter(ImageFilter.GaussianBlur(radius=max(28, width // 64)))
    return Image.alpha_composite(result, accent_grad)


def resolve_quality_settings(profile="compressed", quality=None):
    settings = dict(QUALITY_PRESETS[profile])
    if quality is not None: settings["quality"] = quality
    return settings


def save_output(canvas, path, quality_settings):
    final = canvas.convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    final.save(path, "JPEG", quality=quality_settings["quality"], optimize=True, progressive=quality_settings["progressive"], subsampling=quality_settings["subsampling"])
    
    webp_path = path.with_suffix(".webp")
    with Image.open(path) as jpg_image:
        jpg_image.save(webp_path, "WEBP", quality=quality_settings["quality"], method=6)


def resolve_outputs(output=None, output_dir=None, label=None, size="both"):
    if output:
        base = Path(output)
        if size == "both":
            return {
                "4k": base.with_name(f"{base.stem}_4k{base.suffix or '.jpg'}"),
                "1080p": base.with_name(f"{base.stem}_1080p{base.suffix or '.jpg'}"),
            }
        return {size: base}

    directory = Path(output_dir or DEFAULT_OUTPUT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    stem = (label or "backdrop").strip().lower().replace(" ", "_").replace("/", "_")
    if size == "both":
        return {"4k": directory / f"{stem}_wallpaper_4k.jpg", "1080p": directory / f"{stem}_wallpaper_1080p.jpg"}
    suffix = "4k" if size == "4k" else "1080p"
    return {size: directory / f"{stem}_wallpaper_{suffix}.jpg"}


def backdrops(api_key, label, tmdb_requests, fanart_key=None, accent_color=None, output=None, output_dir=None, focus_x=None, focus_y=None, count=60, size="both", profile="compressed", quality=None, preferred_language="fr", logger=None):
    log = logger or print
    request_specs = [parse_request_spec(spec) for spec in tmdb_requests]
    if not request_specs: raise ValueError("No TMDB request specs were supplied.")

    fx = FOCUS_X if focus_x is None else focus_x
    fy = FOCUS_Y if focus_y is None else focus_y
    accent = accent_color or default_accent_for_label(label)
    outputs = resolve_outputs(output=output, output_dir=output_dir, label=label, size=size)
    quality_settings = resolve_quality_settings(profile=profile, quality=quality)

    log(f"\n--- Analyse de Mosaïque à Logos : {label} ---")
    titles = fetch_titles(request_specs, api_key, label=label, count=count)
    if not titles: raise RuntimeError("No titles found.")

    tile_images = []
    for index, (media_type, item) in enumerate(titles, start=1):
        image, source = fetch_tile_image(media_type, item, api_key, fanart_key, preferred_language)
        if image:
            tile_images.append(image)

    minimum_tiles = 12
    if len(tile_images) < minimum_tiles:
        tile_images = ensure_minimum_tiles(tile_images, minimum_tiles)

    saved_paths = {}
    for output_size, destination in outputs.items():
        width, height, scale = SIZE_PRESETS[output_size]
        canvas = build_tilted_grid(tile_images, width, height, scale=scale, focus_x=fx, focus_y=fy)
        canvas = apply_gradient(canvas, accent)
        save_output(canvas, destination, quality_settings=quality_settings)
        saved_paths[output_size] = destination

    return saved_paths


def parse_focus_value(value):
    if not value: return FOCUS_X, FOCUS_Y
    if value in FOCUS_PRESETS: return FOCUS_PRESETS[value]
    try:
        raw_x, raw_y = value.split(",", 1)
        return float(raw_x), float(raw_y)
    except:
        raise ValueError("Invalid focus format.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--fanart-key", default=None)
    parser.add_argument("--preferred-language", default="fr")
    parser.add_argument("--label", required=True)
    parser.add_argument("--tmdb-request", action="append", default=[])
    parser.add_argument("--accent-color", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output", default=None)
    parser.add_argument("--size", choices=("4k", "1080p", "both"), default="both")
    parser.add_argument("--profile", choices=tuple(QUALITY_PRESETS), default="compressed")
    parser.add_argument("--quality", type=int, default=None)
    parser.add_argument("--focus", default=None)
    parser.add_argument("--count", type=int, default=60)
    args = parser.parse_args()

    try:
        accent = parse_accent_color(args.accent_color) if args.accent_color else None
        focus_x, focus_y = parse_focus_value(args.focus)
        backdrops(api_key=args.api_key, label=args.label, tmdb_requests=args.tmdb_request, fanart_key=args.fanart_key, accent_color=accent, output=args.output, output_dir=args.output_dir, focus_x=focus_x, focus_y=focus_y, count=args.count, size=args.size, profile=args.profile, quality=args.quality, preferred_language=args.preferred_language)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    try: main()
    finally: cleanup_pycache()

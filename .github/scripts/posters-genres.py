import os
import sys
import time
import json
import requests
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter

# ==============================================================================
# CONFIGURATION GLOBALE & COUPE-CIRCUIT DE SÉCURITÉ
# ==============================================================================
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

if not TMDB_API_KEY:
    print("Erreur : La variable TMDB_API_KEY n'est pas définie.")
    sys.exit(1)

OUTPUT_DIR = "Ressources/Collections Covers/Genres/Static Covers"
HISTORY_FILE = ".github/scripts/posters_history.json"

# IDs TMDB de mots-clés adultes / érotiques / softcore à bannir définitivement 
BANNED_KEYWORDS = {155716, 190340, 156201, 291195, 180549, 210113} 

# IDs TMDB des genres TV de flux (News, Reality, Talk, Soap) à exclure pour éviter les émissions de plateau
BANNED_TV_GENRES = {10763, 10764, 10767, 10766}

# Langues globales autorisées (Inclusion du Japon / Corée / Chine selon tes directives) 
ALLOWED_LANGUAGES = {"fr", "en", "es", "de", "it", "ja", "ko", "zh"}

RUN_PROCESSED_IDS = set()

# ==============================================================================
# CARTOGRAPHIE DE TA MINE D'OR DE TAGS [cite: 9, 11]
# ==============================================================================
GENRES_CONFIG = {
    "action": {
        "label": "Action", "color": (210, 40, 45), "movie_genre": 28, "tv_genre": 10759, 
        "type": "live-action", "scoring_keywords": [779, 9715, 1721, 1419, 3713, 322496, 14643, 12371, 14955, 192913]
    },
    "animation": {
        "label": "Animation", "color": (0, 150, 210), "movie_genre": 16, "tv_genre": 16, 
        "type": "animation-occidentale", "scoring_keywords": [10121, 297442, 6513, 278823, 161919, 197065, 10159, 234662]
    },
    "animation-japonaise": {
        "label": "Animation Japonaise", "color": (140, 45, 210), "movie_genre": 16, "tv_genre": 16, 
        "type": "animation-asiatique", "scoring_keywords": [210024, 13141, 222243]
    },
    "aventure": {
        "label": "Aventure", "color": (20, 130, 70), "movie_genre": 12, "tv_genre": 10759, 
        "type": "live-action", "scoring_keywords": [10349, 2041, 189092, 3593, 322942, 1454, 6956, 1963, 175428]
    },
    "comedie": {
        "label": "Comédie", "color": (220, 110, 10), "movie_genre": 35, "tv_genre": 35, 
        "type": "live-action", "scoring_keywords": [322268, 9716, 8201, 9755, 9253, 320420, 169086, 167541, 11514, 328540]
    },
    "crime": {
        "label": "Crime", "color": (70, 85, 105), "movie_genre": 80, "tv_genre": 80, 
        "type": "live-action", "scoring_keywords": [9826, 6149, 1930, 703, 3149, 642, 10391, 323114, 33722, 10051, 1812, 207046, 10291, 15090, 155790, 8015, 161982, 158927, 15167]
    },
    "documentaire": {
        "label": "Documentaire", "color": (20, 140, 60), "movie_genre": 99, "tv_genre": 99, 
        "type": "live-action", "scoring_keywords": [9672, 282080, 221355, 5565, 18330, 18165, 272851, 270, 9902, 305903, 5968, 252105, 211505, 284176, 160330, 9882]
    },
    "drame": {
        "label": "Drame", "color": (30, 90, 170), "movie_genre": 18, "tv_genre": 18, 
        "type": "live-action", "scoring_keywords": [34079, 316421, 14964, 9672, 378, 9872, 1326, 9957, 894, 931, 12279, 311315, 697, 41329, 417, 10085, 15160, 12987, 10163, 10614, 2754, 4232]
    },
    "famille": {
        "label": "Famille", "color": (170, 25, 150), "movie_genre": 10751, "tv_genre": 10751, 
        "type": "flexible", "scoring_keywords": [10683, 18035, 6054, 970, 2343, 10235, 15101, 11093, 159947, 197349, 18187]
    },
    "fantastique": {
        "label": "Fantastique", "color": (110, 30, 190), "movie_genre": 14, "tv_genre": 10765, 
        "type": "live-action", "scoring_keywords": [2343, 3205, 12554, 2035, 179411, 177912, 236458, 2710, 234213, 4152, 5457, 227686, 5147]
    },
    "guerre": {
        "label": "Guerre", "color": (90, 80, 70), "movie_genre": 10752, "tv_genre": 10768, 
        "type": "live-action", "scoring_keywords": [1956, 2504, 13065, 6092, 2957, 836, 4595]
    },
    "histoire": {
        "label": "Histoire", "color": (140, 70, 30), "movie_genre": 36, "tv_genre": 10768, 
        "type": "live-action", "scoring_keywords": [207928, 282633, 192772, 15126, 6165, 160279, 207941, 161257, 41406, 12995, 285398, 9920, 5049, 208244, 280999, 157894, 10506, 1405, 159289]
    },
    "horreur": {
        "label": "Horreur", "color": (180, 20, 20), "movie_genre": 27, "tv_genre": 27, 
        "type": "live-action", "scoring_keywords": [162846, 10714, 3133, 12339, 12377, 1299, 15001, 3358, 10541, 9712, 13073, 14999, 284439, 161261, 230191]
    },
    "romance": {
        "label": "Romance", "color": (180, 35, 90), "movie_genre": 10749, "tv_genre": 10749, 
        "type": "live-action", "scoring_keywords": [9673, 9840, 6038, 128, 13027, 324429, 14720, 157303]
    },
    "science-fiction": {
        "label": "Science-Fiction", "color": (15, 60, 160), "movie_genre": 878, "tv_genre": 10765, 
        "type": "live-action", "scoring_keywords": [4379, 4565, 310, 281358, 2964, 14544, 1576, 12190, 161176, 803, 252937]
    },
    "sport": {
        "label": "Sport", "color": (235, 170, 0), "movie_genre": None, "tv_genre": None, 
        "type": "live-action", "is_pseudo_genre": True, "scoring_keywords": [6075, 13042, 209476, 6496, 333328, 10039]
    },
    "thriller": {
        "label": "Thriller", "color": (15, 100, 85), "movie_genre": 53, "tv_genre": 80, 
        "type": "live-action", "scoring_keywords": [12565, 1930, 5340, 316362, 288394, 316332, 10410, 314730, 321464, 272553, 207046, 316832]
    },
    "western": {
        "label": "Western", "color": (160, 60, 15), "movie_genre": 37, "tv_genre": 37, 
        "type": "live-action", "scoring_keywords": [2673, 18034, 1556, 156212, 2752, 798, 155291, 9503, 305941, 801, 1582]
    }
}

# ==============================================================================
# UTILS & CORE SYSTEM
# ==============================================================================
def tmdb_api_call(endpoint, params=None):
    if params is None: params = {}
    params["api_key"] = TMDB_API_KEY
    for attempt in range(3):
        try:
            res = requests.get(f"{TMDB_BASE}{endpoint}", params=params, timeout=15)
            res.raise_for_status()
            return res.json()
        except Exception:
            if attempt == 2: raise
            time.sleep(1.5 + attempt)

def load_and_clean_history():
    if not os.path.exists(HISTORY_FILE): return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception: return {}
    cleaned_history = {}
    limit_date = datetime.now() - timedelta(days=14)
    for k, data in history.items():
        try:
            if datetime.strptime(data["date"], "%Y-%m-%d") > limit_date:
                cleaned_history[k] = data
        except Exception: continue
    return cleaned_history

def get_media_keywords(media_type, media_id):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/keywords")
        kw = res.get("keywords") or res.get("results") or []
        return {k["id"] for k in kw if "id" in k}
    except: return set()

# ==============================================================================
# ALGORITHME DE RECHERCHE ET DE FILTRAGE QUALITATIF
# ==============================================================================
def get_trending_media_for_genre(config, excluded_keys):
    movie_pool, tv_pool = [], []
    
    # Paramètres de base blindés géographiquement 
    base_params = "&include_adult=false&with_original_language=fr|en|es|de|it|ja|ko|zh"
    
    # Règle d'isolation Live-Action vs Animations [cite: 3, 4, 5]
    if config["type"] == "live-action":
        base_params += "&without_genres=16"
    elif config["type"] == "animation-occidentale":
        base_params += "&with_genres=16&without_original_language=ja|ko|zh"
    elif config["type"] == "animation-asiatique":
        base_params += "&with_genres=16&with_original_language=ja|ko|zh"

    # Traitement du pseudo-genre Sport (uniquement par mots-clés) 
    if config.get("is_pseudo_genre"):
        kw_string = "|".join(str(k) for k in config["scoring_keywords"])
        base_params += f"&with_keywords={kw_string}"
    else:
        if config["movie_genre"]: base_params += f"&with_genres={config['movie_genre']}"
        if config["tv_genre"]: base_params += f"&with_genres={config['tv_genre']}"

    # Collecte sur les 3 premières pages de TMDB pour extraire la crème de la crème 
    for page in range(1, 4):
        try:
            if config["movie_genre"] or config.get("is_pseudo_genre"):
                res = tmdb_api_call(f"/discover/movie?sort_by=popularity.desc{base_params}&page={page}")
                for item in res.get("results", []):
                    if item.get("backdrop_path"): 
                        item["media_type"] = "movie"
                        movie_pool.append(item)
        except: break
        
    for page in range(1, 4):
        try:
            if config["tv_genre"] or config.get("is_pseudo_genre"):
                res = tmdb_api_call(f"/discover/tv?sort_by=popularity.desc{base_params}&page={page}")
                for item in res.get("results", []):
                    if item.get("backdrop_path"): 
                        item["media_type"] = "tv"
                        tv_pool.append(item)
        except: break

    combined = movie_pool + tv_pool
    filtered = []
    
    for item in combined:
        composite_key = f"{item['media_type']}_{item['id']}"
        orig_lang = item.get("original_language", "")
        
        # Sécurité anti-doublons
        if composite_key in excluded_keys or composite_key in RUN_PROCESSED_IDS: 
            continue
            
        # SÉCURITÉ ANTI-FLUX : Bannir les émissions de flux/plateaux TV (Reality, News, Talk, Soap)
        if item["media_type"] == "tv":
            genre_ids = set(item.get("genre_ids", []))
            if genre_ids.intersection(BANNED_TV_GENRES):
                continue
        
        # FILTRE DE VÉRIFICATION DE TRADUCTION FRANÇAISE (Pour les œuvres asiatiques hors animation) 
        if orig_lang in {"ja", "ko", "zh"} and config["type"] == "live-action":
            try:
                trans = tmdb_api_call(f"/{item['media_type']}/{item['id']}/translations")
                has_fr = any(t.get("iso_639_1") == "fr" for t in trans.get("translations", []))
                if not has_fr: continue
            except: continue
            
        filtered.append(item)
        
    return filtered

# ==============================================================================
# LOGIQUE GRAPHISME ET ARTWORK
# ==============================================================================
def get_best_textless_backdrops(media_type, media_id, fallback_path):
    try:
        res = tmdb_api_call(f"/{media_type}/{media_id}/images", {"include_image_language": "null"})
        bd = res.get("backdrops", [])
        if not bd: return [{"file_path": fallback_path, "width": 1920, "vote_count": 5}]
        
        safe_bd = [b for b in bd if b.get("vote_average", 5) >= 3.0]
        if not safe_bd: safe_bd = bd
        return safe_bd[:15]
    except: return [{"file_path": fallback_path, "width": 1920, "vote_count": 5}]

def score_and_select_backdrop(backdrops):
    scored_images = []
    for bg in backdrops:
        width = bg.get("width", 0)
        height = bg.get("height", 0)
        votes = bg.get("vote_count", 0)
        
        base_score = votes * 2
        if width >= 3840 or height >= 2160: base_score += 500  
        elif width >= 2560 or height >= 1440: base_score += 250  
        elif width >= 1920 or height >= 1080: base_score += 50   
        else: base_score -= 100  
            
        scored_images.append((base_score, bg))
        
    scored_images.sort(key=lambda x: x[0], reverse=True)
    return scored_images[0][1] if scored_images else backdrops[0]

def apply_premium_duotone(img, base_color):
    img_gray = img.convert("L")
    stat = img_gray.histogram()
    pixels_lumineux = sum(stat[200:]) / sum(stat)
    
    if pixels_lumineux > 0.25:
        img = ImageEnhance.Brightness(img).enhance(0.85)
        img = ImageEnhance.Contrast(img).enhance(1.18)
    else:
        img = ImageEnhance.Contrast(img).enhance(1.05)
        
    color_layer = Image.new("RGB", img.size, base_color)
    img_ycbcr = img.convert("YCbCr")
    color_ycbcr = color_layer.convert("YCbCr")
    
    y_img, _, _ = img_ycbcr.split()
    _, cb_color, cr_color = color_ycbcr.split()
    
    y_img = ImageEnhance.Brightness(y_img).enhance(0.95)
    final_ycbcr = Image.merge("YCbCr", (y_img, cb_color, cr_color))
    final_rgb = final_ycbcr.convert("RGB")
    
    final_rgb = ImageEnhance.Color(final_rgb).enhance(1.15)
    return final_rgb.filter(ImageFilter.SHARPEN)

def finalize_landscape_banner(img, label, color):
    img = ImageOps.fit(img, (1920, 1080), method=Image.Resampling.LANCZOS)
    img = apply_premium_duotone(img, color)
    img_rgba = img.convert("RGBA")
    
    gradient = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(450, 1080):
        alpha = int(((y - 450) / 630) ** 1.8 * 255)
        g_draw.line([(0, y), (1920, y)], fill=(0, 0, 0, alpha))
        
    img_with_gradient = Image.alpha_composite(img_rgba, gradient)

    text_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(text_layer)
    s_draw = ImageDraw.Draw(shadow_layer)
    
    font_size = 165
    try: font = ImageFont.truetype(".github/assets/fonts/SF-Pro-Display-Bold.otf", font_size)
    except: font = ImageFont.load_default()

    padding_left, padding_bottom = 130, 140
    max_text_width = 1920 - (padding_left * 2)

    words = label.split(" ")
    lines, current_line = [], ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        if t_draw.textlength(test_line, font=font) <= max_text_width: current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)

    line_spacing, line_height = 20, font_size - 22
    total_text_height = (len(lines) * line_height) + ((len(lines) - 1) * line_spacing)
    base_y = (1080 - padding_bottom - line_height) - (total_text_height - line_height)

    current_y = base_y
    for line in lines:
        s_draw.text((padding_left + 6, current_y + 10), line, fill=(0, 0, 0, 245), font=font)
        t_draw.text((padding_left, current_y), line, fill=(255, 255, 255, 255), font=font)
        current_y += line_height + line_spacing

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(12))
    final_img = Image.alpha_composite(img_with_gradient, shadow_layer)
    final_img = Image.alpha_composite(final_img, text_layer)
    
    return final_img.convert("RGB")

# ==============================================================================
# ORCHESTRATEUR DE SCORING ET EXÉCUTION
# ==============================================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    history = load_and_clean_history()
    excluded_keys = set(history.keys())

    for genre_name, config in GENRES_CONFIG.items():
        print(f"\n--- Analyse Algorithmique : {config['label']} ---")
        candidates = get_trending_media_for_genre(config, excluded_keys)
        if not candidates:
            print(" -> Aucun candidat éligible trouvé après filtrage géographique.")
            continue
        
        scoring_keywords = set(config.get("scoring_keywords", []))
        scored_candidates = []
        
        for item in candidates:
            media_keywords = get_media_keywords(item["media_type"], item["id"])
            
            # FILTRE ABSOLU SÉCURITÉ : Exclusion immédiate si tag Adulte/NSFW 
            if media_keywords.intersection(BANNED_KEYWORDS):
                print(f" -> [SÉCURITÉ] {item.get('title') or item.get('name')} banni immédiatement pour mots-clés inadéquats.")
                continue
                
            # FORMULE DE SCORING MULTI-CRITÈRES 
            # Forte valeur ajoutée aux tags de ton fichier (+30 pts par tag) combiné à la popularité globale
            keyword_bonus = len(media_keywords.intersection(scoring_keywords)) * 30
            popularity_bonus = min(item.get("popularity", 0) / 4, 150)
            
            total_score = keyword_bonus + popularity_bonus
            scored_candidates.append({"item": item, "score": total_score})
            
        # Tri mathématique des candidats du meilleur au moins bon 
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        
        success_genre = False
        for candidate in scored_candidates:
            media = candidate["item"]
            backdrops = get_best_textless_backdrops(media["media_type"], media["id"], media["backdrop_path"])
            best_bg = score_and_select_backdrop(backdrops)
            
            try:
                res = requests.get(f"https://image.tmdb.org/t/p/original{best_bg['file_path']}", stream=True, timeout=10)
                if res.status_code == 200:
                    raw_img = Image.open(res.raw).convert("RGB")
                    media_title = media.get('title') or media.get('name')
                    print(f" -> Sélectionné ({best_bg.get('width')}x{best_bg.get('height')} - Score: {candidate['score']:.1f}) : {media_title}")
                    
                    final_banner = finalize_landscape_banner(raw_img, config["label"], config["color"])
                    
                    # Sauvegardes optimales
                    final_banner.save(f"{OUTPUT_DIR}/{genre_name}.jpg", "JPEG", quality=94)
                    final_banner.save(f"{OUTPUT_DIR}/{genre_name}.webp", "WEBP", quality=94)
                    
                    composite_key = f"{media['media_type']}_{media['id']}"
                    RUN_PROCESSED_IDS.add(composite_key)
                    history[composite_key] = {
                        "title": media_title, 
                        "genre": genre_name, 
                        "date": datetime.now().strftime("%Y-%m-%d")
                    }
                    success_genre = True
                    break
            except Exception as e:
                print(f" Échec d'application de la charte graphique : {e}")
                continue
                
        if not success_genre:
            print(f" [ALERTE] Échec critique : Aucun visuel généré pour : {config['label']}")

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(history.items(), key=lambda x: x[1]['date'], reverse=True)), f, ensure_ascii=False, indent=4)
    print("\n[SUCCESS] Génération journalière terminée, stabilisée et purifiée des émissions TV.")

if __name__ == "__main__":
    main()

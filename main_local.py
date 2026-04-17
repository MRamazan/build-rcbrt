import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from flask import Flask, render_template, request, jsonify, session, Response
import uuid
import pickle
from utils import *
from options import args
from models import model_factory
from datetime import datetime
import re
import xml.etree.ElementTree as ET

app = Flask(__name__)
app.secret_key = '1903bjk'

_sessions = {}

import json

_APPDATA = os.environ.get('APPDATA', os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_APPDATA, 'Recbert AI')
os.makedirs(_DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(_DATA_DIR, 'user_favorites.json')

def load_sessions():
    global _sessions
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _sessions = {k: [int(x) for x in v] for k, v in data.items()}
            print(f"Favoriler yüklendi: {sum(len(v) for v in _sessions.values())} anime")
        except Exception as e:
            print(f"Favori yükleme hatası: {e}")
            _sessions = {}

def save_sessions():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(_sessions, f)
    except Exception as e:
        print(f"Favori kaydetme hatası: {e}")
        
def get_session_id():
    sid = request.headers.get('X-Session-ID')
    if not sid:
        sid = str(uuid.uuid4())
    return sid

def get_user_favorites():
    sid = get_session_id()
    if sid not in _sessions:
        _sessions[sid] = []
    return sid, _sessions[sid]

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Session-ID'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    return '', 204


@app.route('/sitemap.xml')
def sitemap():
    try:
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        urlset.set('xmlns:image', 'http://www.google.com/schemas/sitemap-image/1.1')

        base_url = request.url_root.rstrip('/')
        current_date = datetime.now().strftime('%Y-%m-%d')

        url = ET.SubElement(urlset, 'url')
        ET.SubElement(url, 'loc').text = f'{base_url}/'
        ET.SubElement(url, 'lastmod').text = current_date
        ET.SubElement(url, 'changefreq').text = 'daily'
        ET.SubElement(url, 'priority').text = '1.0'

        if recommendation_system and recommendation_system.id_to_anime:
            anime_count = 0
            for anime_id, anime_data in recommendation_system.id_to_anime.items():
                if anime_count >= 100:
                    break

                try:
                    anime_name = anime_data[0] if isinstance(anime_data, list) and len(anime_data) > 0 else str(anime_data)
                    safe_name = anime_name.replace(' ', '-').replace('/', '-').replace('?', '').replace('&', 'and')
                    safe_name = re.sub(r'[^\w\-]', '', safe_name)

                    url = ET.SubElement(urlset, 'url')
                    ET.SubElement(url, 'loc').text = f'{base_url}/anime/{anime_id}/{safe_name}'
                    ET.SubElement(url, 'lastmod').text = current_date
                    ET.SubElement(url, 'changefreq').text = 'weekly'
                    ET.SubElement(url, 'priority').text = '0.6'

                    image_url = recommendation_system.get_anime_image_url(int(anime_id))
                    if image_url:
                        image_elem = ET.SubElement(url, 'image:image')
                        ET.SubElement(image_elem, 'image:loc').text = image_url
                        ET.SubElement(image_elem, 'image:title').text = anime_name
                        ET.SubElement(image_elem, 'image:caption').text = f'Poster image for {anime_name}'

                    anime_count += 1
                except Exception as e:
                    print(f"Error processing anime {anime_id}: {e}")
                    continue

        xml_str = ET.tostring(urlset, encoding='unicode')
        full_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

        return Response(full_xml, mimetype='application/xml')

    except Exception as e:
        print(f"Sitemap generation error: {e}")
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
            mimetype='application/xml')


@app.route('/robots.txt')
def robots_txt():
    robots_content = f"""User-agent: *
Allow: /

Sitemap: {request.url_root.rstrip('/')}/sitemap.xml
"""
    return Response(robots_content, mimetype='text/plain')


@app.route('/anime/<int:anime_id>/<path:anime_name>')
def anime_detail(anime_id, anime_name):
    if not recommendation_system or str(anime_id) not in recommendation_system.id_to_anime:
        return render_template('error.html', error="Anime not found"), 404

    anime_data = recommendation_system.id_to_anime[str(anime_id)]
    anime_name = anime_data[0] if isinstance(anime_data, list) and len(anime_data) > 0 else str(anime_data)

    image_url = recommendation_system.get_anime_image_url(anime_id)
    mal_url = recommendation_system.get_anime_mal_url(anime_id)
    genres = recommendation_system.get_anime_genres(anime_id)
    type = recommendation_system._get_type(anime_id)

    similar_animes = []
    try:
        recommendations, _, _ = recommendation_system.get_recommendations([anime_id], num_recommendations=7)
        similar_animes = recommendations
    except:
        pass

    anime_info = {
        'id': anime_id,
        'name': anime_name,
        'image_url': image_url,
        'mal_url': mal_url,
        'genres': genres,
        'similar_animes': similar_animes,
        'type': type
    }

    structured_data = generate_anime_structured_data(anime_info)

    return render_template('anime_detail.html', anime=anime_info, structured_data=json.dumps(structured_data))


def generate_anime_structured_data(anime_info):
    structured_data = {
        "@context": "https://schema.org",
        "@type": anime_info["type"],
        "name": anime_info['name'],
        "url": f"{request.url_root.rstrip('/')}/anime/{anime_info['id']}/{anime_info['name'].replace(' ', '-')}"
    }

    if anime_info['genres']:
        structured_data["genre"] = anime_info['genres']

    if anime_info['image_url']:
        structured_data["image"] = anime_info['image_url']

    if anime_info['mal_url']:
        structured_data["sameAs"] = anime_info['mal_url']

    return structured_data


@app.route('/sitemap-index.xml')
def sitemap_index():
    try:
        sitemapindex = ET.Element('sitemapindex')
        sitemapindex.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')

        base_url = request.url_root.rstrip('/')
        current_date = datetime.now().strftime('%Y-%m-%d')

        sitemap = ET.SubElement(sitemapindex, 'sitemap')
        ET.SubElement(sitemap, 'loc').text = f'{base_url}/sitemap.xml'
        ET.SubElement(sitemap, 'lastmod').text = current_date

        if recommendation_system and len(recommendation_system.id_to_anime) > 100:
            sitemap = ET.SubElement(sitemapindex, 'sitemap')
            ET.SubElement(sitemap, 'loc').text = f'{base_url}/sitemap-animes.xml'
            ET.SubElement(sitemap, 'lastmod').text = current_date

        xml_str = ET.tostring(sitemapindex, encoding='unicode')
        full_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

        return Response(full_xml, mimetype='application/xml')

    except Exception as e:
        print(f"Sitemap index generation error: {e}")
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></sitemapindex>',
            mimetype='application/xml')


@app.route('/sitemap-animes.xml')
def sitemap_animes():
    try:
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        urlset.set('xmlns:image', 'http://www.google.com/schemas/sitemap-image/1.1')

        base_url = request.url_root.rstrip('/')
        current_date = datetime.now().strftime('%Y-%m-%d')

        if recommendation_system and recommendation_system.id_to_anime:
            for anime_id, anime_data in recommendation_system.id_to_anime.items():
                try:
                    anime_name = anime_data[0] if isinstance(anime_data, list) and len(anime_data) > 0 else str(anime_data)
                    safe_name = anime_name.replace(' ', '-').replace('/', '-').replace('?', '').replace('&', 'and')
                    safe_name = re.sub(r'[^\w\-]', '', safe_name)

                    url = ET.SubElement(urlset, 'url')
                    ET.SubElement(url, 'loc').text = f'{base_url}/anime/{anime_id}/{safe_name}'
                    ET.SubElement(url, 'lastmod').text = current_date
                    ET.SubElement(url, 'changefreq').text = 'weekly'
                    ET.SubElement(url, 'priority').text = '0.6'

                    image_url = recommendation_system.get_anime_image_url(int(anime_id))
                    if image_url:
                        image_elem = ET.SubElement(url, 'image:image')
                        ET.SubElement(image_elem, 'image:loc').text = image_url
                        ET.SubElement(image_elem, 'image:title').text = anime_name
                        ET.SubElement(image_elem, 'image:caption').text = f'Poster image for {anime_name}'

                except Exception as e:
                    print(f"Error processing anime {anime_id}: {e}")
                    continue

        xml_str = ET.tostring(urlset, encoding='unicode')
        full_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

        return Response(full_xml, mimetype='application/xml')

    except Exception as e:
        print(f"Anime sitemap generation error: {e}")
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
            mimetype='application/xml')


def get_meta_tags(page_type, anime_info=None):
    meta_tags = {
        'home': {
            'title': 'Anime Recommendation System - Discover Your Next Favorite Anime with BERT Transformer',
            'description': 'Get personalized anime recommendations based on your favorite shows. Discover new anime series and movies with our AI-powered recommendation system.',
            'keywords': 'anime, recommendation, anime list, manga, otaku, anime series, anime movies, ai, ai anime recommendation'
        }
    }

    if page_type == 'anime' and anime_info:
        return {
            'title': f"{anime_info['name']} - Anime Details & Recommendations",
            'description': f"Learn about {anime_info['name']} and discover similar anime. Get personalized recommendations based on this anime.",
            'keywords': f"{anime_info['name']}, anime, {', '.join(anime_info['genres'])}, recommendations"
        }

    return meta_tags.get(page_type, meta_tags['home'])


class AnimeRecommendationSystem:
    def __init__(self, checkpoint_path, dataset_path, animes_path, images_path, mal_urls_path, type_seq_path, genres_path):
        self.model = None
        self.dataset = None
        self.id_to_anime = {}
        self.id_to_url = {}
        self.id_to_mal_url = {}
        self.genres_path = genres_path
        self.id_to_genres = {}
        self.type_seq_path = type_seq_path
        self.id_to_type_seq = {}
        self.checkpoint_path = checkpoint_path
        self.dataset_path = dataset_path
        self.animes_path = animes_path
        self.images_path = images_path
        self.mal_urls_path = mal_urls_path
        self.load_model_and_data()

    def load_model_and_data(self):
     try:
        print("Loading model and data...")
        args.bert_max_len = 128

        
        # mappings of the anime ids
        cache_path =  Path("Data/preprocessed/AnimeRatings_min_rating7-min_uc10-min_sc10-splitleave_one_out/smap.pkl")

  
        with cache_path.open('rb') as f:
            self.dataset = pickle.load(f)
       
        args.num_items = 15687

        with open(self.animes_path, "r", encoding="utf-8") as file:
            self.id_to_anime = json.load(file)

        try:
            with open(self.images_path, "r", encoding="utf-8") as file:
                self.id_to_url = json.load(file)
            print(f"Loaded {len(self.id_to_url)} image URLs")
        except Exception as e:
            print(f"Warning: Could not load image URLs: {str(e)}")
            self.id_to_url = {}

        try:
            with open(self.mal_urls_path, "r", encoding="utf-8") as file:
                self.id_to_mal_url = json.load(file)
            print(f"Loaded {len(self.id_to_mal_url)} MAL URLs")
        except Exception as e:
            print(f"Warning: Could not load MAL URLs: {str(e)}")
            self.id_to_mal_url = {}

        try:
            with open(self.type_seq_path, "r", encoding="utf-8") as file:
                self.id_to_type_seq = json.load(file)
            print(f"Loaded {len(self.id_to_type_seq)} type/sequel info")
        except Exception as e:
            print(f"Warning: Could not load type/sequel info: {str(e)}")
            self.id_to_type_seq = {}

        try:
            with open(self.genres_path, "r", encoding="utf-8") as file:
                self.id_to_genres = json.load(file)
            print(f"Loaded {len(self.id_to_genres)} genre info")
        except Exception as e:
            print(f"Warning: Could not load genres: {str(e)}")
            self.id_to_genres = {}

        self.model = model_factory(args)
        self.load_checkpoint()
        print("Model loaded successfully!")

     except Exception as e:
        print(f"Error loading model: {str(e)}")
        raise e

    def load_checkpoint(self):
        try:
            with open(self.checkpoint_path, 'rb') as f:
                checkpoint = torch.load(f, map_location='cpu', weights_only=False)
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.eval()
        except Exception as e:
            raise Exception(f"Failed to load checkpoint from {self.checkpoint_path}: {str(e)}")

    def get_anime_genres(self, anime_id):
        genres = self.id_to_genres.get(str(anime_id), [])
        return [genre for genre in genres[0]] if genres else []

    def get_all_animes(self):
        animes = []
        for k, v in self.id_to_anime.items():
            anime_name = v[0] if isinstance(v, list) and len(v) > 0 else str(v)
            animes.append((int(k), anime_name))
        animes.sort(key=lambda x: x[1])
        return animes

    def get_anime_image_url(self, anime_id):
        return self.id_to_url.get(str(anime_id), None)

    def get_anime_mal_url(self, anime_id):
        return self.id_to_mal_url.get(str(anime_id), None)

    def get_filtered_anime_pool(self, filters):
        if not filters:
            return None

        if filters.get('show_hentai') and len([k for k, v in filters.items() if v]) == 1:
            hentai_animes = []
            for anime_id_str, anime_data in self.id_to_anime.items():
                anime_id = int(anime_id_str)
                if self._is_hentai(anime_id):
                    hentai_animes.append(anime_id)
            return hentai_animes

        return None

    def _is_hentai(self, anime_id):
        type_seq_info = self.id_to_type_seq.get(str(anime_id))
        if not type_seq_info or len(type_seq_info) < 3:
            return False
        return type_seq_info[2]

    def _get_type(self, anime_id):
        type_seq_info = self.id_to_type_seq.get(str(anime_id))
        if not type_seq_info or len(type_seq_info) < 3:
            return False
        return type_seq_info[1]

    def get_recommendations(self, favorite_anime_ids, num_recommendations=100, filters=None):
        if not favorite_anime_ids:
            return [], [], "Please add some favorite animes first!"

        smap = self.dataset
        inverted_smap = {v: k for k, v in smap.items()}

        converted_ids = []
        for anime_id in favorite_anime_ids:
            if anime_id in smap:
                converted_ids.append(smap[anime_id])

        if not converted_ids:
            return [], [], "None of the selected animes are in the model vocabulary!"

        filtered_pool = self.get_filtered_anime_pool(filters)
        if filtered_pool is not None:
            return self._get_recommendations_from_pool(favorite_anime_ids, filtered_pool, num_recommendations, filters)

        target_len = 128
        padded = converted_ids + [0] * (target_len - len(converted_ids))
        input_tensor = torch.tensor(padded, dtype=torch.long).unsqueeze(0)

        max_predictions = min(500, len(inverted_smap))

        with torch.no_grad():
            logits = self.model(input_tensor)
            last_logits = logits[:, -1, :]
            top_scores, top_indices = torch.topk(last_logits, k=max_predictions, dim=1)

        recommendations = []
        scores = []

        for idx, score in zip(top_indices.numpy()[0], top_scores.detach().numpy()[0]):
            if idx in inverted_smap:
                anime_id = inverted_smap[idx]

                if anime_id in favorite_anime_ids:
                    continue

                if str(anime_id) in self.id_to_anime:
                    if filters and not self._should_include_anime(anime_id, filters):
                        continue

                    anime_data = self.id_to_anime[str(anime_id)]
                    anime_name = anime_data[0] if isinstance(anime_data, list) and len(anime_data) > 0 else str(anime_data)
                    image_url = self.get_anime_image_url(anime_id)
                    mal_url = self.get_anime_mal_url(anime_id)

                    recommendations.append({
                        'id': anime_id,
                        'name': anime_name,
                        'score': float(score),
                        'image_url': image_url,
                        'mal_url': mal_url,
                        'genres': self.get_anime_genres(anime_id)
                    })
                    scores.append(float(score))

                    if len(recommendations) >= num_recommendations:
                        break

        return recommendations, scores, f"Found {len(recommendations)} recommendations!"

    def _get_recommendations_from_pool(self, favorite_anime_ids, anime_pool, num_recommendations, filters):
        try:
            smap = self.dataset
            inverted_smap = {v: k for k, v in smap.items()}

            converted_ids = []
            for anime_id in favorite_anime_ids:
                if anime_id in smap:
                    converted_ids.append(smap[anime_id])

            if not converted_ids:
                return [], [], "None of the selected animes are in the model vocabulary!"

            target_len = 128
            padded = converted_ids + [0] * (target_len - len(converted_ids))
            input_tensor = torch.tensor(padded, dtype=torch.long).unsqueeze(0)

            with torch.no_grad():
                logits = self.model(input_tensor)
                last_logits = logits[:, -1, :]

            anime_scores = []
            for anime_id in anime_pool:
                if anime_id in favorite_anime_ids:
                    continue

                if anime_id in smap:
                    model_id = smap[anime_id]
                    if model_id < last_logits.shape[1]:
                        score = last_logits[0, model_id].item()
                        anime_scores.append((anime_id, score))

            anime_scores.sort(key=lambda x: x[1], reverse=True)

            recommendations = []
            for anime_id, score in anime_scores[:num_recommendations]:
                if str(anime_id) in self.id_to_anime:
                    anime_data = self.id_to_anime[str(anime_id)]
                    anime_name = anime_data[0] if isinstance(anime_data, list) and len(anime_data) > 0 else str(anime_data)
                    image_url = self.get_anime_image_url(anime_id)
                    mal_url = self.get_anime_mal_url(anime_id)

                    recommendations.append({
                        'id': anime_id,
                        'name': anime_name,
                        'score': float(score),
                        'image_url': image_url,
                        'mal_url': mal_url,
                        'genres': self.get_anime_genres(anime_id)
                    })

            return recommendations, [r['score'] for r in recommendations], f"Found {len(recommendations)} filtered recommendations!"

        except Exception as e:
            return [], [], f"Error during filtered prediction: {str(e)}"

    def _should_include_anime(self, anime_id, filters):
        if 'blacklisted_animes' in filters:
            if anime_id in filters['blacklisted_animes']:
                return False

        type_seq_info = self.id_to_type_seq.get(str(anime_id))
        if not type_seq_info or len(type_seq_info) < 2:
            return True

        anime_type = type_seq_info[0]
        is_sequel = type_seq_info[1]
        is_hentai = type_seq_info[2]

        if 'show_sequels' in filters:
            if not filters['show_sequels'] and is_sequel:
                return False

        if 'show_hentai' in filters:
            if filters['show_hentai']:
                if not is_hentai:
                    return False
            else:
                if is_hentai:
                    return False

        if 'show_movies' in filters:
            if not filters['show_movies'] and anime_type == 'MOVIE':
                return False

        if 'show_tv' in filters:
            if not filters['show_tv'] and anime_type == 'TV':
                return False

        if 'show_ova' in filters:
            if not filters['show_ova'] and anime_type in ['ONA', 'OVA', 'SPECIAL']:
                return False

        return True


recommendation_system = None


@app.route('/')
def index():
    if recommendation_system is None:
        return render_template('error.html', error="Recommendation system not initialized. Please check server logs.")

    animes = recommendation_system.get_all_animes()
    return render_template('index.html', animes=animes)


@app.route('/api/search_animes')
def search_animes():
    query = request.args.get('q', '').lower()
    animes = []

    for k, v in recommendation_system.id_to_anime.items():
        anime_names = v if isinstance(v, list) else [v]

        match_found = False
        for name in anime_names:
            if query in name.lower():
                match_found = True
                break

        if not query or match_found:
            main_name = anime_names[0] if anime_names else "Unknown"
            animes.append((int(k), main_name))

    animes.sort(key=lambda x: x[1])
    return jsonify(animes)


@app.route('/api/add_favorite', methods=['POST'])
def add_favorite():
    sid, favorites = get_user_favorites()
    data = request.get_json()
    anime_id = int(data['anime_id'])
    if anime_id not in favorites:
        favorites.append(anime_id)
        save_sessions()  
        return jsonify({'success': True, 'session_id': sid})
    else:
        return jsonify({'success': False, 'session_id': sid})


@app.route('/api/remove_favorite', methods=['POST'])
def remove_favorite():
    sid, favorites = get_user_favorites()
    data = request.get_json()
    anime_id = int(data['anime_id'])
    if anime_id in favorites:
        favorites.remove(anime_id)
        save_sessions()  
        return jsonify({'success': True, 'session_id': sid})
    else:
        return jsonify({'success': False, 'session_id': sid})


@app.route('/api/clear_favorites', methods=['POST'])
def clear_favorites():
    sid, favorites = get_user_favorites()
    _sessions[sid] = []
    save_sessions() 
    return jsonify({'success': True, 'session_id': sid})


@app.route('/api/get_favorites')
def get_favorites():
    sid, favorites = get_user_favorites()
    favorite_animes = []
    for anime_id in favorites:
        if str(anime_id) in recommendation_system.id_to_anime:
            anime_data = recommendation_system.id_to_anime[str(anime_id)]
            anime_name = anime_data[0] if isinstance(anime_data, list) and len(anime_data) > 0 else str(anime_data)
            favorite_animes.append({'id': anime_id, 'name': anime_name})
    return jsonify(favorite_animes)


@app.route('/api/get_recommendations', methods=['POST'])
def get_recommendations():
    sid, favorites = get_user_favorites()
    if not favorites:
        return jsonify({'success': False, 'message': 'Please add some favorite animes first!'})

    data = request.get_json() or {}
    filters = data.get('filters', {})

    blacklisted_animes = data.get('blacklisted_animes', [])
    if blacklisted_animes:
        filters['blacklisted_animes'] = blacklisted_animes

    recommendations, scores, message = recommendation_system.get_recommendations(
        favorites,
        filters=filters
    )

    if recommendations:
        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'message': message
        })
    else:
        return jsonify({'success': False, 'message': message})


@app.route('/api/mal_logo')
def get_mal_logo():
    return jsonify({
        'success': True,
        'logo_url': 'https://cdn.myanimelist.net/img/sp/icon/apple-touch-icon-256.png'
    })


def main():
    load_sessions()
    global recommendation_system

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    def resolve(arg_val, filename):
        """args'tan gelen değeri kullan; yoksa BASE_DIR altında ara."""
        if arg_val is not None:
            return arg_val
        return os.path.join(BASE_DIR, filename)

    try:
        images_path   = resolve(getattr(args, 'images_path', None),   "id_to_url.json")
        mal_urls_path = resolve(getattr(args, 'mal_urls_path', None),  "anime_to_malurl.json")
        type_seq_path = resolve(getattr(args, 'type_seq_path', None),  "anime_to_typenseq.json")
        checkpoint_path = resolve(getattr(args, 'checkpoint_path', None), "best_model.pth")
        dataset_path    = resolve(getattr(args, 'dataset_path', None),    "dataset.pkl")
        animes_path     = resolve(getattr(args, 'animes_path', None),     "anime_names.json")
        genres_path     = resolve(getattr(args, 'genres_path', None),     "anime_genres.json")

        if not os.path.exists(images_path):
            print(f"Warning: id_to_url.json not found. Images will not be displayed.")

        if not os.path.exists(mal_urls_path):
            print(f"Warning: anime_to_malurl.json not found. MAL links will not be available.")

        recommendation_system = AnimeRecommendationSystem(
            "Data/AnimeRatings/pretrained_bert.pth",
            "Data/preprocessed/AnimeRatings_min_rating7-min_uc10-min_sc10-splitleave_one_out/dataset.pkl",
            "Data/animes.json",
            "Data/id_to_url.json",
            "Data/anime_to_malurl.json",
            "Data/anime_to_typenseq.json",
            "Data/id_to_genres.json"
        )
        print("Recommendation system initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize recommendation system: {e}")
        sys.exit(1)

    port = int(os.environ.get('FLASK_PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port, use_reloader=False)


if __name__ == "__main__":
    main()
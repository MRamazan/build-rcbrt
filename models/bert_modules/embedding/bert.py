import torch
import torch.nn as nn
import torch.nn.functional as F
import pickle
import json
import threading
from pathlib import Path
import torch.nn as nn
from .token import TokenEmbedding
from .position import PositionalEmbedding
import time
from pathlib import Path
from torch.nn.utils.rnn import pad_sequence
import pickle 
import json
import os

class BERTEmbedding(nn.Module):
    _mappings_cache = None
    _cache_lock = threading.Lock()
    
    @classmethod
    def _load_mappings(cls):
        if cls._mappings_cache is None:
            with cls._cache_lock:
                if cls._mappings_cache is None:  # Double-checked locking
                    try:

                        main_dir = os.getcwd()

                        relative_path_dataset = "Data/preprocessed/AnimeRatings_min_rating7-min_uc10-min_sc10-splitleave_one_out/smap.pkl"
                        relative_path_genres = "Data/AnimeRatings/id_to_genreids.json"

                        full_path_dataset = Path(main_dir) / relative_path_dataset
                        full_path_genres = Path(main_dir) / relative_path_genres


                        with full_path_dataset.open('rb') as f:
                            dataset_smap = pickle.load(f)
                        
                        with full_path_genres.open('rb') as f:
                            id_to_genres = json.load(f)
                        
                        cls._mappings_cache = {
                            'dataset_smap': dataset_smap,
                            'id_to_genres': id_to_genres
                        }
                        
                    except Exception as e:
                        print(f"Warning: Could not load mappings: {e}")
                        cls._mappings_cache = {
                            'dataset_smap': {},
                            'id_to_genres': {}
                        }
        return cls._mappings_cache
    
    def __init__(self, vocab_size, embed_size, max_len, dropout=0.1, multi_genre=True, max_genres_per_anime=5):
        super().__init__()

        mappings = self._load_mappings()
        dataset_smap = mappings['dataset_smap']
        id_to_genres = mappings['id_to_genres']
        
        self.multi_genre = multi_genre
        self.max_genres_per_anime = max_genres_per_anime

        all_genres = set()
        for anime_id, genres in id_to_genres.items():
            all_genres.update(genres)

        max_genre_id = max(all_genres) if all_genres else 0
        self.num_genres = max_genre_id + 1
        
        print(f"Detected {self.num_genres} unique genres (max_id: {max_genre_id})")

        self.vocab_size = vocab_size
        
        if multi_genre:
            self._create_multi_genre_mapping(dataset_smap, id_to_genres, vocab_size)
        else:
            self._create_single_genre_mapping(dataset_smap, id_to_genres, vocab_size)

        self.token = TokenEmbedding(vocab_size=vocab_size, embed_size=embed_size)
        self.genre_embed = nn.Embedding(num_embeddings=self.num_genres, embedding_dim=embed_size, padding_idx=0)

        if multi_genre:
            self.fusion_layer = nn.Sequential(
                nn.Linear(embed_size * 2, embed_size),
                nn.LayerNorm(embed_size),
                nn.ReLU()
            )

            self.genre_aggregation = nn.Parameter(torch.ones(max_genres_per_anime) / max_genres_per_anime)
            self.genre_attention = nn.MultiheadAttention(embed_size, num_heads=4, batch_first=True)
        else:
            self.fusion_layer = nn.Sequential(
                nn.Linear(embed_size * 2, embed_size),
                nn.LayerNorm(embed_size),
                nn.ReLU()
            )
        
        self.dropout = nn.Dropout(p=dropout)
        self.embed_size = embed_size

        self._genre_cache = {}
        self._cache_lock = threading.Lock()
    
    def _create_single_genre_mapping(self, dataset_smap, id_to_genres, vocab_size):
        token_to_genre = {}
        for anime_id, token_id in dataset_smap.items():
            if token_id < vocab_size:
                genre_list = id_to_genres.get(str(anime_id), [0])
                genre_id = genre_list[0] if genre_list else 0
                if genre_id >= self.num_genres:
                    print(f"Warning: Genre ID {genre_id} >= {self.num_genres}, setting to 0")
                    genre_id = 0
                token_to_genre[token_id] = genre_id
        
        if token_to_genre:
            token_ids = torch.tensor(list(token_to_genre.keys()), dtype=torch.long)
            genre_ids = torch.tensor(list(token_to_genre.values()), dtype=torch.long)
            
            self.register_buffer('token_ids', token_ids)
            self.register_buffer('genre_ids', genre_ids)
            self.has_mappings = True
        else:
            self.register_buffer('token_ids', torch.empty(0, dtype=torch.long))
            self.register_buffer('genre_ids', torch.empty(0, dtype=torch.long))
            self.has_mappings = False
    
    def _create_multi_genre_mapping(self, dataset_smap, id_to_genres, vocab_size):
        token_to_genres = {}
        for anime_id, token_id in dataset_smap.items():
            if token_id < vocab_size:
                genre_list = id_to_genres.get(str(anime_id), [0])

                valid_genres = []
                for genre_id in genre_list:
                    if genre_id >= self.num_genres:
                        print(f"Warning: Genre ID {genre_id} >= {self.num_genres}, setting to 0")
                        genre_id = 0
                    valid_genres.append(genre_id)

                if len(valid_genres) < self.max_genres_per_anime:
                    valid_genres.extend([0] * (self.max_genres_per_anime - len(valid_genres)))
                else:
                    valid_genres = valid_genres[:self.max_genres_per_anime]
                
                token_to_genres[token_id] = valid_genres
        
        if token_to_genres:
            token_ids = torch.tensor(list(token_to_genres.keys()), dtype=torch.long)
            genre_ids = torch.tensor(list(token_to_genres.values()), dtype=torch.long)
            
            self.register_buffer('token_ids', token_ids)
            self.register_buffer('genre_ids', genre_ids)
            self.has_mappings = True
        else:
            self.register_buffer('token_ids', torch.empty(0, dtype=torch.long))
            self.register_buffer('genre_ids', torch.empty(0, self.max_genres_per_anime, dtype=torch.long))
            self.has_mappings = False
    
    def _get_single_genre_mapping(self, sequence):
        """Original single genre mapping with improved bounds checking"""
        batch_size, seq_len = sequence.shape
        device = sequence.device
        
        if not self.has_mappings:
            return torch.zeros_like(sequence)

        sequence = torch.clamp(sequence, 0, self.vocab_size - 1)
        
        genre_sequence = torch.zeros_like(sequence)
        flat_sequence = sequence.flatten()
        flat_genre = torch.zeros_like(flat_sequence)
        
        token_mask = torch.isin(flat_sequence, self.token_ids)
        
        if token_mask.any():
            valid_tokens = flat_sequence[token_mask]

            with self._cache_lock:
                cache_key = (device, len(self.token_ids))
                if cache_key not in self._genre_cache:
                    sorted_indices = torch.argsort(self.token_ids)
                    self._genre_cache[cache_key] = {
                        'sorted_tokens': self.token_ids[sorted_indices],
                        'sorted_genres': self.genre_ids[sorted_indices]
                    }
                
                cached_data = self._genre_cache[cache_key]
            
            indices = torch.searchsorted(cached_data['sorted_tokens'], valid_tokens)
            indices = torch.clamp(indices, 0, len(cached_data['sorted_tokens']) - 1)
            exact_matches = cached_data['sorted_tokens'][indices] == valid_tokens
            
            genre_values = torch.where(
                exact_matches, 
                cached_data['sorted_genres'][indices], 
                torch.tensor(0, device=device, dtype=self.genre_ids.dtype)
            )
            
            flat_genre[token_mask] = genre_values
        
        return flat_genre.view(batch_size, seq_len)
    
    def _get_multi_genre_mapping(self, sequence):
        """Get multiple genres for each anime in sequence with bounds checking"""
        batch_size, seq_len = sequence.shape
        device = sequence.device
        
        if not self.has_mappings:
            return torch.zeros(batch_size, seq_len, self.max_genres_per_anime, device=device, dtype=torch.long)

        sequence = torch.clamp(sequence, 0, self.vocab_size - 1)

        genre_sequences = torch.zeros(batch_size, seq_len, self.max_genres_per_anime, device=device, dtype=torch.long)
        
        flat_sequence = sequence.flatten()
        flat_genres = torch.zeros(len(flat_sequence), self.max_genres_per_anime, device=device, dtype=torch.long)
        
        token_mask = torch.isin(flat_sequence, self.token_ids)
        
        if token_mask.any():
            valid_tokens = flat_sequence[token_mask]

            with self._cache_lock:
                cache_key = (device, len(self.token_ids), 'multi')
                if cache_key not in self._genre_cache:
                    sorted_indices = torch.argsort(self.token_ids)
                    self._genre_cache[cache_key] = {
                        'sorted_tokens': self.token_ids[sorted_indices],
                        'sorted_genres': self.genre_ids[sorted_indices]  # Shape: (num_tokens, max_genres_per_anime)
                    }
                
                cached_data = self._genre_cache[cache_key]
            
            indices = torch.searchsorted(cached_data['sorted_tokens'], valid_tokens)
            indices = torch.clamp(indices, 0, len(cached_data['sorted_tokens']) - 1)
            exact_matches = cached_data['sorted_tokens'][indices] == valid_tokens

            genre_values = cached_data['sorted_genres'][indices]  # Shape: (num_valid_tokens, max_genres_per_anime)

            valid_mask = token_mask.nonzero(as_tuple=True)[0]
            exact_valid_mask = valid_mask[exact_matches]
            
            flat_genres[exact_valid_mask] = genre_values[exact_matches]
        
        return flat_genres.view(batch_size, seq_len, self.max_genres_per_anime)
    
    def _aggregate_genre_embeddings(self, genre_embeddings):
        """Aggregate multiple genre embeddings per anime"""
        batch_size, seq_len, max_genres, embed_size = genre_embeddings.shape

        weights = F.softmax(self.genre_aggregation, dim=0)
        weighted_genres = torch.einsum('bsgd,g->bsd', genre_embeddings, weights)
        
        return weighted_genres
    
    def forward(self, sequence):
        """
        Enhanced forward pass with per-anime genre processing
        """
        if sequence.max() >= self.vocab_size:
            print(f"Warning: Input contains tokens >= vocab_size ({self.vocab_size})")
            
        sequence = torch.clamp(sequence, 0, self.vocab_size - 1)

        token_emb = self.token(sequence)

        if self.multi_genre:
            genre_sequences = self._get_multi_genre_mapping(sequence)  # (batch, seq, max_genres)
            
            genre_sequences = torch.clamp(genre_sequences, 0, self.num_genres - 1)
            
            genre_embeddings = self.genre_embed(genre_sequences)  # (batch, seq, max_genres, embed_size)
            
            aggregated_genre_emb = self._aggregate_genre_embeddings(genre_embeddings)  # (batch, seq, embed_size)

            combined = torch.cat([token_emb, aggregated_genre_emb], dim=-1)
        else:
            genre_sequence = self._get_single_genre_mapping(sequence)
            
            genre_sequence = torch.clamp(genre_sequence, 0, self.num_genres - 1)
            
            genre_emb = self.genre_embed(genre_sequence)
            combined = torch.cat([token_emb, genre_emb], dim=-1)

        x = self.fusion_layer(combined)
        
        return self.dropout(x)

    
    def clear_cache(self):
        """Clear internal caches to free GPU memory"""
        with self._cache_lock:
            self._genre_cache.clear()
    
    @classmethod
    def clear_global_cache(cls):
        """Clear global mappings cache"""
        with cls._cache_lock:
            cls._mappings_cache = None

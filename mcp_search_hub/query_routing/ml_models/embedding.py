"""Embedding generator for text representation."""

import logging
import multiprocessing
import os
from functools import lru_cache
from multiprocessing import cpu_count

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Flag to control whether to use ML features
USE_ML = os.environ.get("USE_ML_FEATURES", "true").lower() == "true"


class EmbeddingResult(BaseModel):
    """Result of embedding generation."""

    text: str = Field(..., description="The text that was embedded")
    embedding: list[float] = Field(..., description="The embedding vector")
    model_name: str = Field(..., description="Name of the model used for embedding")


class EmbeddingGenerator:
    """Generates embeddings for text using sentence-transformers."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_size: int = 1000,
        use_gpu: bool = False,
        backend: str = "default",
        cache_folder: str | None = None,
        use_quantization: bool = False,
        use_disk_cache: bool = False,
        parallel_processes: int | None = None,
    ):
        """Initialize the embedding generator.

        Args:
            model_name: Name of the sentence-transformers model to use
            cache_size: Size of the LRU cache for embeddings
            use_gpu: Whether to use GPU for embedding generation
            backend: Model backend ('default', 'onnx', or 'openvino')
            cache_folder: Directory to cache downloaded models
            use_quantization: Whether to use model quantization for faster inference
            use_disk_cache: Whether to cache embeddings to disk
            parallel_processes: Number of processes for parallel embedding (None for auto)
        """
        self.model_name = model_name
        self.cache_size = cache_size
        self.use_gpu = use_gpu
        self.backend = backend
        self.use_quantization = use_quantization
        self.use_disk_cache = use_disk_cache
        self.cache_folder = cache_folder or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "model_cache"
        )
        self._model = None

        # Configure multiprocessing
        self.parallel_processes = parallel_processes
        if parallel_processes is None:
            # Auto-configure based on CPU count
            self.parallel_processes = max(1, cpu_count() - 1)

        # Set up disk cache if enabled
        if use_disk_cache:
            self._setup_disk_cache()

        # Initialize the model lazily to avoid loading it unnecessarily
        if USE_ML:
            try:
                import torch

                # Set device
                self.device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
                logger.info(f"Embedding generator will use device: {self.device}")

                # Check for tensor cores (Ampere or newer) to enable BF16
                self.use_bf16 = False
                self.use_fp16 = False
                if self.device == "cuda":
                    capability = torch.cuda.get_device_capability()[0]
                    if capability >= 8:  # Ampere (RTX 30xx) or newer
                        self.use_bf16 = True
                        logger.info("CUDA device supports BF16 precision")
                    else:
                        self.use_fp16 = True
                        logger.info("CUDA device supports FP16 precision")
            except ImportError:
                logger.warning(
                    "Torch not available. Embedding generator will use CPU only."
                )
                self.device = "cpu"
        else:
            logger.info("ML features are disabled. Using fallback methods.")

    def _setup_disk_cache(self) -> None:
        """Set up disk cache for embeddings."""
        try:
            import hashlib

            import diskcache

            # Create cache directory
            cache_dir = os.path.join(self.cache_folder, "embedding_cache")
            os.makedirs(cache_dir, exist_ok=True)

            # Initialize disk cache
            self._disk_cache = diskcache.Cache(cache_dir)
            logger.info(f"Disk cache initialized at {cache_dir}")

            # Function to hash text for cache key
            def text_hash(text: str) -> str:
                return hashlib.md5(text.encode()).hexdigest()

            self._text_hash = text_hash

        except ImportError:
            logger.warning("diskcache package not available. Disk caching disabled.")
            self.use_disk_cache = False

    @property
    def model(self):
        """Lazily load the model when needed."""
        if self._model is None and USE_ML:
            try:
                import os

                from sentence_transformers import SentenceTransformer

                # Ensure cache directory exists
                os.makedirs(self.cache_folder, exist_ok=True)

                # Load model with appropriate backend
                model_kwargs = {"device": self.device}

                if self.backend != "default":
                    logger.info(f"Using {self.backend} backend for embedding model")
                    model_kwargs["backend"] = self.backend

                self._model = SentenceTransformer(
                    self.model_name, cache_folder=self.cache_folder, **model_kwargs
                )

                # Apply precision optimizations if on GPU
                if self.device == "cuda":
                    if self.use_bf16:
                        self._model = self._model.bfloat16()
                        logger.info("Using bfloat16 precision for embedding model")
                    elif self.use_fp16:
                        self._model = self._model.half()
                        logger.info("Using float16 precision for embedding model")

                # Apply quantization if requested
                if self.use_quantization:
                    try:
                        from sentence_transformers.quantization import quantize_model

                        self._model = quantize_model(self._model)
                        logger.info("Applied quantization to embedding model")
                    except (ImportError, Exception) as e:
                        logger.warning(f"Failed to apply quantization: {e}")

                logger.info(f"Loaded embedding model: {self.model_name}")
            except ImportError:
                logger.warning(
                    "sentence-transformers not available. Embeddings will be "
                    "randomly generated as fallback."
                )
                self._model = "fallback"
            except Exception as e:
                logger.error(f"Error loading embedding model: {e}")
                self._model = "fallback"

        return self._model

    def _get_from_disk_cache(self, text: str) -> list[float] | None:
        """Get embedding from disk cache if available."""
        if not self.use_disk_cache:
            return None

        try:
            key = f"{self.model_name}:{self._text_hash(text)}"
            embedding = self._disk_cache.get(key)
            if embedding is not None:
                return embedding
        except Exception as e:
            logger.debug(f"Error retrieving from disk cache: {e}")

        return None

    def _save_to_disk_cache(self, text: str, embedding: list[float]) -> None:
        """Save embedding to disk cache."""
        if not self.use_disk_cache:
            return

        try:
            key = f"{self.model_name}:{self._text_hash(text)}"
            self._disk_cache.set(key, embedding)
        except Exception as e:
            logger.debug(f"Error saving to disk cache: {e}")

    @lru_cache(maxsize=1000)
    def _generate_cached(self, text: str) -> list[float]:
        """Generate embedding with caching."""
        # Try disk cache first if enabled
        if self.use_disk_cache:
            cached_embedding = self._get_from_disk_cache(text)
            if cached_embedding is not None:
                return cached_embedding

        # Fallback mode
        if self.model == "fallback" or not USE_ML:
            # Use a hash-based fallback for reproducibility
            import hashlib

            hash_obj = hashlib.md5(text.encode())
            hash_val = int(hash_obj.hexdigest(), 16)
            np.random.seed(hash_val)
            # Generate a fixed-length embedding (384 matches all-MiniLM-L6-v2)
            embedding = np.random.normal(0, 1, 384).tolist()

            # Save to disk cache if enabled
            if self.use_disk_cache:
                self._save_to_disk_cache(text, embedding)

            return embedding

        # Actually generate the embedding
        embedding = self.model.encode(text)
        result = embedding.tolist()

        # Save to disk cache if enabled
        if self.use_disk_cache:
            self._save_to_disk_cache(text, result)

        return result

    def generate(self, text: str) -> EmbeddingResult:
        """Generate embedding for a text string.

        Args:
            text: The text to embed

        Returns:
            EmbeddingResult with the embedding vector
        """
        embedding = self._generate_cached(text)
        return EmbeddingResult(
            text=text, embedding=embedding, model_name=self.model_name
        )

    def _process_batch(self, texts_chunk: list[str]) -> list[EmbeddingResult]:
        """Process a batch of texts to generate embeddings.

        This function is used by the parallel processing system.
        """
        if self.model == "fallback" or not USE_ML:
            return [self.generate(text) for text in texts_chunk]

        try:
            embeddings = self.model.encode(
                texts_chunk,
                batch_size=32,  # Optimal batch size for most GPUs
                show_progress_bar=False,
                convert_to_tensor=True,
                normalize_embeddings=True,  # Pre-normalize for similarity calculations
            )

            # Convert to list format if we got tensors
            if hasattr(embeddings, "cpu"):
                embeddings = embeddings.cpu().numpy()

            results = []
            for text, embedding in zip(texts_chunk, embeddings, strict=False):
                emb_list = (
                    embedding.tolist() if hasattr(embedding, "tolist") else embedding
                )

                # Save to disk cache if enabled
                if self.use_disk_cache:
                    self._save_to_disk_cache(text, emb_list)

                results.append(
                    EmbeddingResult(
                        text=text, embedding=emb_list, model_name=self.model_name
                    )
                )
            return results
        except Exception as e:
            logger.warning(
                f"Batch processing error: {e}. Falling back to individual encoding."
            )
            return [self.generate(text) for text in texts_chunk]

    def batch_generate(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResults
        """
        # For small batches, use the cached single embedding approach
        if len(texts) < 10 or self.model == "fallback" or not USE_ML:
            return [self.generate(text) for text in texts]

        # For medium batches, use the batch encoding capability without parallelization
        if len(texts) < 100 or self.parallel_processes <= 1:
            return self._process_batch(texts)

        # For large batches, use parallel processing
        try:
            # Check disk cache first if enabled
            if self.use_disk_cache:
                # Try to get embeddings from cache first
                cached_results = []
                texts_to_process = []

                for text in texts:
                    cached_embedding = self._get_from_disk_cache(text)
                    if cached_embedding is not None:
                        cached_results.append(
                            EmbeddingResult(
                                text=text,
                                embedding=cached_embedding,
                                model_name=self.model_name,
                            )
                        )
                    else:
                        texts_to_process.append(text)

                # If all embeddings were in cache, return them
                if not texts_to_process:
                    return cached_results

                # Otherwise, process the remaining texts and combine results
                texts = texts_to_process

            # Divide texts into chunks for parallel processing
            chunk_size = max(10, len(texts) // self.parallel_processes)
            chunks = [
                texts[i : i + chunk_size] for i in range(0, len(texts), chunk_size)
            ]

            # Process chunks in parallel
            with multiprocessing.Pool(
                processes=min(len(chunks), self.parallel_processes)
            ) as pool:
                results = pool.map(self._process_batch, chunks)

            # Flatten results
            all_results = [result for sublist in results for result in sublist]

            # Combine with cached results if any
            if self.use_disk_cache and cached_results:
                all_results.extend(cached_results)

            return all_results

        except Exception as e:
            logger.warning(
                f"Parallel batch encoding error: {e}. Falling back to single process."
            )
            try:
                return self._process_batch(texts)
            except Exception as e2:
                logger.warning(
                    f"Single process batch encoding also failed: {e2}. Using individual encoding."
                )
                return [self.generate(text) for text in texts]

    def similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score between 0 and 1
        """
        # If we have disk cache, check if both embeddings are already cached
        if self.use_disk_cache:
            cached_emb1 = self._get_from_disk_cache(text1)
            cached_emb2 = self._get_from_disk_cache(text2)

            if cached_emb1 is not None and cached_emb2 is not None:
                # Both embeddings found in cache, compute similarity directly
                emb1 = np.array(cached_emb1)
                emb2 = np.array(cached_emb2)

                # Normalize for cosine similarity
                emb1 = emb1 / (np.linalg.norm(emb1) + 1e-8)
                emb2 = emb2 / (np.linalg.norm(emb2) + 1e-8)

                return float(np.dot(emb1, emb2))

        if self.model == "fallback" or not USE_ML:
            # Fall back to numpy implementation
            emb1 = np.array(self.generate(text1).embedding)
            emb2 = np.array(self.generate(text2).embedding)

            # Cosine similarity
            dot_product = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)

            if norm1 * norm2 == 0:
                return 0.0

            return float(dot_product / (norm1 * norm2))

        try:
            # Use built-in sentence-transformers similarity which is more optimized
            similarity = self.model.similarity(text1, text2)
            return float(similarity)
        except Exception as e:
            logger.warning(f"Built-in similarity failed: {e}. Using fallback method.")
            # Fall back to manually computing similarity with our embeddings
            return float(
                np.dot(
                    np.array(self.generate(text1).embedding),
                    np.array(self.generate(text2).embedding),
                )
            )

    def batch_similarity(
        self, reference: str, candidates: list[str]
    ) -> list[tuple[str, float]]:
        """Calculate similarities between a reference and multiple candidates.

        Args:
            reference: Reference text
            candidates: List of candidate texts

        Returns:
            List of (text, similarity) tuples, sorted by similarity (highest first)
        """
        # For very small batches or fallback mode, use single similarity computations
        if len(candidates) < 5 or (
            self.model == "fallback" and not self.use_disk_cache
        ):
            similarities = [
                (candidate, self.similarity(reference, candidate))
                for candidate in candidates
            ]
            return sorted(similarities, key=lambda x: x[1], reverse=True)

        # If using disk cache, optimize by checking what's already cached
        ref_embedding = None
        candidates_to_compute = []
        candidates_with_embeddings = []
        result_map = {}

        if self.use_disk_cache:
            # Try to get reference embedding from cache
            ref_embedding = self._get_from_disk_cache(reference)
            if ref_embedding is not None:
                ref_embedding = np.array(ref_embedding)
                # Normalize for cosine similarity
                ref_embedding = ref_embedding / (np.linalg.norm(ref_embedding) + 1e-8)

            # Check which candidate embeddings are in cache
            for candidate in candidates:
                cached_emb = self._get_from_disk_cache(candidate)
                if cached_emb is not None:
                    candidates_with_embeddings.append((candidate, np.array(cached_emb)))
                else:
                    candidates_to_compute.append(candidate)

            # If reference is cached and some candidates are cached, compute similarities
            if ref_embedding is not None and candidates_with_embeddings:
                for candidate, emb in candidates_with_embeddings:
                    # Normalize the embedding
                    emb = emb / (np.linalg.norm(emb) + 1e-8)
                    similarity = float(np.dot(ref_embedding, emb))
                    result_map[candidate] = similarity

            # If all candidates were in cache, return the results
            if not candidates_to_compute and ref_embedding is not None:
                result = [(candidate, score) for candidate, score in result_map.items()]
                return sorted(result, key=lambda x: x[1], reverse=True)
        else:
            # If not using disk cache, compute all
            candidates_to_compute = candidates

        # If fallback mode and we get here, compute remaining with basic method
        if self.model == "fallback" or not USE_ML:
            # Compute similarities for remaining candidates
            for candidate in candidates_to_compute:
                score = self.similarity(reference, candidate)
                result_map[candidate] = score

            # Return all results sorted
            result = [(candidate, score) for candidate, score in result_map.items()]
            return sorted(result, key=lambda x: x[1], reverse=True)

        # Process remaining candidates with batch encoding
        try:
            # If reference embedding not yet computed, do it now
            if ref_embedding is None:
                ref_embedding = self.model.encode(
                    reference, convert_to_tensor=True, normalize_embeddings=True
                )

                # Save to disk cache if enabled
                if self.use_disk_cache:
                    self._save_to_disk_cache(
                        reference,
                        ref_embedding.cpu().numpy().tolist()
                        if hasattr(ref_embedding, "cpu")
                        else ref_embedding.tolist(),
                    )

            # Process large batches with parallel processing if available
            if len(candidates_to_compute) >= 100 and self.parallel_processes > 1:
                # Instead of computing similarities directly, get embeddings in parallel
                batch_results = self.batch_generate(candidates_to_compute)

                # Process embeddings
                for result in batch_results:
                    candidate = result.text
                    embedding = np.array(result.embedding)

                    # Ensure reference is in proper numpy format
                    if hasattr(ref_embedding, "cpu"):
                        ref_np = ref_embedding.cpu().numpy()
                    else:
                        ref_np = np.array(ref_embedding)

                    # Compute similarity
                    similarity = float(
                        np.dot(
                            embedding / (np.linalg.norm(embedding) + 1e-8),
                            ref_np / (np.linalg.norm(ref_np) + 1e-8),
                        )
                    )
                    result_map[candidate] = similarity
            else:
                # For medium batches, encode in one go
                candidate_embeddings = self.model.encode(
                    candidates_to_compute,
                    batch_size=32,
                    convert_to_tensor=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )

                # Save to disk cache if enabled
                if self.use_disk_cache:
                    if hasattr(candidate_embeddings, "cpu"):
                        candidate_numpy = candidate_embeddings.cpu().numpy()
                        for i, candidate in enumerate(candidates_to_compute):
                            self._save_to_disk_cache(
                                candidate, candidate_numpy[i].tolist()
                            )
                    else:
                        for i, candidate in enumerate(candidates_to_compute):
                            self._save_to_disk_cache(
                                candidate,
                                candidate_embeddings[i].tolist()
                                if hasattr(candidate_embeddings[i], "tolist")
                                else candidate_embeddings[i],
                            )

                # Compute similarities efficiently
                import torch

                if isinstance(ref_embedding, torch.Tensor) and isinstance(
                    candidate_embeddings, torch.Tensor
                ):
                    similarities = (
                        torch.matmul(candidate_embeddings, ref_embedding)
                        .cpu()
                        .numpy()
                        .tolist()
                    )
                else:
                    # Fall back to numpy if not tensors
                    similarities = np.dot(candidate_embeddings, ref_embedding)
                    if hasattr(similarities, "tolist"):
                        similarities = similarities.tolist()

                # Add to result map
                for candidate, score in zip(
                    candidates_to_compute, similarities, strict=False
                ):
                    result_map[candidate] = float(score)

            # Combine results and sort
            result = [(candidate, score) for candidate, score in result_map.items()]
            return sorted(result, key=lambda x: x[1], reverse=True)

        except Exception as e:
            logger.warning(f"Batch similarity failed: {e}. Using fallback method.")
            # Fall back to individual similarity calculations
            for candidate in candidates_to_compute:
                score = self.similarity(reference, candidate)
                result_map[candidate] = score

            # Return all results sorted
            result = [(candidate, score) for candidate, score in result_map.items()]
            return sorted(result, key=lambda x: x[1], reverse=True)

"""Tests for embedding generator module."""

import os
import tempfile
from unittest import mock

import numpy as np
import pytest

from mcp_search_hub.query_routing.ml_models.embedding import (
    USE_ML,
    EmbeddingGenerator,
    EmbeddingResult,
)


class TestEmbeddingGenerator:
    """Test embedding generator functionality."""

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        generator = EmbeddingGenerator()
        assert generator.model_name == "all-MiniLM-L6-v2"
        assert generator.cache_size == 1000
        assert generator.use_gpu is False
        assert generator.backend == "default"
        assert generator.use_quantization is False
        assert generator.use_disk_cache is False
        assert generator._model is None

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        generator = EmbeddingGenerator(
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
            cache_size=2000,
            use_gpu=True,
            backend="onnx",
            use_quantization=True,
            use_disk_cache=True,
            parallel_processes=4,
        )
        assert generator.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert generator.cache_size == 2000
        assert generator.use_gpu is True
        assert generator.backend == "onnx"
        assert generator.use_quantization is True
        assert generator.use_disk_cache is True
        assert generator.parallel_processes == 4
        assert generator._model is None

    @pytest.mark.skipif(not USE_ML, reason="ML features disabled")
    def test_disk_cache(self):
        """Test disk cache functionality."""
        # Create a temporary directory for the cache
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create generator with disk cache
            generator = EmbeddingGenerator(
                model_name="all-MiniLM-L6-v2",
                cache_folder=tmpdir,
                use_disk_cache=True,
            )

            # Mock the _setup_disk_cache method to verify it was called
            with mock.patch.object(
                EmbeddingGenerator,
                "_setup_disk_cache",
                wraps=generator._setup_disk_cache,
            ) as mock_setup:
                # Force initialization
                generator._setup_disk_cache()

                # Verify the method was called
                assert mock_setup.call_count == 1

                # Verify the disk cache directory was created
                cache_dir = os.path.join(tmpdir, "embedding_cache")
                assert os.path.exists(cache_dir)

    def test_generate_fallback(self):
        """Test embedding generation with fallback."""
        # Create generator with ML disabled
        with mock.patch(
            "mcp_search_hub.query_routing.ml_models.embedding.USE_ML", False
        ):
            generator = EmbeddingGenerator()

            # Generate embedding
            result = generator.generate("test text")

            # Verify result
            assert isinstance(result, EmbeddingResult)
            assert result.text == "test text"
            assert len(result.embedding) == 384  # Default size
            assert result.model_name == "all-MiniLM-L6-v2"

            # Generate again and verify deterministic fallback
            result2 = generator.generate("test text")
            assert result.embedding == result2.embedding

    def test_batch_generate_fallback(self):
        """Test batch embedding generation with fallback."""
        # Create generator with ML disabled
        with mock.patch(
            "mcp_search_hub.query_routing.ml_models.embedding.USE_ML", False
        ):
            generator = EmbeddingGenerator()

            # Generate batch embeddings
            texts = ["text1", "text2", "text3"]
            results = generator.batch_generate(texts)

            # Verify results
            assert len(results) == 3
            for i, result in enumerate(results):
                assert isinstance(result, EmbeddingResult)
                assert result.text == texts[i]
                assert len(result.embedding) == 384  # Default size
                assert result.model_name == "all-MiniLM-L6-v2"

    def test_similarity_fallback(self):
        """Test similarity calculation with fallback."""
        # Create generator with ML disabled
        with mock.patch(
            "mcp_search_hub.query_routing.ml_models.embedding.USE_ML", False
        ):
            generator = EmbeddingGenerator()

            # Calculate similarity
            similarity = generator.similarity("text1", "text1")

            # Verify result (same text should have high similarity)
            assert 0.9 < similarity <= 1.0

            # Calculate similarity between different texts
            similarity = generator.similarity("text1", "completely different concept")

            # Verify result (should be consistent but not identical)
            assert 0.0 <= similarity < 1.0

    def test_batch_similarity_fallback(self):
        """Test batch similarity calculation with fallback."""
        # Create generator with ML disabled
        with mock.patch(
            "mcp_search_hub.query_routing.ml_models.embedding.USE_ML", False
        ):
            generator = EmbeddingGenerator()

            # Calculate batch similarities
            reference = "reference text"
            candidates = ["similar text", "different concept", "unrelated content"]
            results = generator.batch_similarity(reference, candidates)

            # Verify results
            assert len(results) == 3
            assert all(isinstance(item, tuple) and len(item) == 2 for item in results)
            assert all(
                isinstance(item[0], str) and isinstance(item[1], float)
                for item in results
            )

            # Verify sorting (highest similarity first)
            for i in range(len(results) - 1):
                assert results[i][1] >= results[i + 1][1]

    @pytest.mark.skipif(not USE_ML, reason="ML features disabled")
    @mock.patch(
        "mcp_search_hub.query_routing.ml_models.embedding.EmbeddingGenerator.model"
    )
    def test_generate_with_real_model(self, mock_model):
        """Test embedding generation with mock model."""
        # Create fake embedding
        fake_embedding = np.random.randn(384)
        mock_model.encode.return_value = fake_embedding

        # Create generator
        generator = EmbeddingGenerator()

        # Generate embedding
        result = generator.generate("test text")

        # Verify result
        assert isinstance(result, EmbeddingResult)
        assert result.text == "test text"
        assert len(result.embedding) == 384
        assert result.model_name == "all-MiniLM-L6-v2"

        # Verify model was called
        mock_model.encode.assert_called_once_with("test text")

    @pytest.mark.skipif(not USE_ML, reason="ML features disabled")
    @mock.patch(
        "mcp_search_hub.query_routing.ml_models.embedding.EmbeddingGenerator.model"
    )
    def test_batch_process(self, mock_model):
        """Test batch processing functionality."""
        # Create fake batch embeddings
        texts = ["text1", "text2", "text3"]
        fake_embeddings = np.random.randn(3, 384)
        mock_model.encode.return_value = fake_embeddings

        # Create generator
        generator = EmbeddingGenerator()

        # Process batch
        results = generator._process_batch(texts)

        # Verify results
        assert len(results) == 3
        for i, result in enumerate(results):
            assert isinstance(result, EmbeddingResult)
            assert result.text == texts[i]
            assert len(result.embedding) == 384

        # Verify model was called with correct parameters
        mock_model.encode.assert_called_once_with(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_tensor=True,
            normalize_embeddings=True,
        )

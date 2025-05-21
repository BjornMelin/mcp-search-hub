"""Tests for model trainer module."""

import os
import tempfile
from unittest import mock

import pytest
import numpy as np

from mcp_search_hub.query_routing.ml_models.model_trainer import (
    ModelTrainer,
    TrainingExample,
    TrainingConfig,
)
from mcp_search_hub.query_routing.ml_models.embedding import USE_ML


class TestModelTrainer:
    """Test model trainer functionality."""

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        trainer = ModelTrainer()
        assert trainer.base_model_name == "all-MiniLM-L6-v2"
        assert trainer.use_gpu is False
        assert "trained_models" in trainer.output_path

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = ModelTrainer(
                base_model_name="paraphrase-multilingual-MiniLM-L12-v2",
                output_path=tmpdir,
                use_gpu=True,
            )
            assert trainer.base_model_name == "paraphrase-multilingual-MiniLM-L12-v2"
            assert trainer.output_path == tmpdir
            assert trainer.use_gpu is True

    def test_create_training_dataset_empty(self):
        """Test creating training dataset with empty examples."""
        trainer = ModelTrainer()
        train_dataset, eval_dataset = trainer.create_training_dataset([])
        assert train_dataset == []
        assert eval_dataset == []

    def test_create_training_dataset_fallback(self):
        """Test creating training dataset with ML disabled."""
        # Mock ML features as disabled
        with mock.patch("mcp_search_hub.query_routing.ml_models.model_trainer.USE_ML", False):
            trainer = ModelTrainer()
            examples = [
                TrainingExample(text1="text1", text2="text2", score=0.8),
                TrainingExample(text1="text3", text2="text4", score=0.5),
            ]
            train_dataset, eval_dataset = trainer.create_training_dataset(examples)
            assert train_dataset == []
            assert eval_dataset == []

    def test_create_training_dataset_with_examples(self):
        """Test creating training dataset with examples."""
        trainer = ModelTrainer()
        
        # Create examples
        examples = [
            TrainingExample(text1="text1", text2="text2", score=0.8),
            TrainingExample(text1="text3", text2="text4", score=0.5),
            TrainingExample(text1="text5", text2="text6", score=0.9),
            TrainingExample(text1="text7", text2="text8", score=0.1),
            TrainingExample(text1="text9", text2="text10", score=-1.0),  # Negative pair
        ]
        
        # Mock np.random.shuffle to make test deterministic
        with mock.patch("numpy.random.shuffle"):
            train_dataset, eval_dataset = trainer.create_training_dataset(examples, train_test_split=0.6)
        
        # Verify results
        assert len(train_dataset) == 3  # 60% of 5 examples
        assert len(eval_dataset) == 2   # 40% of 5 examples
        
        # Verify format
        assert all("texts" in item for item in train_dataset)
        assert all("label" in item for item in train_dataset)
        assert all(isinstance(item["texts"], list) for item in train_dataset)
        assert all(len(item["texts"]) == 2 for item in train_dataset)
        assert all(isinstance(item["label"], float) for item in train_dataset)

    def test_train_model_fallback(self):
        """Test training model with ML disabled."""
        # Mock ML features as disabled
        with mock.patch("mcp_search_hub.query_routing.ml_models.model_trainer.USE_ML", False):
            trainer = ModelTrainer()
            examples = [
                TrainingExample(text1="text1", text2="text2", score=0.8),
                TrainingExample(text1="text3", text2="text4", score=0.5),
            ]
            result = trainer.train_model(examples)
            # Should return the base model name as fallback
            assert result == trainer.base_model_name

    def test_train_model_empty_examples(self):
        """Test training model with empty examples."""
        trainer = ModelTrainer()
        result = trainer.train_model([])
        # Should return the base model name
        assert result == trainer.base_model_name

    @pytest.mark.skipif(not USE_ML, reason="ML features disabled")
    def test_train_model_with_modules_missing(self):
        """Test training model with required modules missing."""
        # Mock _can_train attribute
        trainer = ModelTrainer()
        trainer._can_train = False
        
        examples = [
            TrainingExample(text1="text1", text2="text2", score=0.8),
            TrainingExample(text1="text3", text2="text4", score=0.5),
        ]
        
        result = trainer.train_model(examples)
        # Should return the base model name
        assert result == trainer.base_model_name

    @pytest.mark.skipif(not USE_ML, reason="ML features disabled")
    def test_create_training_examples_from_queries(self):
        """Test creating training examples from queries."""
        trainer = ModelTrainer()
        
        # Test data
        similar_queries = [
            ("how to make pasta", "how to cook spaghetti"),
            ("best smartphone 2025", "top mobile phones this year"),
        ]
        
        dissimilar_queries = [
            ("machine learning", "healthy recipes"),
            ("climate change", "fantasy novels"),
        ]
        
        labeled_scores = [
            ("python tutorial", "learn python programming", 0.9),
            ("hiking trails", "mountain hiking paths", 0.7),
        ]
        
        # Create examples
        examples = trainer.create_training_examples_from_queries(
            similar_queries=similar_queries,
            dissimilar_queries=dissimilar_queries,
            labeled_scores=labeled_scores,
        )
        
        # Verify results
        assert len(examples) == 6  # 2 + 2 + 2
        
        # Check similar queries (score 1.0)
        assert any(ex.text1 == "how to make pasta" and ex.text2 == "how to cook spaghetti" and ex.score == 1.0 for ex in examples)
        assert any(ex.text1 == "best smartphone 2025" and ex.text2 == "top mobile phones this year" and ex.score == 1.0 for ex in examples)
        
        # Check dissimilar queries (score 0.0)
        assert any(ex.text1 == "machine learning" and ex.text2 == "healthy recipes" and ex.score == 0.0 for ex in examples)
        assert any(ex.text1 == "climate change" and ex.text2 == "fantasy novels" and ex.score == 0.0 for ex in examples)
        
        # Check labeled scores
        assert any(ex.text1 == "python tutorial" and ex.text2 == "learn python programming" and ex.score == 0.9 for ex in examples)
        assert any(ex.text1 == "hiking trails" and ex.text2 == "mountain hiking paths" and ex.score == 0.7 for ex in examples)

    @pytest.mark.skipif(not USE_ML, reason="ML features disabled")
    def test_create_training_examples_with_none_params(self):
        """Test creating training examples with None parameters."""
        trainer = ModelTrainer()
        
        # Only similar queries
        examples1 = trainer.create_training_examples_from_queries(
            similar_queries=[("query1", "query2")],
            dissimilar_queries=None,
            labeled_scores=None,
        )
        assert len(examples1) == 1
        
        # Only dissimilar queries
        examples2 = trainer.create_training_examples_from_queries(
            similar_queries=None,
            dissimilar_queries=[("query3", "query4")],
            labeled_scores=None,
        )
        assert len(examples2) == 1
        
        # Only labeled scores
        examples3 = trainer.create_training_examples_from_queries(
            similar_queries=None,
            dissimilar_queries=None,
            labeled_scores=[("query5", "query6", 0.5)],
        )
        assert len(examples3) == 1
        
        # All None
        examples4 = trainer.create_training_examples_from_queries(
            similar_queries=None,
            dissimilar_queries=None,
            labeled_scores=None,
        )
        assert len(examples4) == 0
#!/usr/bin/env python3
"""Example script for training and updating embedding models."""

import logging
import sys
from pathlib import Path

# Add the parent directory to the path for imports
sys.path.append(str(Path(__file__).parent.parent))

from mcp_search_hub.query_routing.ml_models import (
    ModelTrainer,
    TrainingConfig,
    TrainingExample,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("model_training_example")


def main():
    """Run the model training example."""
    logger.info("Starting model training example")

    # 1. Create a model trainer
    trainer = ModelTrainer(
        base_model_name="all-MiniLM-L6-v2",
        output_path="./trained_models",
        use_gpu=True,  # Set to False if no GPU is available
    )

    # 2. Create training examples
    # Example 1: Create examples from similar/dissimilar query pairs
    similar_queries = [
        ("how to make pasta", "how to cook spaghetti"),
        ("best smartphone 2025", "top mobile phones this year"),
        ("climate change effects", "impact of global warming"),
        ("learn python programming", "python tutorials for beginners"),
        ("stock market analysis", "how to analyze stocks"),
    ]

    dissimilar_queries = [
        ("how to make pasta", "buy a new car"),
        ("best smartphone 2025", "ancient roman history"),
        ("climate change effects", "best chocolate cake recipe"),
        ("learn python programming", "tropical vacation destinations"),
        ("stock market analysis", "how to train your dog"),
    ]

    # Example 2: Create examples with specific similarity scores
    labeled_examples = [
        ("machine learning tutorial", "AI course online", 0.85),
        ("covid vaccination", "covid vaccine side effects", 0.7),
        ("healthy breakfast ideas", "nutritious morning meals", 0.9),
        ("affordable laptops", "budget computers", 0.8),
        ("hybrid cars", "electric vehicles", 0.6),
    ]

    # Combine examples
    examples = trainer.create_training_examples_from_queries(
        similar_queries=similar_queries,
        dissimilar_queries=dissimilar_queries,
        labeled_scores=labeled_examples,
    )

    logger.info(f"Created {len(examples)} training examples")

    # 3. Configure training
    config = TrainingConfig(
        batch_size=16,
        epochs=3,
        warmup_steps=100,
        evaluation_steps=100,
        learning_rate=2e-5,
        use_amp=True,  # Automatic mixed precision for faster training
        save_best_model=True,
        output_path="./trained_models/search_queries_model",
    )

    # 4. Train the model
    model_path = trainer.train_model(
        examples, config, model_name="search-queries-model"
    )
    logger.info(f"Model trained and saved to {model_path}")

    # 5. Evaluate the model
    # Create test examples (different from training data)
    test_examples = [
        TrainingExample(
            text1="how to bake bread", text2="bread baking tutorial", score=0.95
        ),
        TrainingExample(
            text1="renewable energy", text2="solar and wind power", score=0.85
        ),
        TrainingExample(
            text1="learn guitar", text2="guitar lessons for beginners", score=0.9
        ),
        TrainingExample(
            text1="digital marketing", text2="online advertising strategies", score=0.8
        ),
        TrainingExample(text1="healthy recipes", text2="quantum physics", score=0.1),
    ]

    metrics = trainer.evaluate_model(model_path, test_examples)
    logger.info(f"Model evaluation results: {metrics}")

    # 6. Export the model to ONNX format for faster inference
    exported_path = trainer.export_model(
        model_path, export_format="onnx", quantize=True
    )
    logger.info(f"Model exported to {exported_path}")

    # 7. How to use the trained model with EmbeddingGenerator
    logger.info("\nTo use this model with EmbeddingGenerator:")
    logger.info(
        "from mcp_search_hub.query_routing.ml_models import EmbeddingGenerator\n"
        f"generator = EmbeddingGenerator(model_name='{model_path}', backend='onnx')\n"
        "# For ONNX exported model:\n"
        f"# generator = EmbeddingGenerator(model_name='{exported_path}', backend='onnx')\n"
        "embedding = generator.generate('your query here')\n"
    )


if __name__ == "__main__":
    main()

"""Model training and updating using sentence-transformers v4."""

import logging
import os
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from .embedding import USE_ML

logger = logging.getLogger(__name__)


class TrainingExample(BaseModel):
    """A single training example for model updating."""

    text1: str = Field(..., description="First text in the pair")
    text2: str = Field(..., description="Second text in the pair")
    score: float = Field(
        ..., description="Similarity score (0-1) or -1 for non-similar pairs"
    )


class TrainingConfig(BaseModel):
    """Configuration for model training."""

    batch_size: int = Field(16, description="Training batch size")
    epochs: int = Field(3, description="Number of training epochs")
    warmup_steps: int = Field(
        100, description="Warmup steps for learning rate scheduler"
    )
    evaluation_steps: int = Field(
        0, description="Steps between evaluations (0 to disable)"
    )
    use_amp: bool = Field(False, description="Whether to use automatic mixed precision")
    learning_rate: float = Field(2e-5, description="Learning rate for training")
    weight_decay: float = Field(0.01, description="Weight decay for optimizer")
    max_grad_norm: float = Field(1.0, description="Maximum gradient norm for clipping")
    save_best_model: bool = Field(True, description="Whether to save the best model")
    output_path: str | None = Field(None, description="Where to save the model")


class ModelTrainer:
    """Manages training and updating of embedding models."""

    def __init__(
        self,
        base_model_name: str = "all-MiniLM-L6-v2",
        output_path: str | None = None,
        use_gpu: bool = False,
    ):
        """Initialize the model trainer.

        Args:
            base_model_name: Name of the base model to fine-tune
            output_path: Where to save trained models (defaults to ./trained_models)
            use_gpu: Whether to use GPU for training
        """
        self.base_model_name = base_model_name
        self.output_path = output_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "trained_models"
        )
        self.use_gpu = use_gpu

        # Ensure output directory exists
        Path(self.output_path).mkdir(parents=True, exist_ok=True)

        # Check if ML features are enabled and required packages are available
        self._can_train = USE_ML
        if USE_ML:
            try:
                import torch

                # Import just to check availability
                import sentence_transformers

                self._can_train = True
                # Set device
                self.device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
                logger.info(f"Model trainer will use device: {self.device}")
            except ImportError:
                logger.warning(
                    "Required packages not available. Model training disabled."
                )
                self._can_train = False

    def create_training_dataset(
        self, examples: list[TrainingExample], train_test_split: float = 0.8
    ) -> tuple[list[dict], list[dict]]:
        """Create a dataset for sentence transformer training.

        Args:
            examples: List of training examples
            train_test_split: Proportion of data to use for training (rest for evaluation)

        Returns:
            Tuple of (train_dataset, eval_dataset)
        """
        if not self._can_train:
            logger.warning("ML features disabled. Cannot create training dataset.")
            return [], []

        # Convert examples to sentence transformer format
        dataset = []
        for example in examples:
            # For cosine similarity scores
            if example.score >= 0:
                dataset.append(
                    {
                        "texts": [example.text1, example.text2],
                        "label": float(example.score),
                    }
                )
            # For contrastive pairs (similarity=1 for positive, 0 for negative)
            else:
                dataset.append(
                    {
                        "texts": [example.text1, example.text2],
                        "label": 0.0,  # Negative pair
                    }
                )

        # Shuffle dataset
        np.random.shuffle(dataset)

        # Split into training and evaluation
        train_idx = int(len(dataset) * train_test_split)
        train_dataset = dataset[:train_idx]
        eval_dataset = dataset[train_idx:]

        return train_dataset, eval_dataset

    def train_model(
        self,
        examples: list[TrainingExample],
        config: TrainingConfig | None = None,
        model_name: str | None = None,
    ) -> str:
        """Train or fine-tune a sentence transformer model.

        Args:
            examples: List of training examples
            config: Training configuration
            model_name: Custom name for the trained model (default: fine-tuned-{base_model})

        Returns:
            Path to the trained model
        """
        if not self._can_train or not examples:
            logger.warning(
                "Cannot train model: ML features disabled or no training examples provided."
            )
            return self.base_model_name

        # Use default config if none provided
        config = config or TrainingConfig()

        try:
            from sentence_transformers import InputExample, SentenceTransformer, losses
            from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
            from torch.utils.data import DataLoader

            # Create unique model name if not provided
            if not model_name:
                import time

                timestamp = int(time.time())
                model_name = (
                    f"fine-tuned-{self.base_model_name.split('/')[-1]}-{timestamp}"
                )

            # Set output path
            output_path = config.output_path or os.path.join(
                self.output_path, model_name
            )

            # Load base model
            model = SentenceTransformer(self.base_model_name, device=self.device)

            # Create training examples in the format expected by sentence-transformers
            train_examples = []
            for ex in examples:
                train_examples.append(
                    InputExample(texts=[ex.text1, ex.text2], label=ex.score)
                )

            # Create data loader
            train_dataloader = DataLoader(
                train_examples, shuffle=True, batch_size=config.batch_size
            )

            # Select loss function based on the type of training data
            # Check if we have regression scores (0-1) or binary (similar/dissimilar) pairs
            has_scores = any(ex.score > 0 and ex.score < 1 for ex in examples)

            if has_scores:
                # Regression loss for similarity scores
                train_loss = losses.CosineSimilarityLoss(model)
                logger.info("Using CosineSimilarityLoss for regression training")
            else:
                # Contrastive loss for binary similar/dissimilar pairs
                train_loss = losses.ContrastiveLoss(model)
                logger.info("Using ContrastiveLoss for binary similar/dissimilar pairs")

            # Create evaluator if we have evaluation examples
            evaluator = None
            if config.evaluation_steps > 0:
                # Create a separate evaluation set (20% of examples)
                from sklearn.model_selection import train_test_split as sklearn_split

                train_examples, eval_examples = sklearn_split(
                    train_examples, test_size=0.2
                )

                # Recreate data loader with reduced training set
                train_dataloader = DataLoader(
                    train_examples, shuffle=True, batch_size=config.batch_size
                )

                # Create evaluator
                evaluator = EmbeddingSimilarityEvaluator.from_input_examples(
                    eval_examples, name="eval"
                )

            # Train the model
            logger.info(
                f"Training model with {len(train_examples)} examples for {config.epochs} epochs"
            )
            model.fit(
                train_objectives=[(train_dataloader, train_loss)],
                epochs=config.epochs,
                warmup_steps=config.warmup_steps,
                evaluation_steps=config.evaluation_steps,
                evaluator=evaluator,
                output_path=output_path,
                save_best_model=config.save_best_model,
                optimizer_params={
                    "lr": config.learning_rate,
                    "weight_decay": config.weight_decay,
                },
                use_amp=config.use_amp,
                max_grad_norm=config.max_grad_norm,
                show_progress_bar=True,
            )

            logger.info(f"Model trained and saved to {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error during model training: {e}")
            return self.base_model_name

    def evaluate_model(
        self, model_path: str, examples: list[TrainingExample]
    ) -> dict[str, float]:
        """Evaluate a trained model on test examples.

        Args:
            model_path: Path to the model to evaluate
            examples: List of test examples

        Returns:
            Dictionary with evaluation metrics
        """
        if not self._can_train or not examples:
            logger.warning(
                "Cannot evaluate model: ML features disabled or no examples provided."
            )
            return {"error": "Evaluation not possible"}

        try:
            from sentence_transformers import InputExample, SentenceTransformer
            from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator

            # Load model
            model = SentenceTransformer(model_path, device=self.device)

            # Create evaluation examples
            eval_examples = [
                InputExample(texts=[ex.text1, ex.text2], label=ex.score)
                for ex in examples
            ]

            # Create evaluator
            evaluator = EmbeddingSimilarityEvaluator.from_input_examples(
                eval_examples, name="test-eval"
            )

            # Run evaluation
            result = evaluator(model)

            # Return metrics with descriptive names
            return {
                "spearman_correlation": result[0],
                "pearson_correlation": result[1],
            }

        except Exception as e:
            logger.error(f"Error during model evaluation: {e}")
            return {"error": str(e)}

    def export_model(
        self, model_path: str, export_format: str = "onnx", quantize: bool = False
    ) -> str:
        """Export a trained model to a specified format.

        Args:
            model_path: Path to the model to export
            export_format: Format to export to ('onnx' or 'openvino')
            quantize: Whether to quantize the model during export

        Returns:
            Path to the exported model
        """
        if not self._can_train:
            logger.warning("ML features disabled. Cannot export model.")
            return model_path

        try:
            import os

            from sentence_transformers import SentenceTransformer

            # Load model
            model = SentenceTransformer(model_path, device=self.device)

            # Create export directory
            export_dir = os.path.join(
                os.path.dirname(model_path),
                f"{os.path.basename(model_path)}-{export_format}",
            )
            os.makedirs(export_dir, exist_ok=True)

            if export_format.lower() == "onnx":
                # Export to ONNX format
                from sentence_transformers.export import export_to_onnx

                logger.info(f"Exporting model to ONNX format: {export_dir}")
                export_to_onnx(
                    model,
                    export_dir,
                    quantize=quantize,
                    use_dynamic_axes=True,
                )

            elif export_format.lower() == "openvino":
                # Export to OpenVINO format (requires openvino package)
                # First export to ONNX, then convert to OpenVINO
                from sentence_transformers.export import export_to_onnx

                # Create temporary ONNX directory
                onnx_dir = os.path.join(
                    os.path.dirname(model_path),
                    f"{os.path.basename(model_path)}-onnx-temp",
                )
                os.makedirs(onnx_dir, exist_ok=True)

                # Export to ONNX first
                logger.info(f"Exporting model to temporary ONNX format: {onnx_dir}")
                export_to_onnx(
                    model,
                    onnx_dir,
                    quantize=False,  # Don't quantize yet
                    use_dynamic_axes=True,
                )

                # Convert to OpenVINO
                try:
                    from openvino.tools import mo

                    logger.info(f"Converting ONNX to OpenVINO format: {export_dir}")

                    # Find main model file
                    model_files = [
                        f for f in os.listdir(onnx_dir) if f.endswith(".onnx")
                    ]

                    for model_file in model_files:
                        onnx_path = os.path.join(onnx_dir, model_file)
                        ov_path = os.path.join(
                            export_dir, model_file.replace(".onnx", ".xml")
                        )

                        # Convert to OpenVINO IR
                        ov_model = mo.convert_model(onnx_path)

                        # Quantize if requested
                        if quantize:
                            from openvino.runtime import serialize
                            from openvino.tools import pot

                            # Configure quantization
                            compression_config = {
                                "name": "DefaultQuantization",
                                "params": {
                                    "preset": "mixed",
                                    "target_device": "CPU",
                                },
                            }

                            # Quantize the model
                            ov_model = pot.quantize(ov_model, compression_config)

                        # Save the model
                        serialize(ov_model, ov_path)

                        logger.info(f"Saved OpenVINO model to {ov_path}")

                    # Clean up temporary ONNX directory
                    import shutil

                    shutil.rmtree(onnx_dir)

                except ImportError:
                    logger.warning(
                        "OpenVINO packages not installed. Falling back to ONNX export."
                    )
                    # Fall back to ONNX export
                    export_dir = os.path.join(
                        os.path.dirname(model_path),
                        f"{os.path.basename(model_path)}-onnx",
                    )
                    export_to_onnx(
                        model,
                        export_dir,
                        quantize=quantize,
                        use_dynamic_axes=True,
                    )
            else:
                logger.warning(
                    f"Unsupported export format: {export_format}. Using original model."
                )
                return model_path

            return export_dir

        except Exception as e:
            logger.error(f"Error during model export: {e}")
            return model_path

    def create_training_examples_from_queries(
        self,
        similar_queries: list[tuple[str, str]],
        dissimilar_queries: list[tuple[str, str]] | None = None,
        labeled_scores: list[tuple[str, str, float]] | None = None,
    ) -> list[TrainingExample]:
        """Create training examples from similar and dissimilar query pairs.

        Args:
            similar_queries: List of (query1, query2) tuples that are similar
            dissimilar_queries: List of (query1, query2) tuples that are dissimilar
            labeled_scores: List of (query1, query2, score) tuples with specific scores

        Returns:
            List of TrainingExample objects
        """
        examples = []

        # Add similar query pairs (score 1.0)
        for q1, q2 in similar_queries or []:
            examples.append(TrainingExample(text1=q1, text2=q2, score=1.0))

        # Add dissimilar query pairs (score 0.0)
        for q1, q2 in dissimilar_queries or []:
            examples.append(TrainingExample(text1=q1, text2=q2, score=0.0))

        # Add labeled examples with specific scores
        for q1, q2, score in labeled_scores or []:
            examples.append(TrainingExample(text1=q1, text2=q2, score=float(score)))

        return examples

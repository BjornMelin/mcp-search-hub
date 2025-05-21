"""ML-based content classifier for query categorization."""

import logging
import os
import pickle

import numpy as np
from pydantic import BaseModel, Field

from .embedding import USE_ML, EmbeddingGenerator

logger = logging.getLogger(__name__)

# Define content types
CONTENT_TYPES = ["academic", "news", "technical", "business", "web_content", "general"]


class ClassificationResult(BaseModel):
    """Result of content classification."""

    content_type: str = Field(..., description="The detected content type")
    confidence: float = Field(..., description="Confidence score (0.0-1.0)")
    probabilities: dict[str, float] = Field(
        ..., description="Probability scores for each content type"
    )
    method_used: str = Field(
        ..., description="Classification method used (ml, rule_based, or fallback)"
    )


class ContentClassifier:
    """ML-based classifier for content type detection."""

    def __init__(self, model_dir: str | None = None):
        """Initialize the content classifier.

        Args:
            model_dir: Directory containing trained models (optional)
        """
        self.embedding_generator = EmbeddingGenerator(
            model_name="all-MiniLM-L6-v2", cache_size=1000
        )
        self.model_dir = model_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "models"
        )
        self._classifier = None
        self._vectorizer = None
        self._fallback_analyzer = None

    @property
    def classifier(self):
        """Lazily load the classifier model."""
        if self._classifier is None and USE_ML:
            try:
                # Try to load the sklearn model
                from sklearn.ensemble import RandomForestClassifier

                model_path = os.path.join(self.model_dir, "content_classifier.pkl")

                if os.path.exists(model_path):
                    with open(model_path, "rb") as f:
                        self._classifier = pickle.load(f)
                    logger.info("Loaded content classifier from file")
                else:
                    # Create a new model if no saved model exists
                    self._classifier = RandomForestClassifier(
                        n_estimators=100, random_state=42
                    )
                    logger.info("Created new content classifier model")

                    # Ensure the model directory exists
                    os.makedirs(self.model_dir, exist_ok=True)

                    # For initial model, we'll train on examples from our keyword system
                    # This is a simplified training that would be improved with real data
                    self._train_initial_model()
            except ImportError:
                logger.warning(
                    "scikit-learn not available. Content classification will use fallback."
                )
            except Exception as e:
                logger.error(f"Error loading content classifier model: {e}")

        return self._classifier

    def _train_initial_model(self):
        """Train an initial model based on examples from the keyword system."""
        # Generate synthetic training data based on our keyword system
        examples = self._generate_synthetic_examples()

        if not examples:
            logger.warning("No synthetic examples available for training")
            return

        texts = [example[0] for example in examples]
        labels = [example[1] for example in examples]

        # Get embeddings for all examples
        embeddings = [
            np.array(self.embedding_generator.generate(text).embedding)
            for text in texts
        ]

        # Convert to numpy array
        X = np.vstack(embeddings)
        y = np.array(labels)

        # Train the model
        self.classifier.fit(X, y)

        # Save the model
        with open(os.path.join(self.model_dir, "content_classifier.pkl"), "wb") as f:
            pickle.dump(self.classifier, f)

        logger.info(f"Trained initial content classifier on {len(examples)} examples")

    def _generate_synthetic_examples(self) -> list[tuple[str, str]]:
        """Generate synthetic examples based on our keyword system."""
        # Synthetic examples format: (text, content_type)
        examples = []

        # Academic examples
        examples.extend(
            [
                ("research paper on climate change", "academic"),
                ("recent studies in quantum computing", "academic"),
                ("peer-reviewed journal articles about machine learning", "academic"),
                ("scientific papers on vaccine efficacy", "academic"),
                ("dissertation on renewable energy technology", "academic"),
                ("academic research on artificial intelligence ethics", "academic"),
                ("scientific publications about black holes", "academic"),
                ("literature review on cognitive psychology", "academic"),
                ("research methodology in social sciences", "academic"),
                ("academic papers on blockchain technology", "academic"),
            ]
        )

        # News examples
        examples.extend(
            [
                ("latest news about tech industry", "news"),
                ("breaking news on the election results", "news"),
                ("current events in the middle east", "news"),
                ("today's headlines about climate policy", "news"),
                ("recent developments in the stock market", "news"),
                ("latest updates on the global pandemic", "news"),
                ("breaking stories about cryptocurrency regulation", "news"),
                ("news coverage of the Olympic games", "news"),
                ("this week's economic news summary", "news"),
                ("media reports on corporate mergers", "news"),
            ]
        )

        # Technical examples
        examples.extend(
            [
                ("python programming tutorial", "technical"),
                ("how to implement a REST API", "technical"),
                ("debugging memory leaks in C++", "technical"),
                ("setup kubernetes on AWS", "technical"),
                ("javascript framework comparison", "technical"),
                ("configuring nginx as a reverse proxy", "technical"),
                ("github actions workflow tutorial", "technical"),
                ("optimizing database query performance", "technical"),
                ("java design patterns examples", "technical"),
                ("tensorflow installation guide", "technical"),
            ]
        )

        # Business examples
        examples.extend(
            [
                ("quarterly earnings report for Apple", "business"),
                ("startup funding rounds in 2025", "business"),
                ("market analysis of electric vehicle industry", "business"),
                ("business model canvas template", "business"),
                ("competitor analysis framework", "business"),
                ("venture capital trends in biotech", "business"),
                ("company valuation methods comparison", "business"),
                ("CEO profiles of Fortune 500 companies", "business"),
                ("stock market performance this year", "business"),
                ("supply chain optimization strategies", "business"),
            ]
        )

        # Web content examples
        examples.extend(
            [
                ("extract content from wikipedia page", "web_content"),
                ("scrape product data from amazon", "web_content"),
                ("get text from CNN website", "web_content"),
                ("extract tables from this webpage", "web_content"),
                ("download all images from site", "web_content"),
                ("scrape job listings from linkedin", "web_content"),
                ("extract article content from medium", "web_content"),
                ("scrape reviews from yelp", "web_content"),
                ("extract pricing data from e-commerce site", "web_content"),
                ("get content behind paywall", "web_content"),
            ]
        )

        # General examples
        examples.extend(
            [
                ("information about healthy diets", "general"),
                ("where is the Eiffel Tower located", "general"),
                ("how to tie a tie", "general"),
                ("best movies of 2024", "general"),
                ("history of the internet", "general"),
                ("what does GDP stand for", "general"),
                ("who invented the telephone", "general"),
                ("explanation of photosynthesis", "general"),
                ("top tourist destinations in Europe", "general"),
                ("how does the immune system work", "general"),
            ]
        )

        return examples

    @property
    def fallback_analyzer(self):
        """Get the rule-based analyzer for fallback."""
        if self._fallback_analyzer is None:
            from ..analyzer import QueryAnalyzer

            self._fallback_analyzer = QueryAnalyzer()
        return self._fallback_analyzer

    def classify(self, text: str) -> ClassificationResult:
        """Classify the content type of a query.

        Args:
            text: The query text to classify

        Returns:
            ClassificationResult with content type and confidence
        """
        if self.classifier is None or not USE_ML:
            # Fallback to rule-based analyzer
            features = self.fallback_analyzer._detect_content_type(text)

            # Create a simple probability distribution with high confidence for the detected type
            probabilities = dict.fromkeys(CONTENT_TYPES, 0.1)
            probabilities[features] = 0.9

            return ClassificationResult(
                content_type=features,
                confidence=0.9,
                probabilities=probabilities,
                method_used="rule_based",
            )

        try:
            # Generate embedding for the text
            embedding = np.array(self.embedding_generator.generate(text).embedding)

            # Reshape for sklearn (expects 2D array)
            embedding = embedding.reshape(1, -1)

            # Get probabilities for each class
            probas = self.classifier.predict_proba(embedding)[0]

            # Map to class names
            classes = self.classifier.classes_
            probabilities = {
                cls: float(proba) for cls, proba in zip(classes, probas, strict=False)
            }

            # Get predicted class and confidence
            predicted_idx = np.argmax(probas)
            content_type = classes[predicted_idx]
            confidence = float(probas[predicted_idx])

            # If confidence is low, fall back to rule-based
            if confidence < 0.6:
                rule_based_type = self.fallback_analyzer._detect_content_type(text)

                # If ML and rule-based agree, boost confidence
                if content_type == rule_based_type:
                    confidence = min(confidence + 0.2, 1.0)
                    return ClassificationResult(
                        content_type=content_type,
                        confidence=confidence,
                        probabilities=probabilities,
                        method_used="ml_confirmed",
                    )
                # Otherwise use rule-based with its probabilities
                rule_probabilities = dict.fromkeys(CONTENT_TYPES, 0.1)
                rule_probabilities[rule_based_type] = 0.9

                return ClassificationResult(
                    content_type=rule_based_type,
                    confidence=0.9,
                    probabilities=rule_probabilities,
                    method_used="rule_based_fallback",
                )

            return ClassificationResult(
                content_type=content_type,
                confidence=confidence,
                probabilities=probabilities,
                method_used="ml",
            )
        except Exception as e:
            logger.error(f"Error during ML content classification: {e}")
            # Fall back to rule-based
            rule_based_type = self.fallback_analyzer._detect_content_type(text)

            # Simple probability distribution for rule-based
            probabilities = dict.fromkeys(CONTENT_TYPES, 0.1)
            probabilities[rule_based_type] = 0.9

            return ClassificationResult(
                content_type=rule_based_type,
                confidence=0.9,
                probabilities=probabilities,
                method_used="rule_based_error_fallback",
            )

    def update_model(self, texts: list[str], labels: list[str]) -> bool:
        """Update the model with new labeled examples.

        Args:
            texts: List of query texts
            labels: List of corresponding content type labels

        Returns:
            True if model was updated successfully
        """
        if not self.classifier or not USE_ML:
            logger.warning(
                "Cannot update model: ML features disabled or model not available"
            )
            return False

        try:
            # Get embeddings for all texts
            embeddings = [
                np.array(self.embedding_generator.generate(text).embedding)
                for text in texts
            ]

            # Convert to numpy array
            X = np.vstack(embeddings)
            y = np.array(labels)

            # Update the model
            self.classifier.fit(X, y)

            # Save the updated model
            os.makedirs(self.model_dir, exist_ok=True)
            with open(
                os.path.join(self.model_dir, "content_classifier.pkl"), "wb"
            ) as f:
                pickle.dump(self.classifier, f)

            logger.info(f"Updated content classifier with {len(texts)} new examples")
            return True
        except Exception as e:
            logger.error(f"Error updating content classifier: {e}")
            return False

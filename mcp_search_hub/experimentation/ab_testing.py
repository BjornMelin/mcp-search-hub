"""A/B testing framework for evaluating different search configurations."""

import hashlib
import json
import logging
import os
import random
import time
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from ..models.query import SearchQuery
from ..models.results import SearchResponse

logger = logging.getLogger(__name__)


class ExperimentVariant(BaseModel):
    """A variant in an A/B test experiment."""

    id: str = Field(..., description="Unique identifier for this variant")
    name: str = Field(..., description="Human-readable name for this variant")
    weight: float = Field(
        1.0, description="Relative weight for random assignment (0.0-1.0)"
    )
    config: dict[str, Any] = Field(..., description="Configuration for this variant")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata for this variant"
    )


class ExperimentResult(BaseModel):
    """Result of an experiment variant execution."""

    variant_id: str = Field(..., description="ID of the variant that was tested")
    query: str = Field(..., description="The search query text")
    response: SearchResponse | None = Field(
        None, description="The search response from the variant"
    )
    metrics: dict[str, float] = Field(
        default_factory=dict, description="Performance metrics for this variant"
    )
    error: str | None = Field(None, description="Error message if the variant failed")
    latency_ms: float = Field(..., description="Execution time in milliseconds")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(), description="When the test was run"
    )


class Experiment(BaseModel):
    """An A/B test experiment definition."""

    id: str = Field(..., description="Unique identifier for this experiment")
    name: str = Field(..., description="Human-readable name for this experiment")
    description: str = Field("", description="Description of what is being tested")
    variants: list[ExperimentVariant] = Field(..., description="Variants to test")
    active: bool = Field(True, description="Whether this experiment is active")
    start_date: datetime | None = Field(
        None, description="When this experiment started"
    )
    end_date: datetime | None = Field(None, description="When this experiment will end")
    traffic_percentage: float = Field(
        100.0, description="Percentage of traffic to include in the test (0-100)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata for this experiment"
    )


class Assignment(str, Enum):
    """Traffic assignment strategies for experiments."""

    RANDOM = "random"  # Random assignment
    DETERMINISTIC = "deterministic"  # Based on query hash
    USER_ID = "user_id"  # Based on user ID


class ABTestingManager:
    """Manages A/B testing of search configurations."""

    def __init__(
        self,
        storage_dir: str | None = None,
        assignment_strategy: Assignment = Assignment.DETERMINISTIC,
        enable_shadow_testing: bool = True,
    ):
        """Initialize the A/B testing manager.

        Args:
            storage_dir: Directory to store experiment data
            assignment_strategy: Strategy for assigning traffic to variants
            enable_shadow_testing: Whether to run shadow tests
        """
        self.storage_dir = storage_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "experiments"
        )
        self.assignment_strategy = assignment_strategy
        self.enable_shadow_testing = enable_shadow_testing
        self.experiments: dict[str, Experiment] = {}
        self.results: dict[str, list[ExperimentResult]] = {}
        self._initialize()

    def _initialize(self):
        """Initialize the testing framework."""
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load_experiments()

    def _load_experiments(self):
        """Load experiment definitions from storage."""
        experiment_path = os.path.join(self.storage_dir, "experiments")
        os.makedirs(experiment_path, exist_ok=True)

        # Load experiment files
        for filename in os.listdir(experiment_path):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(experiment_path, filename)) as f:
                        experiment_data = json.load(f)
                        experiment = Experiment(**experiment_data)
                        self.experiments[experiment.id] = experiment
                        logger.info(f"Loaded experiment: {experiment.id}")
                except Exception as e:
                    logger.error(f"Error loading experiment {filename}: {e}")

    def _save_experiment(self, experiment: Experiment):
        """Save experiment definition to storage."""
        experiment_path = os.path.join(self.storage_dir, "experiments")
        os.makedirs(experiment_path, exist_ok=True)

        try:
            with open(os.path.join(experiment_path, f"{experiment.id}.json"), "w") as f:
                f.write(experiment.model_dump_json(indent=2))
            logger.info(f"Saved experiment: {experiment.id}")
        except Exception as e:
            logger.error(f"Error saving experiment {experiment.id}: {e}")

    def _save_result(self, experiment_id: str, result: ExperimentResult):
        """Save experiment result to storage."""
        results_path = os.path.join(self.storage_dir, "results", experiment_id)
        os.makedirs(results_path, exist_ok=True)

        # Generate a unique filename based on timestamp
        filename = f"{int(time.time())}_{result.variant_id}.json"

        try:
            with open(os.path.join(results_path, filename), "w") as f:
                # Exclude the response to save space
                result_copy = result.model_copy(deep=True)
                result_copy.response = None
                f.write(result_copy.model_dump_json(indent=2))

            # Add to in-memory results
            if experiment_id not in self.results:
                self.results[experiment_id] = []
            self.results[experiment_id].append(result)
        except Exception as e:
            logger.error(f"Error saving result for experiment {experiment_id}: {e}")

    def create_experiment(
        self,
        name: str,
        variants: list[dict[str, Any]],
        description: str = "",
        traffic_percentage: float = 100.0,
        metadata: dict[str, Any] | None = None,
    ) -> Experiment:
        """Create a new A/B test experiment.

        Args:
            name: Human-readable name for the experiment
            variants: List of variant configurations
            description: Description of what is being tested
            traffic_percentage: Percentage of traffic to include (0-100)
            metadata: Additional metadata for the experiment

        Returns:
            The created experiment
        """
        # Generate a unique ID based on name and time
        experiment_id = (
            f"exp_{hashlib.md5(f'{name}_{time.time()}'.encode()).hexdigest()[:8]}"
        )

        # Create the experiment variants
        experiment_variants = []
        for i, variant_data in enumerate(variants):
            variant_id = variant_data.get("id", f"variant_{i}")
            variant_name = variant_data.get("name", f"Variant {i}")
            variant_weight = variant_data.get("weight", 1.0)
            variant_config = variant_data.get("config", {})
            variant_metadata = variant_data.get("metadata", {})

            experiment_variants.append(
                ExperimentVariant(
                    id=variant_id,
                    name=variant_name,
                    weight=variant_weight,
                    config=variant_config,
                    metadata=variant_metadata,
                )
            )

        # Create the experiment
        experiment = Experiment(
            id=experiment_id,
            name=name,
            description=description,
            variants=experiment_variants,
            active=True,
            start_date=datetime.now(),
            end_date=None,
            traffic_percentage=traffic_percentage,
            metadata=metadata or {},
        )

        # Save the experiment
        self.experiments[experiment_id] = experiment
        self._save_experiment(experiment)

        return experiment

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        """Get experiment by ID.

        Args:
            experiment_id: ID of the experiment to get

        Returns:
            The experiment or None if not found
        """
        return self.experiments.get(experiment_id)

    def list_experiments(self, active_only: bool = False) -> list[Experiment]:
        """List all experiments.

        Args:
            active_only: Whether to include only active experiments

        Returns:
            List of experiments
        """
        if active_only:
            return [exp for exp in self.experiments.values() if exp.active]
        return list(self.experiments.values())

    def activate_experiment(self, experiment_id: str) -> bool:
        """Activate an experiment.

        Args:
            experiment_id: ID of the experiment to activate

        Returns:
            True if successful, False otherwise
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            return False

        experiment.active = True
        self._save_experiment(experiment)
        return True

    def deactivate_experiment(self, experiment_id: str) -> bool:
        """Deactivate an experiment.

        Args:
            experiment_id: ID of the experiment to deactivate

        Returns:
            True if successful, False otherwise
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            return False

        experiment.active = False
        experiment.end_date = datetime.now()
        self._save_experiment(experiment)
        return True

    def assign_variant(
        self,
        experiment: Experiment,
        query: SearchQuery,
        user_id: str | None = None,
    ) -> ExperimentVariant:
        """Assign a variant based on the assignment strategy.

        Args:
            experiment: The experiment to assign a variant for
            query: The search query
            user_id: Optional user ID for user-based assignment

        Returns:
            The assigned variant
        """
        if self.assignment_strategy == Assignment.RANDOM:
            # Random assignment based on variant weights
            weights = [v.weight for v in experiment.variants]
            # Normalize weights
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]
            return random.choices(experiment.variants, weights=normalized_weights)[0]

        if self.assignment_strategy == Assignment.USER_ID and user_id:
            # Deterministic assignment based on user ID
            hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
            # Normalize to 0-1 range
            normalized_val = hash_val / (2**128)

            # Map to a variant based on weights
            cumulative_weight = 0
            total_weight = sum(v.weight for v in experiment.variants)
            for variant in experiment.variants:
                cumulative_weight += variant.weight / total_weight
                if normalized_val < cumulative_weight:
                    return variant

            # Fallback to last variant
            return experiment.variants[-1]

        # Default to deterministic based on query
        # Deterministic assignment based on query
        query_hash = hashlib.md5(query.query.encode()).hexdigest()
        hash_val = int(query_hash, 16)
        # Normalize to 0-1 range
        normalized_val = hash_val / (2**128)

        # Map to a variant based on weights
        cumulative_weight = 0
        total_weight = sum(v.weight for v in experiment.variants)
        for variant in experiment.variants:
            cumulative_weight += variant.weight / total_weight
            if normalized_val < cumulative_weight:
                return variant

        # Fallback to last variant
        return experiment.variants[-1]

    def should_include_in_experiment(
        self, experiment: Experiment, query: SearchQuery
    ) -> bool:
        """Determine if a query should be included in an experiment.

        Args:
            experiment: The experiment to check
            query: The search query

        Returns:
            True if the query should be included in the experiment
        """
        # Check if experiment is active
        if not experiment.active:
            return False

        # Check date range
        now = datetime.now()
        if experiment.start_date and now < experiment.start_date:
            return False
        if experiment.end_date and now > experiment.end_date:
            return False

        # Apply traffic percentage
        if experiment.traffic_percentage < 100.0:
            # Generate a consistent hash for the query
            query_hash = hashlib.md5(query.query.encode()).hexdigest()
            hash_val = int(query_hash, 16)
            # Normalize to 0-100 range
            normalized_val = (hash_val % 100) + (hash_val % 100) / 100

            # Check if within traffic percentage
            return normalized_val < experiment.traffic_percentage

        return True

    async def process_query(
        self,
        query: SearchQuery,
        experiment_id: str,
        execute_fn: Callable[[SearchQuery, dict[str, Any]], SearchResponse],
        user_id: str | None = None,
    ) -> tuple[SearchResponse, ExperimentResult | None]:
        """Process a query using the appropriate experiment variant.

        Args:
            query: The search query to process
            experiment_id: ID of the experiment to use
            execute_fn: Function to execute the query with variant config
            user_id: Optional user ID for user-based assignment

        Returns:
            Tuple of (response, experiment result)
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            logger.warning(f"Experiment {experiment_id} not found")
            # Execute with default config and return
            return await execute_fn(query, {}), None

        # Check if query should be included in experiment
        if not self.should_include_in_experiment(experiment, query):
            # Execute with default variant and return
            default_variant = experiment.variants[0]  # Use first variant as default
            return await execute_fn(query, default_variant.config), None

        # Assign variant
        variant = self.assign_variant(experiment, query, user_id)

        # Execute the variant
        start_time = time.time()
        try:
            response = await execute_fn(query, variant.config)
            error = None
        except Exception as e:
            logger.error(f"Error executing variant {variant.id}: {e}")
            response = None
            error = str(e)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Create experiment result
        result = ExperimentResult(
            variant_id=variant.id,
            query=query.query,
            response=response,
            metrics={
                "latency_ms": latency_ms,
                "result_count": len(response.results) if response else 0,
            },
            error=error,
            latency_ms=latency_ms,
        )

        # Save result
        self._save_result(experiment_id, result)

        return response or SearchResponse(results=[]), result

    async def run_shadow_test(
        self,
        query: SearchQuery,
        experiment_id: str,
        execute_fn: Callable[[SearchQuery, dict[str, Any]], SearchResponse],
        user_id: str | None = None,
    ) -> None:
        """Run a shadow test for an experiment without affecting user results.

        Args:
            query: The search query to process
            experiment_id: ID of the experiment to use
            execute_fn: Function to execute the query with variant config
            user_id: Optional user ID for user-based assignment
        """
        if not self.enable_shadow_testing:
            return

        experiment = self.get_experiment(experiment_id)
        if not experiment:
            logger.warning(f"Experiment {experiment_id} not found for shadow testing")
            return

        # Check if query should be included in experiment
        if not self.should_include_in_experiment(experiment, query):
            return

        # Run all variants as shadow tests
        for variant in experiment.variants:
            # Execute the variant
            start_time = time.time()
            try:
                response = await execute_fn(query, variant.config)
                error = None
            except Exception as e:
                logger.error(f"Error in shadow test for variant {variant.id}: {e}")
                response = None
                error = str(e)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Create experiment result
            result = ExperimentResult(
                variant_id=variant.id,
                query=query.query,
                response=response,
                metrics={
                    "latency_ms": latency_ms,
                    "result_count": len(response.results) if response else 0,
                    "is_shadow": True,
                },
                error=error,
                latency_ms=latency_ms,
            )

            # Save result
            self._save_result(experiment_id, result)

    def get_results(
        self, experiment_id: str, limit: int = 1000
    ) -> list[ExperimentResult]:
        """Get results for an experiment.

        Args:
            experiment_id: ID of the experiment to get results for
            limit: Maximum number of results to return

        Returns:
            List of experiment results
        """
        results = self.results.get(experiment_id, [])
        return results[-limit:] if limit < len(results) else results

    def analyze_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Analyze the results of an experiment.

        Args:
            experiment_id: ID of the experiment to analyze

        Returns:
            Analysis results
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            return {"error": f"Experiment {experiment_id} not found"}

        results = self.get_results(experiment_id)
        if not results:
            return {"error": f"No results found for experiment {experiment_id}"}

        # Group results by variant
        variant_results = {}
        for variant in experiment.variants:
            variant_results[variant.id] = [
                r for r in results if r.variant_id == variant.id
            ]

        # Calculate metrics for each variant
        metrics = {}
        for variant_id, variant_results_list in variant_results.items():
            if not variant_results_list:
                metrics[variant_id] = {"error": "No results"}
                continue

            # Calculate average latency
            latencies = [r.latency_ms for r in variant_results_list]
            avg_latency = sum(latencies) / len(latencies)

            # Calculate result counts
            result_counts = [
                len(r.response.results) if r.response else 0
                for r in variant_results_list
            ]
            avg_result_count = sum(result_counts) / len(result_counts)

            # Calculate error rate
            error_count = sum(1 for r in variant_results_list if r.error)
            error_rate = error_count / len(variant_results_list)

            # Calculate other metrics (can be expanded)
            metrics[variant_id] = {
                "count": len(variant_results_list),
                "avg_latency_ms": avg_latency,
                "avg_result_count": avg_result_count,
                "error_rate": error_rate,
                "p50_latency_ms": np.percentile(latencies, 50),
                "p90_latency_ms": np.percentile(latencies, 90),
                "p95_latency_ms": np.percentile(latencies, 95),
                "p99_latency_ms": np.percentile(latencies, 99),
            }

        # Create summary
        return {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "total_queries": len(results),
            "variants": metrics,
            "start_date": experiment.start_date,
            "end_date": experiment.end_date,
            "active": experiment.active,
        }


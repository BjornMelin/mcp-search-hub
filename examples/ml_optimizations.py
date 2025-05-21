#!/usr/bin/env python3
"""Example script demonstrating ML optimization features."""

import logging
import sys
import time
from pathlib import Path

# Add the parent directory to the path for imports
sys.path.append(str(Path(__file__).parent.parent))

from mcp_search_hub.query_routing.ml_models import EmbeddingGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ml_optimizations_example")


def benchmark_embedding_generation(
    generator: EmbeddingGenerator,
    texts: list[str],
    batch_size: int = 100,
    iterations: int = 3,
) -> float:
    """Benchmark embedding generation performance.

    Args:
        generator: EmbeddingGenerator instance
        texts: List of texts to embed
        batch_size: Batch size for each run
        iterations: Number of iterations to run

    Returns:
        Average time per text in milliseconds
    """
    # Warm up
    logger.info("Warming up generator with a single text...")
    generator.generate(texts[0])

    # Benchmark
    total_times = []
    for i in range(iterations):
        batch = texts[:batch_size]
        start_time = time.time()
        results = generator.batch_generate(batch)
        end_time = time.time()
        total_time = end_time - start_time
        texts_per_second = len(batch) / total_time
        ms_per_text = 1000 * total_time / len(batch)
        total_times.append(total_time)
        logger.info(
            f"Iteration {i + 1}: {len(batch)} texts in {total_time:.2f}s "
            f"({texts_per_second:.2f} texts/s, {ms_per_text:.2f} ms/text)"
        )

    avg_time = sum(total_times) / len(total_times)
    avg_ms_per_text = 1000 * avg_time / batch_size
    logger.info(f"Average: {avg_ms_per_text:.2f} ms per text")

    return avg_ms_per_text


def benchmark_similarity_calculation(
    generator: EmbeddingGenerator,
    reference: str,
    candidates: list[str],
    iterations: int = 3,
) -> float:
    """Benchmark similarity calculation performance.

    Args:
        generator: EmbeddingGenerator instance
        reference: Reference text
        candidates: List of candidate texts
        iterations: Number of iterations to run

    Returns:
        Average time per comparison in milliseconds
    """
    # Warm up
    logger.info("Warming up similarity with a single comparison...")
    generator.similarity(reference, candidates[0])

    # Benchmark
    total_times = []
    for i in range(iterations):
        start_time = time.time()
        results = generator.batch_similarity(reference, candidates)
        end_time = time.time()
        total_time = end_time - start_time
        comparisons_per_second = len(candidates) / total_time
        ms_per_comparison = 1000 * total_time / len(candidates)
        total_times.append(total_time)
        logger.info(
            f"Iteration {i + 1}: {len(candidates)} comparisons in {total_time:.2f}s "
            f"({comparisons_per_second:.2f} comparisons/s, {ms_per_comparison:.2f} ms/comparison)"
        )

    avg_time = sum(total_times) / len(total_times)
    avg_ms_per_comparison = 1000 * avg_time / len(candidates)
    logger.info(f"Average: {avg_ms_per_comparison:.2f} ms per comparison")

    return avg_ms_per_comparison


def generate_test_texts(count: int) -> list[str]:
    """Generate test texts of varying length.

    Args:
        count: Number of texts to generate

    Returns:
        List of generated texts
    """
    import random

    # Some base topics
    topics = [
        "artificial intelligence",
        "machine learning",
        "natural language processing",
        "computer vision",
        "neural networks",
        "deep learning",
        "big data",
        "quantum computing",
        "blockchain",
        "cybersecurity",
        "cloud computing",
        "internet of things",
        "augmented reality",
        "virtual reality",
        "autonomous vehicles",
        "robotics",
        "space exploration",
        "renewable energy",
        "biotechnology",
        "nanotechnology",
        "climate change",
        "global warming",
        "sustainable development",
        "public health",
        "education",
        "economics",
        "history",
        "politics",
        "philosophy",
        "psychology",
        "sociology",
        "anthropology",
    ]

    # Generate random queries based on topics
    texts = []
    for _ in range(count):
        topic = random.choice(topics)
        query_type = random.choice(
            [
                "how to",
                "what is",
                "why is",
                "when did",
                "where can I",
                "who invented",
                "best practices for",
                "top 10",
                "examples of",
                "definition of",
                "history of",
                "future of",
                "advantages of",
                "disadvantages of",
                "comparison of",
                "difference between",
                "relationship between",
                "impact of",
                "causes of",
                "effects of",
            ]
        )

        # Add random specificity
        specificity = random.choice(
            [
                "for beginners",
                "in 2025",
                "with Python",
                "using TensorFlow",
                "in business",
                "in healthcare",
                "in education",
                "in manufacturing",
                "for small businesses",
                "for enterprises",
                "for startups",
                "in developing countries",
                "in the United States",
                "in Europe",
                "in Asia",
                "in Africa",
                "in Australia",
                "in South America",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",  # Empty strings to make specific terms less common
            ]
        )

        # Combine to form a query
        query = f"{query_type} {topic} {specificity}".strip()
        texts.append(query)

    return texts


def main():
    """Run the ML optimizations example."""
    logger.info("Starting ML optimizations example")

    # Generate test data
    num_texts = 1000
    logger.info(f"Generating {num_texts} test texts...")
    texts = generate_test_texts(num_texts)

    # Reference text for similarity tests
    reference = "how to implement machine learning in business applications"

    # Test configurations
    configs = [
        {
            "name": "Default",
            "params": {
                "model_name": "all-MiniLM-L6-v2",
                "use_gpu": False,
                "backend": "default",
                "use_disk_cache": False,
                "use_quantization": False,
                "parallel_processes": 1,
            },
        },
        {
            "name": "With Memory Cache",
            "params": {
                "model_name": "all-MiniLM-L6-v2",
                "use_gpu": False,
                "backend": "default",
                "use_disk_cache": False,
                "use_quantization": False,
                "cache_size": 10000,  # Larger memory cache
                "parallel_processes": 1,
            },
        },
        {
            "name": "With Disk Cache",
            "params": {
                "model_name": "all-MiniLM-L6-v2",
                "use_gpu": False,
                "backend": "default",
                "use_disk_cache": True,
                "use_quantization": False,
                "parallel_processes": 1,
            },
        },
        {
            "name": "With Parallel Processing",
            "params": {
                "model_name": "all-MiniLM-L6-v2",
                "use_gpu": False,
                "backend": "default",
                "use_disk_cache": False,
                "use_quantization": False,
                "parallel_processes": None,  # Auto-detect
            },
        },
    ]

    # Add GPU configs if available
    try:
        import torch

        if torch.cuda.is_available():
            configs.extend(
                [
                    {
                        "name": "With GPU",
                        "params": {
                            "model_name": "all-MiniLM-L6-v2",
                            "use_gpu": True,
                            "backend": "default",
                            "use_disk_cache": False,
                            "use_quantization": False,
                            "parallel_processes": 1,
                        },
                    },
                    {
                        "name": "With GPU + FP16",
                        "params": {
                            "model_name": "all-MiniLM-L6-v2",
                            "use_gpu": True,
                            "backend": "default",
                            "use_disk_cache": False,
                            "use_quantization": False,
                            "parallel_processes": 1,
                        },
                    },
                ]
            )
    except ImportError:
        logger.warning("Torch not available. Skipping GPU configurations.")

    # Add ONNX config if available
    try:
        import onnxruntime

        configs.append(
            {
                "name": "With ONNX Backend",
                "params": {
                    "model_name": "all-MiniLM-L6-v2",
                    "use_gpu": False,
                    "backend": "onnx",
                    "use_disk_cache": False,
                    "use_quantization": False,
                    "parallel_processes": 1,
                },
            }
        )
    except ImportError:
        logger.warning("ONNX Runtime not available. Skipping ONNX configuration.")

    # Add OpenVINO config if available
    try:
        import openvino

        configs.append(
            {
                "name": "With OpenVINO Backend",
                "params": {
                    "model_name": "all-MiniLM-L6-v2",
                    "use_gpu": False,
                    "backend": "openvino",
                    "use_disk_cache": False,
                    "use_quantization": False,
                    "parallel_processes": 1,
                },
            }
        )
    except ImportError:
        logger.warning("OpenVINO not available. Skipping OpenVINO configuration.")

    # Run benchmarks
    results = []
    for config in configs:
        logger.info(
            f"\n\n========== Testing configuration: {config['name']} =========="
        )
        try:
            # Create generator with this configuration
            generator = EmbeddingGenerator(**config["params"])

            # Benchmark embedding generation
            logger.info("Benchmarking embedding generation...")
            embedding_time = benchmark_embedding_generation(
                generator,
                texts,
                batch_size=100,
                iterations=3,
            )

            # Benchmark similarity calculation
            logger.info("Benchmarking similarity calculation...")
            similarity_time = benchmark_similarity_calculation(
                generator,
                reference,
                texts[:200],  # Use a subset for similarity tests
                iterations=3,
            )

            # Record results
            results.append(
                {
                    "config": config["name"],
                    "embedding_ms": embedding_time,
                    "similarity_ms": similarity_time,
                }
            )

        except Exception as e:
            logger.error(f"Error testing configuration {config['name']}: {e}")

    # Print summary
    logger.info("\n\n========== SUMMARY ==========")
    logger.info(
        f"{'Configuration':<25} {'Embedding (ms/text)':<20} {'Similarity (ms/comparison)':<25}"
    )
    logger.info("-" * 70)

    for result in results:
        logger.info(
            f"{result['config']:<25} {result['embedding_ms']:<20.2f} {result['similarity_ms']:<25.2f}"
        )


if __name__ == "__main__":
    main()

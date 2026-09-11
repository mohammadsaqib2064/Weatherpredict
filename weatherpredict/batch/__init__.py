"""Batch layer: pluggable processing adapters, synthetic generation, pipeline."""

from weatherpredict.batch.adapters import (
    BatchAdapter,
    HadoopAdapter,
    LocalFallbackAdapter,
    get_adapter,
)
from weatherpredict.batch.pipeline import run_batch_pipeline
from weatherpredict.batch.synthetic import REGIONS, generate_synthetic_dataset

__all__ = [
    "BatchAdapter",
    "HadoopAdapter",
    "LocalFallbackAdapter",
    "get_adapter",
    "run_batch_pipeline",
    "REGIONS",
    "generate_synthetic_dataset",
]

"""Batch adapters: local pandas plus a Hadoop/HDFS interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd


class BatchAdapter(ABC):
    """Contract for batch climate processing (Hadoop-pluggable)."""

    name: str = "base"

    @abstractmethod
    def partition(self, df: pd.DataFrame, partition_keys: list[str]) -> dict[str, pd.DataFrame]:
        ...

    @abstractmethod
    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        ...

    @abstractmethod
    def reduce_aggregate(self, partitions: dict[str, pd.DataFrame]) -> pd.DataFrame:
        ...

    def write_partitions(self, partitions: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for key, part in partitions.items():
            safe = (
                str(key)
                .replace("/", "_")
                .replace("\\", "_")
                .replace("|", "__")
                .replace(":", "_")
                .replace("*", "_")
                .replace("?", "_")
                .replace("<", "_")
                .replace(">", "_")
                .replace('"', "_")
            )
            path = out_dir / f"part_{safe}.csv"
            part.to_csv(path, index=False)
            paths.append(path)
        return paths


class LocalFallbackAdapter(BatchAdapter):
    """Windows-friendly pandas implementation (PySpark-style local fallback)."""

    name = "local_pandas"

    def partition(self, df: pd.DataFrame, partition_keys: list[str]) -> dict[str, pd.DataFrame]:
        if df.empty:
            return {}
        keys = [k for k in partition_keys if k in df.columns]
        if not keys:
            return {"all": df.copy()}
        groups = {}
        for values, group in df.groupby(keys, dropna=False):
            if not isinstance(values, tuple):
                values = (values,)
            key = "|".join(str(v) for v in values)
            groups[key] = group.copy()
        return groups

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        out = df.copy()
        if "observed_at" in out.columns:
            out["observed_at"] = pd.to_datetime(out["observed_at"], utc=True, errors="coerce")
            out = out.dropna(subset=["observed_at"])
        numeric_cols = [
            c
            for c in out.columns
            if c.endswith(("_c", "_mm", "_pct", "_ms", "_hpa", "_ppm")) or c == "value"
        ]
        for col in numeric_cols:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        # Flag missing but keep rows (graceful missing-record handling)
        if numeric_cols:
            out["missing_count"] = out[numeric_cols].isna().sum(axis=1)
        # Drop exact duplicates
        subset = [c for c in ["station_id", "sensor_id", "observed_at", "metric"] if c in out.columns]
        if subset:
            out = out.drop_duplicates(subset=subset, keep="last")
        return out.reset_index(drop=True)

    def reduce_aggregate(self, partitions: dict[str, pd.DataFrame]) -> pd.DataFrame:
        frames = []
        for key, part in partitions.items():
            if part.empty:
                continue
            region = key.split("|")[0] if key else "unknown"
            work = part.copy()
            if "observed_at" in work.columns:
                work["period"] = work["observed_at"].dt.to_period("M").astype(str)
            else:
                work["period"] = "unknown"
            metrics = {}
            for col in ["temp_c", "precip_mm", "humidity_pct", "value"]:
                if col in work.columns:
                    metrics[f"{col}_mean"] = work.groupby("period")[col].mean()
                    metrics[f"{col}_min"] = work.groupby("period")[col].min()
                    metrics[f"{col}_max"] = work.groupby("period")[col].max()
                    metrics[f"{col}_count"] = work.groupby("period")[col].count()
            if not metrics:
                continue
            agg = pd.DataFrame(metrics).reset_index()
            agg["region"] = region
            frames.append(agg)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)


class HadoopAdapter(BatchAdapter):
    """
    Production Hadoop/HDFS/MapReduce adapter (interface + stubs).

    Upgrade path:
    1. Set HDFS_NAMENODE / YARN_RM env vars.
    2. Stage input under hdfs://.../weatherpredict/raw/
    3. Submit MapReduce or Spark job that implements the same clean/partition/reduce contract.
    4. Write aggregates to hdfs://.../weatherpredict/processed/ and Impala-external tables.
    """

    name = "hadoop_hdfs"

    def __init__(self, hdfs_raw: str | None = None, hdfs_processed: str | None = None):
        self.hdfs_raw = hdfs_raw or "hdfs://namenode:8020/weatherpredict/raw"
        self.hdfs_processed = hdfs_processed or "hdfs://namenode:8020/weatherpredict/processed"
        self._local = LocalFallbackAdapter()

    def partition(self, df: pd.DataFrame, partition_keys: list[str]) -> dict[str, pd.DataFrame]:
        # Local emulation until cluster credentials are available
        return self._local.partition(df, partition_keys)

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        return self._local.clean(df)

    def reduce_aggregate(self, partitions: dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self._local.reduce_aggregate(partitions)

    def submit_mapreduce(self, job_name: str, input_glob: str) -> dict[str, Any]:
        """Documented production hook — not executed without a live cluster."""
        return {
            "status": "not_configured",
            "message": (
                "Hadoop cluster not configured. Use LocalFallbackAdapter for development. "
                f"Would submit job={job_name} input={input_glob} "
                f"raw={self.hdfs_raw} processed={self.hdfs_processed}"
            ),
        }


def get_adapter(name: str | None = None) -> BatchAdapter:
    choice = (name or "local").lower()
    if choice in ("hadoop", "hdfs", "hadoop_hdfs"):
        return HadoopAdapter()
    return LocalFallbackAdapter()

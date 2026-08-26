"""
Performance baseline tracking and comparison.

Monitors test results against established baselines and tracks trends.
"""

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class PerformanceMetric:
    """Represents a performance metric measurement."""

    endpoint: str
    timestamp: datetime
    request_count: int
    failure_count: int
    median_response_time: float
    average_response_time: float
    min_response_time: float
    max_response_time: float
    p50: float
    p95: float
    p99: float
    requests_per_second: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceMetric":
        """Create from dictionary."""
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class BaselineTracker:
    """Tracks and compares performance against baselines."""

    def __init__(self, baseline_file: Optional[str] = None):
        """Initialize baseline tracker."""
        self.baseline_file = baseline_file or "load_testing/baselines.json"
        self.baselines = self._load_baselines()
        self.current_metrics: Dict[str, List[PerformanceMetric]] = {}

    def _load_baselines(self) -> Dict[str, Dict[str, float]]:
        """Load baselines from file or use defaults."""
        baseline_path = Path(self.baseline_file)
        if baseline_path.exists():
            with open(baseline_path, "r") as f:
                return json.load(f)
        else:
            # Use defaults from config
            from load_testing.config import TestConfig

            return TestConfig.PERFORMANCE_BASELINES

    def save_baselines(self, baselines: Optional[Dict[str, Dict[str, float]]] = None):
        """Save baselines to file."""
        baselines = baselines or self.baselines
        baseline_path = Path(self.baseline_file)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)

        with open(baseline_path, "w") as f:
            json.dump(baselines, f, indent=2)

    def record_metric(self, metric: PerformanceMetric):
        """Record a performance metric."""
        if metric.endpoint not in self.current_metrics:
            self.current_metrics[metric.endpoint] = []
        self.current_metrics[metric.endpoint].append(metric)

    def record_from_stats(self, stats: Dict[str, Any], endpoint: str):
        """Record metrics from Locust stats."""
        metric = PerformanceMetric(
            endpoint=endpoint,
            timestamp=datetime.now(),
            request_count=stats.get("num_requests", 0),
            failure_count=stats.get("num_failures", 0),
            median_response_time=stats.get("median_response_time", 0),
            average_response_time=stats.get("avg_response_time", 0),
            min_response_time=stats.get("min_response_time", 0),
            max_response_time=stats.get("max_response_time", 0),
            p50=stats.get("percentiles", {}).get(0.5, 0),
            p95=stats.get("percentiles", {}).get(0.95, 0),
            p99=stats.get("percentiles", {}).get(0.99, 0),
            requests_per_second=stats.get("current_rps", 0),
        )
        self.record_metric(metric)

    def compare_to_baseline(self, endpoint: str) -> Tuple[bool, Dict[str, Any]]:
        """Compare current metrics to baseline."""
        if endpoint not in self.current_metrics:
            return False, {"error": f"No metrics recorded for {endpoint}"}

        if endpoint not in self.baselines:
            return False, {"error": f"No baseline defined for {endpoint}"}

        metrics = self.current_metrics[endpoint]
        if not metrics:
            return False, {"error": "No metrics to compare"}

        # Calculate aggregates from current metrics
        p50_values = [m.p50 for m in metrics]
        p95_values = [m.p95 for m in metrics]
        p99_values = [m.p99 for m in metrics]

        current_p50 = statistics.median(p50_values) if p50_values else 0
        current_p95 = statistics.median(p95_values) if p95_values else 0
        current_p99 = statistics.median(p99_values) if p99_values else 0

        baseline = self.baselines[endpoint]

        # Compare against baseline
        comparison: Dict[str, Any] = {
            "endpoint": endpoint,
            "baseline": baseline,
            "current": {
                "p50": current_p50,
                "p95": current_p95,
                "p99": current_p99,
            },
            "delta": {
                "p50": current_p50 - baseline["p50"],
                "p95": current_p95 - baseline["p95"],
                "p99": current_p99 - baseline["p99"],
            },
            "delta_percentage": {
                "p50": ((current_p50 - baseline["p50"]) / baseline["p50"] * 100)
                if baseline["p50"] > 0
                else 0,
                "p95": ((current_p95 - baseline["p95"]) / baseline["p95"] * 100)
                if baseline["p95"] > 0
                else 0,
                "p99": ((current_p99 - baseline["p99"]) / baseline["p99"] * 100)
                if baseline["p99"] > 0
                else 0,
            },
        }

        # Determine if performance is within acceptable range
        # Allow 20% degradation from baseline
        tolerance = 1.2
        passed = all(
            [
                current_p50 <= baseline["p50"] * tolerance,
                current_p95 <= baseline["p95"] * tolerance,
                current_p99 <= baseline["p99"] * tolerance,
            ]
        )

        comparison["passed"] = passed
        comparison["message"] = (
            "Performance within acceptable range"
            if passed
            else "Performance degradation detected"
        )

        return passed, comparison

    def generate_summary(self) -> Dict[str, Any]:
        """Generate summary of all metrics and comparisons."""
        summary: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "endpoints": {},
            "overall_passed": True,
            "total_requests": 0,
            "total_failures": 0,
        }

        for endpoint, metrics in self.current_metrics.items():
            if not metrics:
                continue

            # Aggregate metrics
            total_requests = sum(m.request_count for m in metrics)
            total_failures = sum(m.failure_count for m in metrics)
            avg_rps = statistics.mean(m.requests_per_second for m in metrics)

            summary["total_requests"] += total_requests
            summary["total_failures"] += total_failures

            # Compare to baseline
            passed, comparison = self.compare_to_baseline(endpoint)
            if not passed:
                summary["overall_passed"] = False

            summary["endpoints"][endpoint] = {
                "metrics": {
                    "request_count": total_requests,
                    "failure_count": total_failures,
                    "failure_rate": (
                        total_failures / total_requests * 100
                        if total_requests > 0
                        else 0
                    ),
                    "avg_rps": avg_rps,
                },
                "comparison": comparison,
                "passed": passed,
            }

        return summary

    def update_baselines_from_current(self, endpoints: Optional[List[str]] = None):
        """Update baselines using current metrics."""
        endpoints = endpoints or list(self.current_metrics.keys())

        for endpoint in endpoints:
            if endpoint not in self.current_metrics:
                continue

            metrics = self.current_metrics[endpoint]
            if not metrics:
                continue

            # Calculate new baseline values
            p50_values = [m.p50 for m in metrics]
            p95_values = [m.p95 for m in metrics]
            p99_values = [m.p99 for m in metrics]

            self.baselines[endpoint] = {
                "p50": statistics.median(p50_values) if p50_values else 0,
                "p95": statistics.median(p95_values) if p95_values else 0,
                "p99": statistics.median(p99_values) if p99_values else 0,
            }

        self.save_baselines()

    def get_trend_analysis(
        self, endpoint: str, window_size: int = 10
    ) -> Dict[str, Any]:
        """Analyze performance trends for an endpoint."""
        if endpoint not in self.current_metrics:
            return {"error": f"No metrics for {endpoint}"}

        metrics = self.current_metrics[endpoint]
        if len(metrics) < 2:
            return {"error": "Insufficient data for trend analysis"}

        # Get the last N metrics
        recent_metrics = metrics[-window_size:]

        # Calculate trend
        p50_values = [m.p50 for m in recent_metrics]
        p95_values = [m.p95 for m in recent_metrics]
        p99_values = [m.p99 for m in recent_metrics]

        def calculate_trend(values: List[float]) -> str:
            """Calculate trend direction."""
            if len(values) < 2:
                return "stable"

            # Simple linear regression
            n = len(values)
            x_mean = (n - 1) / 2
            y_mean = sum(values) / n

            numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
            denominator = sum((i - x_mean) ** 2 for i in range(n))

            if denominator == 0:
                return "stable"

            slope = numerator / denominator

            # Determine trend based on slope
            if slope > 0.05 * y_mean:  # More than 5% increase
                return "degrading"
            elif slope < -0.05 * y_mean:  # More than 5% decrease
                return "improving"
            else:
                return "stable"

        return {
            "endpoint": endpoint,
            "window_size": len(recent_metrics),
            "trends": {
                "p50": calculate_trend(p50_values),
                "p95": calculate_trend(p95_values),
                "p99": calculate_trend(p99_values),
            },
            "current_values": {
                "p50": p50_values[-1] if p50_values else 0,
                "p95": p95_values[-1] if p95_values else 0,
                "p99": p99_values[-1] if p99_values else 0,
            },
            "previous_values": {
                "p50": p50_values[-2] if len(p50_values) > 1 else 0,
                "p95": p95_values[-2] if len(p95_values) > 1 else 0,
                "p99": p99_values[-2] if len(p99_values) > 1 else 0,
            },
        }

    def export_metrics(self, output_file: str):
        """Export collected metrics to file."""
        export_data: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "baselines": self.baselines,
            "metrics": {},
        }

        for endpoint, metrics in self.current_metrics.items():
            export_data["metrics"][endpoint] = [m.to_dict() for m in metrics]

        with open(output_file, "w") as f:
            json.dump(export_data, f, indent=2)

    def clear_metrics(self):
        """Clear current metrics."""
        self.current_metrics = {}

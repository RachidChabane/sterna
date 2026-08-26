"""
Load test runner script for CI/CD integration.

This script orchestrates load testing execution and reporting.
"""

import argparse
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from load_testing.config import LoadProfile, TestConfig
from load_testing.baselines import BaselineTracker
from load_testing.reports import ReportGenerator


class LoadTestRunner:
    """Orchestrates load test execution."""

    def __init__(self, profile: LoadProfile, base_url: Optional[str] = None):
        """Initialize load test runner."""
        self.profile = profile
        self.profile_config = TestConfig.get_profile(profile)
        self.base_url = base_url or TestConfig.BASE_URL
        self.baseline_tracker = BaselineTracker()
        self.report_generator = ReportGenerator()

    def run_locust(self, headless: bool = True) -> Dict[str, Any]:
        """Run Locust tests."""
        print(f"Starting load test with profile: {self.profile.value}")
        print(f"Configuration: {self.profile_config}")

        # Build Locust command
        cmd = [
            "locust",
            "-f",
            "load_testing/locustfile.py",
            "--host",
            self.base_url,
            "--users",
            str(self.profile_config["users"]),
            "--spawn-rate",
            str(self.profile_config["spawn_rate"]),
            "--run-time",
            str(self.profile_config["run_time"]),
        ]

        if headless:
            # Run in headless mode for CI
            cmd.extend(
                [
                    "--headless",
                    "--only-summary",
                    "--csv",
                    "load_testing/reports/output/results",
                    "--html",
                    "load_testing/reports/output/report.html",
                ]
            )

        print(f"Executing: {' '.join(cmd)}")

        # Run Locust
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
            )

            if result.returncode != 0:
                print(f"Locust failed with exit code {result.returncode}")
                print(f"STDERR: {result.stderr}")
                return {"success": False, "error": result.stderr}

            # Parse CSV results
            stats = self._parse_csv_results()
            return {"success": True, "stats": stats}

        except Exception as e:
            print(f"Error running Locust: {e}")
            return {"success": False, "error": str(e)}

    def _parse_csv_results(self) -> Dict[str, Any]:
        """Parse Locust CSV output."""
        stats_file = Path("load_testing/reports/output/results_stats.csv")
        if not stats_file.exists():
            return {}

        stats: Dict[str, Any] = {
            "endpoints": {},
            "total_requests": 0,
            "total_failures": 0,
            "duration": 0,
        }

        # Parse CSV
        import csv

        with open(stats_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["Name"] == "Aggregated":
                    stats["total_requests"] = int(row.get("Request Count", 0))
                    stats["total_failures"] = int(row.get("Failure Count", 0))
                    stats["avg_response_time"] = float(
                        row.get("Average Response Time", 0)
                    )
                    stats["max_response_time"] = float(row.get("Max Response Time", 0))
                else:
                    endpoint = row["Name"]
                    stats["endpoints"][endpoint] = {
                        "num_requests": int(row.get("Request Count", 0)),
                        "num_failures": int(row.get("Failure Count", 0)),
                        "median_response_time": float(
                            row.get("Median Response Time", 0)
                        ),
                        "avg_response_time": float(row.get("Average Response Time", 0)),
                        "min_response_time": float(row.get("Min Response Time", 0)),
                        "max_response_time": float(row.get("Max Response Time", 0)),
                        "percentiles": {
                            0.5: float(row.get("50%", 0)),
                            0.95: float(row.get("95%", 0)),
                            0.99: float(row.get("99%", 0)),
                        },
                        "current_rps": float(row.get("Current RPS", 0)),
                    }

        return stats

    def validate_performance(self, stats: Dict[str, Any]) -> bool:
        """Validate performance against baselines."""
        print("\n=== Performance Validation ===")

        # Record metrics in baseline tracker
        for endpoint, endpoint_stats in stats.get("endpoints", {}).items():
            self.baseline_tracker.record_from_stats(endpoint_stats, endpoint)

        # Generate summary and compare to baselines
        summary = self.baseline_tracker.generate_summary()

        # Print results
        print(f"\nOverall Result: {'PASS' if summary['overall_passed'] else 'FAIL'}")
        print(f"Total Requests: {summary['total_requests']}")
        print(f"Total Failures: {summary['total_failures']}")

        # Print endpoint results
        print("\nEndpoint Performance:")
        for endpoint, data in summary.get("endpoints", {}).items():
            status = "✓ PASS" if data["passed"] else "✗ FAIL"
            print(f"  {endpoint}: {status}")
            if "comparison" in data and "delta_percentage" in data["comparison"]:
                deltas = data["comparison"]["delta_percentage"]
                print(
                    f"    P50: {deltas['p50']:+.1f}%, P95: {deltas['p95']:+.1f}%, P99: {deltas['p99']:+.1f}%"
                )

        return summary["overall_passed"]

    def generate_reports(self, stats: Dict[str, Any]):
        """Generate test reports."""
        print("\n=== Generating Reports ===")

        # Get baseline summary
        summary = self.baseline_tracker.generate_summary()

        # Generate HTML report
        html_report = self.report_generator.generate_html_report(
            test_name=self.profile.value,
            stats=stats,
            baseline_summary=summary,
            profile={
                "name": self.profile.value,
                "users": self.profile_config["users"],
                "spawn_rate": self.profile_config["spawn_rate"],
                "run_time": self.profile_config["run_time"],
                "wait_time": self.profile_config["wait_time"],
            },
        )
        print(f"HTML Report: {html_report}")

        # Generate JSON report
        json_report = self.report_generator.generate_json_report(
            test_name=self.profile.value,
            stats=stats,
            baseline_summary=summary,
            profile={
                "name": self.profile.value,
                "users": self.profile_config["users"],
                "spawn_rate": self.profile_config["spawn_rate"],
                "run_time": self.profile_config["run_time"],
                "wait_time": self.profile_config["wait_time"],
            },
        )
        print(f"JSON Report: {json_report}")

        # Export metrics
        metrics_file = f"load_testing/reports/output/metrics_{self.profile.value}_{int(time.time())}.json"
        self.baseline_tracker.export_metrics(metrics_file)
        print(f"Metrics Export: {metrics_file}")

    def run(self, headless: bool = True) -> bool:
        """Run complete load test suite."""
        print("=" * 60)
        print("Sterna Load Testing")
        print(f"Profile: {self.profile.value}")
        print(f"Target: {self.base_url}")
        print("=" * 60)

        # Create output directory
        Path("load_testing/reports/output").mkdir(parents=True, exist_ok=True)

        # Run Locust tests
        result = self.run_locust(headless=headless)
        if not result["success"]:
            print(f"Load test failed: {result.get('error')}")
            return False

        stats = result.get("stats", {})

        # Validate performance
        passed = self.validate_performance(stats)

        # Generate reports
        self.generate_reports(stats)

        print("\n" + "=" * 60)
        print(f"Load Test Complete: {'PASSED' if passed else 'FAILED'}")
        print("=" * 60)

        return passed


def main():
    """Main entry point for CI integration."""
    parser = argparse.ArgumentParser(description="Run load tests for Sterna")

    parser.add_argument(
        "--profile",
        type=str,
        choices=[p.value for p in LoadProfile],
        default="load",
        help="Load test profile to run",
    )

    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL to test against",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run in headless mode (for CI)",
    )

    parser.add_argument(
        "--update-baselines",
        action="store_true",
        help="Update baselines with current test results",
    )

    parser.add_argument(
        "--fail-on-degradation",
        action="store_true",
        default=True,
        help="Fail test if performance degrades",
    )

    args = parser.parse_args()

    # Set environment variables if provided
    if args.base_url:
        os.environ["LOAD_TEST_BASE_URL"] = args.base_url

    # Create runner
    profile = LoadProfile(args.profile)
    runner = LoadTestRunner(profile, base_url=args.base_url)

    # Run tests
    passed = runner.run(headless=args.headless)

    # Update baselines if requested
    if args.update_baselines and passed:
        print("\nUpdating baselines with current results...")
        runner.baseline_tracker.update_baselines_from_current()
        print("Baselines updated successfully")

    # Exit with appropriate code
    if args.fail_on_degradation and not passed:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

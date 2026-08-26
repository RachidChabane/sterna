"""
Load test report generation.

Creates comprehensive HTML and JSON reports from load test results.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from jinja2 import Template


class ReportGenerator:
    """Generates load test reports in various formats."""

    def __init__(self, output_dir: str = "load_testing/reports/output"):
        """Initialize report generator."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_html_report(
        self,
        test_name: str,
        stats: Dict[str, Any],
        baseline_summary: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> str:
        """Generate HTML report from test results."""
        html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Load Test Report - {{ test_name }}</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f4f4f4;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        h1 {
            margin: 0;
            font-size: 2.5em;
        }

        .metadata {
            margin-top: 15px;
            opacity: 0.9;
        }

        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .card h3 {
            margin-top: 0;
            color: #667eea;
            font-size: 1.2em;
        }

        .metric {
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }

        .metric:last-child {
            border-bottom: none;
        }

        .metric-value {
            font-weight: bold;
            color: #764ba2;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
        }

        td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }

        tr:hover {
            background: #f9f9f9;
        }

        .status-passed {
            color: #22c55e;
            font-weight: bold;
        }

        .status-failed {
            color: #ef4444;
            font-weight: bold;
        }

        .delta-positive {
            color: #ef4444;
        }

        .delta-negative {
            color: #22c55e;
        }

        .section {
            margin-bottom: 30px;
        }

        .section-title {
            font-size: 1.5em;
            color: #667eea;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }

        .chart-container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }

        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e5e7eb;
            border-radius: 10px;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
            transition: width 0.3s ease;
        }

        .failure-progress {
            background: linear-gradient(90deg, #ef4444 0%, #dc2626 100%);
        }

        @media (max-width: 768px) {
            .summary {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Load Test Report: {{ test_name }}</h1>
        <div class="metadata">
            <div>Generated: {{ timestamp }}</div>
            <div>Profile: {{ profile.name }} ({{ profile.users }} users, {{ profile.run_time }} runtime)</div>
            <div>Base URL: {{ base_url }}</div>
        </div>
    </div>

    <!-- Overall Summary -->
    <div class="summary">
        <div class="card">
            <h3>Overall Status</h3>
            <div class="metric">
                <span>Test Result</span>
                <span class="metric-value {% if overall_passed %}status-passed{% else %}status-failed{% endif %}">
                    {% if overall_passed %}PASSED{% else %}FAILED{% endif %}
                </span>
            </div>
            <div class="metric">
                <span>Total Requests</span>
                <span class="metric-value">{{ "{:,}".format(total_requests) }}</span>
            </div>
            <div class="metric">
                <span>Total Failures</span>
                <span class="metric-value">{{ "{:,}".format(total_failures) }}</span>
            </div>
            <div class="metric">
                <span>Failure Rate</span>
                <span class="metric-value">{{ "%.2f"|format(failure_rate) }}%</span>
            </div>
        </div>

        <div class="card">
            <h3>Response Times</h3>
            <div class="metric">
                <span>Median (p50)</span>
                <span class="metric-value">{{ "%.2f"|format(avg_p50) }} ms</span>
            </div>
            <div class="metric">
                <span>95th Percentile</span>
                <span class="metric-value">{{ "%.2f"|format(avg_p95) }} ms</span>
            </div>
            <div class="metric">
                <span>99th Percentile</span>
                <span class="metric-value">{{ "%.2f"|format(avg_p99) }} ms</span>
            </div>
            <div class="metric">
                <span>Max Response Time</span>
                <span class="metric-value">{{ "%.2f"|format(max_response_time) }} ms</span>
            </div>
        </div>

        <div class="card">
            <h3>Throughput</h3>
            <div class="metric">
                <span>Average RPS</span>
                <span class="metric-value">{{ "%.2f"|format(avg_rps) }}</span>
            </div>
            <div class="metric">
                <span>Peak RPS</span>
                <span class="metric-value">{{ "%.2f"|format(peak_rps) }}</span>
            </div>
            <div class="metric">
                <span>Total Duration</span>
                <span class="metric-value">{{ duration }} seconds</span>
            </div>
            <div class="metric">
                <span>Data Transferred</span>
                <span class="metric-value">{{ "%.2f"|format(data_transferred_mb) }} MB</span>
            </div>
        </div>
    </div>

    <!-- Endpoint Details -->
    <div class="section">
        <h2 class="section-title">Endpoint Performance</h2>
        <table>
            <thead>
                <tr>
                    <th>Endpoint</th>
                    <th>Requests</th>
                    <th>Failures</th>
                    <th>Median (ms)</th>
                    <th>P95 (ms)</th>
                    <th>P99 (ms)</th>
                    <th>Baseline Comparison</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for endpoint, data in endpoints.items() %}
                <tr>
                    <td>{{ endpoint }}</td>
                    <td>{{ "{:,}".format(data.metrics.request_count) }}</td>
                    <td>{{ "{:,}".format(data.metrics.failure_count) }}</td>
                    <td>{{ "%.2f"|format(data.comparison.current.p50) }}</td>
                    <td>{{ "%.2f"|format(data.comparison.current.p95) }}</td>
                    <td>{{ "%.2f"|format(data.comparison.current.p99) }}</td>
                    <td>
                        <div>P50:
                            <span class="{% if data.comparison.delta.p50 > 0 %}delta-positive{% else %}delta-negative{% endif %}">
                                {{ "%+.1f"|format(data.comparison.delta_percentage.p50) }}%
                            </span>
                        </div>
                        <div>P95:
                            <span class="{% if data.comparison.delta.p95 > 0 %}delta-positive{% else %}delta-negative{% endif %}">
                                {{ "%+.1f"|format(data.comparison.delta_percentage.p95) }}%
                            </span>
                        </div>
                        <div>P99:
                            <span class="{% if data.comparison.delta.p99 > 0 %}delta-positive{% else %}delta-negative{% endif %}">
                                {{ "%+.1f"|format(data.comparison.delta_percentage.p99) }}%
                            </span>
                        </div>
                    </td>
                    <td>
                        <span class="{% if data.passed %}status-passed{% else %}status-failed{% endif %}">
                            {% if data.passed %}PASS{% else %}FAIL{% endif %}
                        </span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- Test Configuration -->
    <div class="section">
        <h2 class="section-title">Test Configuration</h2>
        <div class="card">
            <table>
                <tr>
                    <td><strong>Load Profile:</strong></td>
                    <td>{{ profile.name }}</td>
                </tr>
                <tr>
                    <td><strong>Number of Users:</strong></td>
                    <td>{{ profile.users }}</td>
                </tr>
                <tr>
                    <td><strong>Spawn Rate:</strong></td>
                    <td>{{ profile.spawn_rate }} users/second</td>
                </tr>
                <tr>
                    <td><strong>Test Duration:</strong></td>
                    <td>{{ profile.run_time }}</td>
                </tr>
                <tr>
                    <td><strong>Wait Time:</strong></td>
                    <td>{{ profile.wait_time[0] }}-{{ profile.wait_time[1] }} seconds</td>
                </tr>
            </table>
        </div>
    </div>

    <!-- Recommendations -->
    {% if recommendations %}
    <div class="section">
        <h2 class="section-title">Recommendations</h2>
        <div class="card">
            <ul>
                {% for recommendation in recommendations %}
                <li>{{ recommendation }}</li>
                {% endfor %}
            </ul>
        </div>
    </div>
    {% endif %}
</body>
</html>
        """

        # Calculate aggregate statistics
        total_requests = baseline_summary.get("total_requests", 0)
        total_failures = baseline_summary.get("total_failures", 0)
        failure_rate = (
            (total_failures / total_requests * 100) if total_requests > 0 else 0
        )

        # Calculate average response times across endpoints
        endpoints_data = baseline_summary.get("endpoints", {})
        p50_values = []
        p95_values = []
        p99_values = []
        rps_values = []

        for endpoint_data in endpoints_data.values():
            if (
                "comparison" in endpoint_data
                and "current" in endpoint_data["comparison"]
            ):
                current = endpoint_data["comparison"]["current"]
                p50_values.append(current.get("p50", 0))
                p95_values.append(current.get("p95", 0))
                p99_values.append(current.get("p99", 0))
            if "metrics" in endpoint_data:
                rps_values.append(endpoint_data["metrics"].get("avg_rps", 0))

        avg_p50 = sum(p50_values) / len(p50_values) if p50_values else 0
        avg_p95 = sum(p95_values) / len(p95_values) if p95_values else 0
        avg_p99 = sum(p99_values) / len(p99_values) if p99_values else 0
        avg_rps = sum(rps_values) / len(rps_values) if rps_values else 0
        peak_rps = max(rps_values) if rps_values else 0

        # Generate recommendations
        recommendations = self._generate_recommendations(baseline_summary)

        # Render template
        template = Template(html_template)
        html_content = template.render(
            test_name=test_name,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            base_url=stats.get("base_url", "http://localhost:8000"),
            profile=profile,
            overall_passed=baseline_summary.get("overall_passed", False),
            total_requests=total_requests,
            total_failures=total_failures,
            failure_rate=failure_rate,
            avg_p50=avg_p50,
            avg_p95=avg_p95,
            avg_p99=avg_p99,
            max_response_time=stats.get("max_response_time", 0),
            avg_rps=avg_rps,
            peak_rps=peak_rps,
            duration=stats.get("duration", 0),
            data_transferred_mb=stats.get("data_transferred", 0) / (1024 * 1024),
            endpoints=endpoints_data,
            recommendations=recommendations,
        )

        # Save report
        report_file = (
            self.output_dir
            / f"report_{test_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        with open(report_file, "w") as f:
            f.write(html_content)

        return str(report_file)

    def generate_json_report(
        self,
        test_name: str,
        stats: Dict[str, Any],
        baseline_summary: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> str:
        """Generate JSON report from test results."""
        report_data = {
            "test_name": test_name,
            "timestamp": datetime.now().isoformat(),
            "profile": profile,
            "summary": baseline_summary,
            "stats": stats,
            "recommendations": self._generate_recommendations(baseline_summary),
        }

        # Save report
        report_file = (
            self.output_dir
            / f"report_{test_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report_data, f, indent=2)

        return str(report_file)

    def _generate_recommendations(self, baseline_summary: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []

        # Check overall pass/fail
        if not baseline_summary.get("overall_passed", False):
            recommendations.append(
                "Performance degradation detected. Review failing endpoints and optimize."
            )

        # Check failure rate
        total_requests = baseline_summary.get("total_requests", 0)
        total_failures = baseline_summary.get("total_failures", 0)
        if total_requests > 0:
            failure_rate = (total_failures / total_requests) * 100
            if failure_rate > 5:
                recommendations.append(
                    f"High failure rate ({failure_rate:.1f}%). Investigate error causes and improve error handling."
                )
            elif failure_rate > 1:
                recommendations.append(
                    f"Moderate failure rate ({failure_rate:.1f}%). Monitor and address recurring errors."
                )

        # Check individual endpoints
        slow_endpoints = []
        degraded_endpoints = []

        for endpoint, data in baseline_summary.get("endpoints", {}).items():
            if not data.get("passed", True):
                comparison = data.get("comparison", {})
                if comparison:
                    delta_p95 = comparison.get("delta_percentage", {}).get("p95", 0)
                    if delta_p95 > 20:
                        degraded_endpoints.append((endpoint, delta_p95))

                    current_p95 = comparison.get("current", {}).get("p95", 0)
                    if current_p95 > 1000:  # More than 1 second
                        slow_endpoints.append((endpoint, current_p95))

        if slow_endpoints:
            recommendations.append(
                "The following endpoints are slow (>1s p95): "
                + ", ".join([f"{ep[0]} ({ep[1]:.0f}ms)" for ep in slow_endpoints[:3]])
            )

        if degraded_endpoints:
            recommendations.append(
                "Performance degradation detected in: "
                + ", ".join(
                    [f"{ep[0]} (+{ep[1]:.1f}%)" for ep in degraded_endpoints[:3]]
                )
            )

        # Add general recommendations
        if not recommendations:
            recommendations.append(
                "All performance metrics are within acceptable ranges."
            )
            recommendations.append("Consider increasing load to find system limits.")

        return recommendations

    def generate_comparison_report(
        self,
        current_results: Dict[str, Any],
        previous_results: Dict[str, Any],
    ) -> str:
        """Generate comparison report between two test runs."""
        comparison: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "current": current_results,
            "previous": previous_results,
            "improvements": [],
            "degradations": [],
            "unchanged": [],
        }

        # Compare endpoint performance
        current_endpoints = current_results.get("endpoints", {})
        previous_endpoints = previous_results.get("endpoints", {})

        for endpoint in set(current_endpoints.keys()) | set(previous_endpoints.keys()):
            if endpoint in current_endpoints and endpoint in previous_endpoints:
                current_p95 = current_endpoints[endpoint]["comparison"]["current"][
                    "p95"
                ]
                previous_p95 = previous_endpoints[endpoint]["comparison"]["current"][
                    "p95"
                ]

                delta = current_p95 - previous_p95
                delta_pct = (delta / previous_p95 * 100) if previous_p95 > 0 else 0

                if delta_pct < -10:
                    comparison["improvements"].append(
                        {
                            "endpoint": endpoint,
                            "delta": delta,
                            "delta_percentage": delta_pct,
                        }
                    )
                elif delta_pct > 10:
                    comparison["degradations"].append(
                        {
                            "endpoint": endpoint,
                            "delta": delta,
                            "delta_percentage": delta_pct,
                        }
                    )
                else:
                    comparison["unchanged"].append(endpoint)

        # Save comparison report
        report_file = (
            self.output_dir
            / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(comparison, f, indent=2)

        return str(report_file)

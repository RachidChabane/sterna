"""
OpenTelemetry Instrumentation

Provides distributed tracing and metrics for the sandbox system.
"""

import logging
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
import os

logger = logging.getLogger(__name__)


def setup_telemetry(service_name: str, use_otlp: bool = True):
    """
    Setup OpenTelemetry instrumentation for a service.

    Args:
        service_name: Name of the service (e.g., 'orchestrator', 'fs-service')
        use_otlp: Whether to use OTLP exporter (requires collector) or console exporter
    """
    # Create resource with service information
    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "sterna",
        "deployment.environment": os.getenv("ENVIRONMENT", "development")
    })

    # Setup tracing
    trace_provider = TracerProvider(resource=resource)

    if use_otlp and os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        # OTLP exporter for production (sends to collector)
        otlp_exporter = OTLPSpanExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"),
            insecure=True
        )
        trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(f"Configured OTLP trace exporter for {service_name}")
    else:
        # Console exporter for development
        console_exporter = ConsoleSpanExporter()
        trace_provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info(f"Configured console trace exporter for {service_name}")

    trace.set_tracer_provider(trace_provider)

    # Setup metrics
    if use_otlp and os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"),
                insecure=True
            ),
            export_interval_millis=60000  # Export every 60 seconds
        )
    else:
        metric_reader = PeriodicExportingMetricReader(
            ConsoleMetricExporter(),
            export_interval_millis=60000
        )

    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Auto-instrument libraries
    RequestsInstrumentor().instrument()

    logger.info(f"OpenTelemetry instrumentation setup complete for {service_name}")


def instrument_fastapi(app):
    """
    Instrument FastAPI application with OpenTelemetry.

    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI instrumented with OpenTelemetry")


def instrument_celery():
    """Instrument Celery with OpenTelemetry."""
    CeleryInstrumentor().instrument()
    logger.info("Celery instrumented with OpenTelemetry")


# Custom metrics for sandbox system
def create_sandbox_metrics():
    """Create custom metrics for sandbox operations."""
    meter = metrics.get_meter(__name__)

    # Counters
    sandbox_creations = meter.create_counter(
        "sterna.sandboxes.created",
        description="Number of sandboxes created",
        unit="1"
    )

    connector_calls = meter.create_counter(
        "sterna.connectors.calls",
        description="Number of connector calls",
        unit="1"
    )

    # Histograms
    artifact_size = meter.create_histogram(
        "sterna.artifacts.size",
        description="Artifact file size",
        unit="bytes"
    )

    # Gauges (via Observable Gauge)
    def get_active_sandboxes():
        # In production, query Docker to count running sandbox containers
        import docker
        try:
            client = docker.from_env()
            containers = client.containers.list(filters={"name": "sandbox-*"})
            return len(containers)
        except Exception:
            return 0

    meter.create_observable_gauge(
        "sterna.sandboxes.active",
        callbacks=[lambda options: [metrics.Observation(get_active_sandboxes())]],
        description="Number of active sandbox containers",
        unit="1"
    )

    return {
        "sandbox_creations": sandbox_creations,
        "connector_calls": connector_calls,
        "artifact_size": artifact_size
    }


# Structured logging configuration
def setup_structured_logging(service_name: str):
    """
    Configure JSON structured logging.

    Args:
        service_name: Name of the service
    """
    import json_logging

    json_logging.init_fastapi(enable_json=True)
    json_logging.init_request_instrument(app=None)

    # Configure logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Add service name to all logs
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service_name = service_name
        return record

    logging.setLogRecordFactory(record_factory)

    logger.info(f"Structured logging configured for {service_name}")

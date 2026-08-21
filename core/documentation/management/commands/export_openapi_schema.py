"""
Management command to export OpenAPI schema to file.
"""

import json
import yaml
from django.core.management.base import BaseCommand
from drf_spectacular.generators import SchemaGenerator


class Command(BaseCommand):
    help = "Export OpenAPI schema to JSON or YAML file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            type=str,
            default="json",
            choices=["json", "yaml"],
            help="Output format (json or yaml)",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="openapi_schema",
            help="Output filename (without extension)",
        )
        parser.add_argument(
            "--pretty", action="store_true", help="Pretty print the output"
        )

    def handle(self, *args, **options):
        format_type = options["format"]
        output_file = f"{options['output']}.{format_type}"
        pretty = options["pretty"]

        self.stdout.write("Generating OpenAPI schema...")

        # Generate schema (title/version/description come from SPECTACULAR_SETTINGS)
        generator = SchemaGenerator()
        schema = generator.get_schema(request=None, public=True)

        # Write to file
        with open(output_file, "w") as f:
            if format_type == "json":
                if pretty:
                    json.dump(schema, f, indent=2)
                else:
                    json.dump(schema, f)
            else:  # yaml
                yaml.dump(schema, f, default_flow_style=False)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully exported schema to {output_file}")
        )

        # Print summary statistics
        paths_count = len(schema.get("paths", {}))
        tags_count = len(
            set(
                tag
                for path in schema.get("paths", {}).values()
                for method in path.values()
                if isinstance(method, dict)
                for tag in method.get("tags", [])
            )
        )

        self.stdout.write("Schema statistics:")
        self.stdout.write(f"  - API Endpoints: {paths_count}")
        self.stdout.write(f"  - Tags/Categories: {tags_count}")
        self.stdout.write(f"  - File size: {len(open(output_file).read())} bytes")

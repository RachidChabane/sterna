"""
Settings module initialization.
Dynamically loads the appropriate settings based on the DJANGO_ENV environment variable.
"""

import os

# Determine which settings module to use
env = os.environ.get("DJANGO_ENV", "dev")

if env == "prod":
    from .prod import *
elif env == "test":
    from .test import *
else:
    from .dev import *

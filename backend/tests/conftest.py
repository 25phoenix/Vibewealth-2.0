"""Set explicit environment defaults before application modules are imported."""

import os

os.environ["APP_ENVIRONMENT"] = "test"
os.environ["ALLOW_INSECURE_COOKIES"] = "false"

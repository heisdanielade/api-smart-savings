import os
import sys
from pathlib import Path

# Set dummy REDIS_URL to avoid errors during collection/import
# This must happen before app.core.config is imported
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# Add the project root directory to Python path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

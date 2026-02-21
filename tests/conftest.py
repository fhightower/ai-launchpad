import sys
from pathlib import Path

# Allow flat imports (e.g. "from config import read_config") to resolve
# against the project root, matching how the application itself runs.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

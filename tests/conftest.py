import sys
from pathlib import Path

# Make the `ai_launchpad` package importable when running tests directly
# (without installing the project), matching how the launch.py entry point runs.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

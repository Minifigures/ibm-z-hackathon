import sys
from pathlib import Path

# Make the backend package importable when pytest is run from the backend dir.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

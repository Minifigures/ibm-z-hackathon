import sys
from pathlib import Path

import pytest

# Make the backend package importable when pytest is run from the backend dir.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _reset_watsonx_state():
    """Reset cached watsonx client + RAG state between tests so cases are independent."""
    from app import disease_lookup, watsonx_client
    watsonx_client.reset()
    disease_lookup.clear_cache()
    yield
    watsonx_client.reset()
    disease_lookup.clear_cache()

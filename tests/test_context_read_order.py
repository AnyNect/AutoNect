"""Read-order coverage (2026-10-07). No server needed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_read_order_includes_quran_progress():
    """2026-10-07: the session-start protocol reads
    personal/quran_progress.md, so the Load Context attach list must
    include it, or the AI still has to fetch it."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.web import server
    rels = server.CONTEXT_READ_ORDER
    assert "personal/quran_progress.md" in rels, rels
    assert "FOR_AI.md" in rels, rels

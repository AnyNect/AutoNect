import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.text.compress import compress, verify, strip_ansi


def test_strips_ansi():
 assert strip_ansi(chr(27) + '[31m' + 'x' + chr(27) + '[0m') == 'x'


def test_collapses_runs():
 line = 'Downloading'
 src = chr(10).join([line]*5)
 out = compress(src)
 assert '(x5)' in out


def test_preserves_detail():
 src = 'error in /a/b.py:42' + chr(10) + 'sha 9f2a1c8b4e6d0a3f' + chr(10) + 'v1.2.3'
 out = compress(src)
 assert verify(src, out) == []
 assert '/a/b.py:42' in out
 assert '9f2a1c8b4e6d0a3f' in out


def test_verify_detects_loss():
 assert verify('hash abc1234', 'gone') != []


def test_never_grows_tiny():
 src = chr(10).join(['a']*3)
 assert len(compress(src)) <= len(src) + 1
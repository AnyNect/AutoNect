"""Custom dictionary correction for STT output.

The STT model has no hotword/word-boosting API (onnx-asr is a thin
inference wrapper).  This is the Chrome-dictionary approach: match a
sliding window of heard words against a list of alias spellings and
rewrite a confident hit to the canonical form.

Matching is fuzzy (rapidfuzz ratio) plus phonetic (Metaphone), so
'autonect', 'auto nect', 'ottonect' all resolve to 'AutoNect'.
Runs on every decode (partials and finals).
"""
import re
from pathlib import Path
from rapidfuzz import fuzz
import jellyfish

HERE = Path(__file__).parent
DICT_PATH = HERE / "dictionary.txt"

# A window must score at least this to be rewritten.
MIN_SCORE = 88.0
# Windows we consider (words).  1 catches single tokens, 2-4 catch
# multi-word aliases like 'auto nect'.
MAX_WIN = 4


def _load():
    terms = []  # (canonical, alias_lower, alias_nospace, alias_phon)
    if not DICT_PATH.exists():
        return terms
    for raw in DICT_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            canon = line
            aliases = [line]
        else:
            canon, rest = line.split("|", 1)
            canon = canon.strip()
            aliases = [canon] + [a.strip() for a in rest.split(",") if a.strip()]
        for a in aliases:
            al = a.lower()
            terms.append((canon, al, al.replace(" ", ""), jellyfish.metaphone(al)))
    return terms


_TERMS = _load()


def reload_vocab():
    global _TERMS
    _TERMS = _load()
    return len(_TERMS)


def _score(heard_words, terms):
    """Best (score, canonical) for the joined heard window."""
    joined = " ".join(heard_words)
    jl = joined.lower()
    jn = jl.replace(" ", "")
    jp = jellyfish.metaphone(joined)
    best = (0.0, None)
    for canon, al, an, ap in terms:
        # Spaced-form ratio (exact word boundaries matter).
        s_spaced = fuzz.ratio(jl, al)
        # Nospace ratio, PENALISED by length difference: without this,
        # 'auto nect is' -> 'autonectis' scores high against 'autonect'
        # and swallows the extra word.  Each stray char costs 8 points.
        s_nospace = fuzz.ratio(jn, an) - 8 * abs(len(jn) - len(an))
        # Metaphone, also length-gated.
        s_phon = (fuzz.ratio(jp, ap) - 8 * abs(len(jp) - len(ap))) if (jp and ap) else 0
        s = max(s_spaced, s_nospace, s_phon)
        if s > best[0]:
            best = (s, canon)
    return best


def correct(text: str) -> str:
    if not text or not _TERMS:
        return text
    # tokenise, keeping trailing punctuation attached to the token
    tokens = text.split()
    if not tokens:
        return text
    out = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        # try the longest window first so 'auto nect' beats 'auto'
        for w in range(min(MAX_WIN, n - i), 0, -1):
            win = tokens[i:i + w]
            # strip punctuation for matching only
            clean = [re.sub(r"^\W+|\W+$", "", t) for t in win]
            if not all(clean):
                continue
            score, canon = _score(clean, _TERMS)
            if canon and score >= MIN_SCORE:
                out.append(canon)
                i += w
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


if __name__ == "__main__":
    for t in ["so i opened autonect", "auto nect is running",
              "the auto next app", "hello world", "autonect"]:
        print(repr(t), "->", repr(correct(t)))

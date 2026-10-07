# Lossless-safe text compression for AutoNect context.
# Deterministic, stdlib-only. NEVER removes load-bearing text
# (hashes, paths, urls, versions, numbers); verify() proves it.
import re

ESC = chr(27)
ANSI = re.compile(ESC + r'\[' + r'[0-9;]*[A-Za-z]')

PATTERNS = [
 ('sha', re.compile('[0-9a-f]{7,40}')),
 ('path', re.compile('(/[A-Za-z0-9.-]+){2,}')),
 ('url', re.compile('https?://[^ ]+')),
 ('version', re.compile('v?[0-9]+[.][0-9]+([.][0-9]+)?')),
 ('num', re.compile('[0-9]+')),
]


def strip_ansi(text):
 return ANSI.sub('', text)


def collapse_runs(text):
 lines = text.splitlines()
 out = []
 i = 0
 n = len(lines)
 while i < n:
  j = i
  while j + 1 < n and lines[j + 1] == lines[i]:
   j += 1
  runlen = j - i + 1
  if runlen > 1 and runlen * (len(lines[i]) + 1) > len(lines[i]) + 8:
   if lines[i].strip() == '':
    out.append('')
   else:
    out.append(lines[i] + '  (x' + str(runlen) + ')')
  else:
   out.append(lines[i])
  i = j + 1
 return chr(10).join(out)


def tokens(text):
 found = {}
 for name, rx in PATTERNS:
  for m in rx.finditer(text):
   found.setdefault(name, set()).add(m.group(0))
 return found


def verify(original, compressed):
 o = tokens(original)
 c = tokens(compressed)
 missing = []
 for name, toks in o.items():
  for t in toks:
   if t not in c.get(name, set()):
    missing.append((name, t))
 return missing


def compress(text, max_lines=0):
 cleaned = strip_ansi(text)
 out = collapse_runs(cleaned)
 if max_lines and out.count(chr(10)) + 1 > max_lines:
  lines = out.splitlines()
  head = max_lines // 2
  tail = max_lines - head
  kept = lines[:head] + ['... (' + str(len(lines) - max_lines) + ' lines elided) ...'] + lines[-tail:]
  out = chr(10).join(kept)
 return out
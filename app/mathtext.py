"""Split prose into plain text and inline math for preview and HML output."""
import re


_EXPLICIT = re.compile(r'\$\$(.+?)\$\$|\$([^$]+)\$|\\\((.*?)\\\)|\\\[(.*?)\\\]', re.DOTALL)
_SCRIPT_PART = r'(?:_\{[^{}\s]{1,24}\}|\^[{][^{}\s]{1,24}[}]|_[A-Za-z0-9+\-]{1,8}|\^[A-Za-z0-9+\-]{1,8})'
_BARE_VARIABLE = re.compile(
    rf'(?<![A-Za-z0-9_./\\])([A-Za-z](?:{_SCRIPT_PART})+)(?![A-Za-z0-9_])'
)
_URL_OR_PATH = re.compile(
    r'(?i)(?:[a-z][a-z0-9+.-]*://|www\.)\S+'
    r'|(?:[a-z]:[\\/]|\\\\)\S+'
    r'|(?:\.\.?[\\/])\S+'
)


def _plain_segments(text):
    """Recognize bare scripted variables while preserving links and paths."""
    protected = [m.span() for m in _URL_OR_PATH.finditer(text)]
    out = []
    cursor = 0
    for match in _BARE_VARIABLE.finditer(text):
        start, end = match.span(1)
        if any(start < right and end > left for left, right in protected):
            continue
        # A bare physical variable can also be a file stem. Keep common
        # filename extensions such as V_0.png as ordinary prose.
        if re.match(r'\.[A-Za-z0-9]{1,8}(?:\.[A-Za-z0-9]{1,8})?(?=$|[\s,;:!?)}\]])', text[end:]):
            continue
        if start > cursor:
            out.append(('text', text[cursor:start]))
        out.append(('math', match.group(1)))
        cursor = end
    if cursor < len(text):
        out.append(('text', text[cursor:]))
    return out or [('text', text)]


def math_segments(value):
    """Return ordered (kind, text) spans; explicit dollars and bare variables render as math."""
    text = str(value or '')
    out = []
    cursor = 0
    for match in _EXPLICIT.finditer(text):
        out.extend(_plain_segments(text[cursor:match.start()]))
        out.append(('math', next(part for part in match.groups() if part is not None)))
        cursor = match.end()
    out.extend(_plain_segments(text[cursor:]))
    return [(kind, part) for kind, part in out if part]

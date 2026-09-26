"""Is a newer Qalam out?

One question to GitHub, asked after the window is already up. Nothing is
downloaded and nothing is installed. A check that fails - offline, throttled,
rate-limited, behind a proxy that eats it - returns nothing at all, because
"could not tell" and "you are current" are the same answer as far as the window
is concerned. Kept free of Qt so the CLI can ask the same way the GUI does.
"""

import json
import urllib.error
import urllib.request

from . import __version__

REPO = "aghamorad/qalam"
RELEASES = f"https://github.com/{REPO}/releases"

# Long enough for a slow link, short enough that a dead one is not noticed. The
# request rides a worker thread, so this is a ceiling on the thread, not on the
# window.
TIMEOUT = 9


def parts(version: str) -> list[int]:
    """"v1.2.10" -> [1, 2, 10]. Anything unparseable counts as zero."""
    out: list[int] = []
    for piece in str(version).strip().lstrip("vV").split("."):
        digits = "".join(c for c in piece if c.isdigit())
        out.append(int(digits) if digits else 0)
    return out


def is_newer(candidate: str, mine: str) -> bool:
    a, b = parts(candidate), parts(mine)
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else 0
        y = b[i] if i < len(b) else 0
        if x != y:
            return x > y
    return False


def latest(timeout: int = TIMEOUT) -> str:
    """The tag of the newest release, bare ("0.2.1"), or "" if unknown.

    Only a published, non-draft, non-prerelease release counts - GitHub's
    `releases/latest` already excludes drafts and prereleases, which is the
    behaviour wanted here: a release candidate is not something to push a
    working copy's owner at.
    """
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"qalam/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return ""
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    return str(payload.get("tag_name") or "").strip().lstrip("vV")


def newer_than_mine(timeout: int = TIMEOUT) -> str:
    """The newer release's number, or "" when there is none or no answer."""
    found = latest(timeout)
    return found if found and is_newer(found, __version__) else ""

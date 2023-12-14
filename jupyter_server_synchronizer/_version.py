"""
store the current version info of the synchronizer.
"""
import re
from typing import List

# Version string must appear intact for automatic versioning
__version__ = "0.1.0.dev0"

# Build up version_info tuple for backwards compatibility
pattern = r"(?P<major>\d+).(?P<minor>\d+).(?P<patch>\d+)(?P<rest>.*)"
match = re.match(pattern, __version__)
assert match is not None  # noqa: S101
parts: List[object] = [int(match[part]) for part in ["major", "minor", "patch"]]
if match["rest"]:
    parts.append(match["rest"])
version_info = tuple(parts)

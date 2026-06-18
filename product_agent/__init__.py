"""Compatibility package for repository-root deployments.

The source tree keeps modules such as `api/` and `services/` at the repository
root while importing them as `product_agent.api`. Some CI/deploy platforms check
the repo out into a directory that is not named `product_agent`; extending the
package search path keeps those imports stable.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_repo_root_path = str(_REPO_ROOT)

if _repo_root_path not in __path__:
    __path__.append(_repo_root_path)

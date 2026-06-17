from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


def _ensure_outer_project_root() -> Path:
    """
    Make `product_agent` importable even when this script is launched from
    inside the standalone `product_agent/` repo.
    """
    repo_root = Path(__file__).resolve().parent
    outer_root = repo_root.parent
    if str(outer_root) not in sys.path:
        sys.path.insert(0, str(outer_root))
    return repo_root


def main() -> None:
    repo_root = _ensure_outer_project_root()
    from product_agent.env_loader import load_product_agent_dotenv

    load_product_agent_dotenv(repo_root / ".env")

    parser = argparse.ArgumentParser(
        description="Start the Product Agent FastAPI backend from inside the product_agent repo."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to.")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to.")
    parser.add_argument("--no-reload", action="store_true", help="Disable hot reload.")
    args = parser.parse_args()

    uvicorn_kwargs = {
        "host": args.host,
        "port": args.port,
        "reload": not args.no_reload,
    }
    if not args.no_reload:
        uvicorn_kwargs["reload_dirs"] = [str(repo_root)]

    uvicorn.run("product_agent.api.fastapi_app:app", **uvicorn_kwargs)


if __name__ == "__main__":
    main()

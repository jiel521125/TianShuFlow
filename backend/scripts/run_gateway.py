"""Start the TianShu gateway with a Windows-compatible event loop.

uvicorn 16 forces ``ProactorEventLoop`` on Windows, which psycopg3's
async mode does not support (it requires ``add_reader``). To run the
gateway against PostgreSQL on Windows, create a ``SelectorEventLoop``
explicitly and drive the uvicorn ``Server`` on it.

Usage (from ``backend/``):

    python scripts/run_gateway.py [--host 127.0.0.1] [--port 8001]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from uvicorn import Config, Server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TianShu gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    config = Config(
        "app.gateway.app:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    server = Server(config)

    if sys.platform == "win32":
        # WindowsSelectorEventLoopPolicy -> asyncio.new_event_loop() returns a
        # SelectorEventLoop, which psycopg3 can use in async mode.
        selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if selector_policy is not None:
            asyncio.set_event_loop_policy(selector_policy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()

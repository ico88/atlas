"""Node Agent entrypoint: register once, then heartbeat on an interval."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import signal
import sys

import httpx

from agent import __version__
from agent.client import (
    ControlPlaneClient,
    build_heartbeat_payload,
    build_register_payload,
)
from agent.config import AgentConfig
from agent.hardware import collect_hardware, collect_health

logger = logging.getLogger("node-agent")

_shutdown = asyncio.Event()


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s node-agent %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


async def _register_with_retry(client: ControlPlaneClient, config: AgentConfig) -> None:
    payload = build_register_payload(config, collect_hardware())
    attempt = 0
    while not _shutdown.is_set():
        attempt += 1
        try:
            node = await client.register(payload)
            logger.info(
                "registered node_id=%s as db_id=%s", config.node_id, node.get("id")
            )
            return
        except (httpx.HTTPError, OSError) as exc:
            if config.register_max_retries and attempt >= config.register_max_retries:
                raise
            delay = min(30.0, 2.0 * attempt)
            logger.warning(
                "registration failed (attempt %s): %s — retrying in %.0fs",
                attempt,
                exc,
                delay,
            )
            await _wait(delay)


async def _wait(seconds: float) -> None:
    """Sleep, but wake immediately on shutdown."""

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_shutdown.wait(), timeout=seconds)


async def run(config: AgentConfig | None = None) -> None:
    config = config or AgentConfig.from_env()
    logger.info(
        "starting node agent v%s node_id=%s control_plane=%s caps=%s",
        __version__,
        config.node_id,
        config.control_plane_url,
        ",".join(config.capabilities) or "-",
    )

    client = ControlPlaneClient(config)
    try:
        await _register_with_retry(client, config)
        while not _shutdown.is_set():
            await _wait(config.heartbeat_interval)
            if _shutdown.is_set():
                break
            payload = build_heartbeat_payload(collect_health())
            try:
                await client.heartbeat(config.node_id, payload)
                logger.info("heartbeat sent: %s", json.dumps(payload["status"]))
            except httpx.HTTPStatusError as exc:
                # A 404 means the control plane lost our record — re-register.
                if exc.response.status_code == 404:
                    logger.warning("node unknown to control plane; re-registering")
                    await _register_with_retry(client, config)
                else:
                    logger.warning("heartbeat failed: %s", exc)
            except (httpx.HTTPError, OSError) as exc:
                logger.warning("heartbeat failed: %s", exc)
    finally:
        await client.aclose()
        logger.info("node agent stopped")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # pragma: no cover
            loop.add_signal_handler(sig, _shutdown.set)


def main() -> None:
    _configure_logging()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()

"""Transport Intelligence Daemon — glowny entry point.

Uruchomienie:
    python -m src.agents.daemon

Funkcjonalnosc:
- Uruchamia AgentScheduler (APScheduler) z jobami 24/7
- Uruchamia FastAPI (uvicorn) w osobnym task
- Ctrl+C → graceful shutdown
- PID file: /tmp/transport-intelligence.pid
- Loguje status co minute
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import uvicorn
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daemon")

CONFIG_PATH = Path(__file__).parent / "daemon_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


class TransportDaemon:
    """Glowny daemon systemu Transport Intelligence.

    Laczy scheduler (agenty) z API serwerem w jednym procesie.
    """

    def __init__(self, port_override: int | None = None):
        self.config = load_config()
        if port_override is not None:
            self.config.setdefault("api", {})["port"] = port_override
        self.pid_file = self.config.get("pid_file", "/tmp/transport-intelligence.pid")
        self._shutdown_event = asyncio.Event()
        self._scheduler = None
        self._uvicorn_server = None

    # ── PID file management ──────────────────────────────────────────────

    def _check_existing_pid(self):
        """Sprawdza czy daemon juz nie dziala."""
        if not os.path.exists(self.pid_file):
            return

        with open(self.pid_file) as f:
            old_pid = f.read().strip()

        if not old_pid:
            return

        try:
            old_pid = int(old_pid)
            # Check if process is actually running
            os.kill(old_pid, 0)
            logger.error(
                "Daemon already running (PID %d). "
                "Kill it first or remove %s",
                old_pid, self.pid_file,
            )
            sys.exit(1)
        except (OSError, ValueError):
            # Process not running — stale PID file
            logger.warning("Stale PID file found (PID %s) — removing", old_pid)
            os.remove(self.pid_file)

    def _write_pid(self):
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))
        logger.info("PID file written: %s (PID %d)", self.pid_file, os.getpid())

    def _remove_pid(self):
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)
            logger.info("PID file removed: %s", self.pid_file)

    # ── Signal handlers ──────────────────────────────────────────────────

    def _setup_signals(self, loop: asyncio.AbstractEventLoop):
        """Rejestruje handlery dla SIGINT i SIGTERM."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal, sig)

    def _handle_signal(self, sig):
        signame = signal.Signals(sig).name
        logger.info("Received %s — initiating graceful shutdown...", signame)
        self._shutdown_event.set()

    # ── Uvicorn Server ───────────────────────────────────────────────────

    async def _run_api(self):
        """Uruchamia FastAPI via uvicorn."""
        api_cfg = self.config.get("api", {})
        host = api_cfg.get("host", "0.0.0.0")
        port = api_cfg.get("port", 8000)

        config = uvicorn.Config(
            "src.api.main:app",
            host=host,
            port=port,
            log_level="info",
            access_log=False,
        )
        self._uvicorn_server = uvicorn.Server(config)

        logger.info("Starting API server on %s:%d", host, port)
        try:
            await self._uvicorn_server.serve()
        except SystemExit:
            logger.warning(
                "API server failed to start (port %d may be in use). "
                "Scheduler continues running without API.", port,
            )
        except Exception as e:
            logger.warning("API server error: %s — scheduler continues", e)

    async def _stop_api(self):
        """Zatrzymuje uvicorn."""
        if self._uvicorn_server:
            logger.info("Stopping API server...")
            self._uvicorn_server.should_exit = True

    # ── Status logger ────────────────────────────────────────────────────

    async def _status_loop(self):
        """Loguje status systemu co minute."""
        interval = self.config.get("logging", {}).get("status_interval_seconds", 60)
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=interval
                )
                break  # shutdown event set
            except asyncio.TimeoutError:
                pass  # timeout = time to log

            if self._scheduler:
                logger.info("System running: %s", self._scheduler.get_stats_summary())

    # ── Main run ─────────────────────────────────────────────────────────

    async def run(self):
        """Glowna petla daemona."""
        self._check_existing_pid()
        self._write_pid()

        loop = asyncio.get_running_loop()
        self._setup_signals(loop)

        logger.info("=" * 70)
        logger.info("TRANSPORT INTELLIGENCE DAEMON")
        logger.info("=" * 70)

        # Start scheduler
        from src.agents.scheduler import AgentScheduler
        self._scheduler = AgentScheduler(self.config)
        self._scheduler.start()

        # Start API + status loop + wait for shutdown
        api_task = asyncio.create_task(self._run_api())
        status_task = asyncio.create_task(self._status_loop())

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # ── Graceful shutdown ────────────────────────────────────────────
        logger.info("=" * 70)
        logger.info("GRACEFUL SHUTDOWN")
        logger.info("=" * 70)

        # Stop scheduler (waits for current jobs, max 30s)
        try:
            self._scheduler.shutdown(wait=True)
        except Exception as e:
            logger.error("Scheduler shutdown error: %s", e)

        # Stop API
        await self._stop_api()

        # Cancel tasks
        status_task.cancel()
        try:
            await asyncio.wait_for(api_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            api_task.cancel()

        self._remove_pid()

        logger.info("=" * 70)
        logger.info("DAEMON STOPPED")
        logger.info("=" * 70)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Transport Intelligence Daemon")
    parser.add_argument("--port", type=int, default=None, help="API server port (overrides daemon_config.yaml)")
    args = parser.parse_args()

    daemon = TransportDaemon(port_override=args.port)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        # Already handled via signal handler, but just in case
        logger.info("KeyboardInterrupt — exiting")
        daemon._remove_pid()


if __name__ == "__main__":
    main()

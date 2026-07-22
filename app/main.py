#!/usr/bin/env python3

import requests
import logging.handlers
from pathlib import Path

from litestar import Litestar, get
from litestar.controller import Controller
from litestar.datastructures import State
from litestar.logging import LoggingConfig
from litestar.static_files.config import StaticFilesConfig


class GPSController(Controller):

    @get("/gps", sync_to_thread=True)
    def get_gps(self, state: State) -> dict:

        # Ask MAVLink2Rest for the latest GLOBAL_POSITION_INT message
        response = requests.get(
            f"{state.mavlink_url}/vehicles/1/components/1/messages/GLOBAL_POSITION_INT"
        )
        response.raise_for_status()

        message = response.json()["message"]

        return {
            "latitude": message["lat"] / 1e7,
            "longitude": message["lon"] / 1e7,
            "heading": message["hdg"] / 100,
            "altitude": message["alt"] / 1000,
        }


logging_config = LoggingConfig(
    loggers={
        __name__: dict(
            level="INFO",
            handlers=["queue_listener"],
        )
    },
)

log_dir = Path("/app/logs")
log_dir.mkdir(parents=True, exist_ok=True)

fh = logging.handlers.RotatingFileHandler(
    log_dir / "lumber.log",
    maxBytes=2**16,
    backupCount=1,
)

app = Litestar(
    route_handlers=[GPSController],

    state=State(
        {
            "mavlink_url": "http://host.docker.internal:6040/v1/mavlink"
        }
    ),

    static_files_config=[
        StaticFilesConfig(
            directories=["app/static"],
            path="/",
            html_mode=True,
        )
    ],

    logging_config=logging_config,
)

app.logger.addHandler(fh)

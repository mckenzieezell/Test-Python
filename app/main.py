#!/usr/bin/env python3

import requests

from litestar import Litestar, get
from litestar.controller import Controller
from litestar.static_files.config import StaticFilesConfig


class GPSController(Controller):

    @get("/gps", sync_to_thread=True)
    def get_gps(self) -> dict:

        # Ask MAVLink2Rest for the latest GLOBAL_POSITION_INT message
        response = requests.get("http://blueos.local/mavlink2rest/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT")
        response.raise_for_status()

        message = response.json()["message"]

        return {
            "latitude": message["lat"] / 1e7,
            "longitude": message["lon"] / 1e7,
            "heading": message["hdg"] / 100,
        }


app = Litestar(
    route_handlers=[GPSController],
    static_files_config=[
        StaticFilesConfig(
            directories=["app/static"],
            path="/",
            html_mode=True,
        )
    ],
)



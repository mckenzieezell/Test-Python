#!/usr/bin/env python3
import requests
from litestar import Litestar, get
from litestar.controller import Controller
from litestar.static_files.config import StaticFilesConfig

class GPSController(Controller):
    @get("/gps", sync_to_thread=True)
    def get_gps(self) -> dict:
        response = requests.get("http://host.docker.internal/mavlink2rest/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT")
        response.raise_for_status()
        message = response.json()["message"]

        lat = message["lat"] / 1e7
        lon = message["lon"] / 1e7

        # lat/lon come back as exactly 0,0 when there's no GPS data at all
        has_fix = not (lat == 0 and lon == 0)

        return {
            "has_fix": has_fix,
            "latitude": lat if has_fix else None,
            "longitude": lon if has_fix else None,
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

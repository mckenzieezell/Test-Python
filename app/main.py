#!/usr/bin/env python3
import requests
from litestar import Litestar, get
from litestar.controller import Controller
from litestar.static_files.config import StaticFilesConfig
from litestar.exceptions import HTTPException


class GPSController(Controller):
    @get("/gps", sync_to_thread=True)
    def get_gps(self) -> dict:
        # Ask MAVLink2Rest for the latest GLOBAL_POSITION_INT message
        try:
            response = requests.get(
                "http://host.docker.internal/mavlink2rest/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT",
                timeout=2,
            )
            response.raise_for_status()
            message = response.json()["message"]
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"MAVLink2Rest unreachable: {e}")
        except KeyError as e:
            raise HTTPException(status_code=502, detail=f"Missing key in response: {e}")

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

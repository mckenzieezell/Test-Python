#!/usr/bin/env python3
import requests
from litestar import Litestar, get
from litestar.controller import Controller
from litestar.static_files.config import StaticFilesConfig
from litestar.exceptions import HTTPException


MAVLINK2REST_BASE = "http://host.docker.internal/mavlink2rest/mavlink/vehicles/1/components/1/messages"

# GPS_RAW_INT fix_type values: 0=no GPS, 1=no fix, 2=2D fix, 3=3D fix, 4/5=DGPS/RTK
MIN_USABLE_FIX_TYPE = 3


class GPSController(Controller):
    @get("/gps", sync_to_thread=True)
    def get_gps(self) -> dict:
        try:
            gps_raw_response = requests.get(f"{MAVLINK2REST_BASE}/GPS_RAW_INT", timeout=2)
            gps_raw_response.raise_for_status()
            fix_type = gps_raw_response.json()["message"]["fix_type"]
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"MAVLink2Rest unreachable: {e}")
        except KeyError as e:
            raise HTTPException(status_code=502, detail=f"Missing key in GPS_RAW_INT response: {e}")

        if fix_type < MIN_USABLE_FIX_TYPE:
            return {
                "has_fix": False,
                "fix_type": fix_type,
                "latitude": None,
                "longitude": None,
                "heading": None,
            }

        try:
            response = requests.get(f"{MAVLINK2REST_BASE}/GLOBAL_POSITION_INT", timeout=2)
            response.raise_for_status()
            message = response.json()["message"]
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"MAVLink2Rest unreachable: {e}")
        except KeyError as e:
            raise HTTPException(status_code=502, detail=f"Missing key in response: {e}")

        return {
            "has_fix": True,
            "fix_type": fix_type,
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

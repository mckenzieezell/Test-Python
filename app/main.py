#!/usr/bin/env python3
import requests
from litestar import Litestar, get, post
from litestar.controller import Controller
from litestar.static_files.config import StaticFilesConfig

MAVLINK2REST_BASE = "http://host.docker.internal/mavlink2rest"

# ArduRover custom mode numbers
ROVER_MODES = {
    "manual": 0,
    "acro": 1,
    "steering": 3,
    "hold": 4,
    "loiter": 5,
    "follow": 6,
    "simple": 7,
    "auto": 10,
    "rtl": 11,
    "smart_rtl": 12,
    "guided": 15,
}
ROVER_MODES_BY_NUMBER = {v: k for k, v in ROVER_MODES.items()}


class GPSController(Controller):
    @get("/gps", sync_to_thread=True)
    def get_gps(self) -> dict:
        response = requests.get(
            f"{MAVLINK2REST_BASE}/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT"
        )
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


class ModeController(Controller):
    @post("/mode/{mode_name:str}", sync_to_thread=True)
    def set_mode(self, mode_name: str) -> dict:
        mode_num = ROVER_MODES.get(mode_name.lower())
        if mode_num is None:
            return {"status": "error", "message": f"unknown mode: {mode_name}"}

        payload = {
            "header": {"system_id": 255, "component_id": 0, "sequence": 0},
            "message": {
                "type": "COMMAND_LONG",
                "param1": 1,  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
                "param2": mode_num,
                "param3": 0,
                "param4": 0,
                "param5": 0,
                "param6": 0,
                "param7": 0,
                "command": {"type": "MAV_CMD_DO_SET_MODE"},
                "target_system": 1,
                "target_component": 1,
                "confirmation": 0,
            },
        }
        response = requests.post(f"{MAVLINK2REST_BASE}/mavlink", json=payload)
        response.raise_for_status()
        return {"status": "ok", "mode": mode_name.upper()}

    @get("/mode/current", sync_to_thread=True)
    def get_current_mode(self) -> dict:
        response = requests.get(
            f"{MAVLINK2REST_BASE}/mavlink/vehicles/1/components/1/messages/HEARTBEAT"
        )
        response.raise_for_status()
        message = response.json()["message"]
        custom_mode = message["custom_mode"]
        mode_name = ROVER_MODES_BY_NUMBER.get(custom_mode, "unknown")
        return {
            "custom_mode": custom_mode,
            "mode_name": mode_name.upper(),
        }


app = Litestar(
    route_handlers=[GPSController, ModeController],
    static_files_config=[
        StaticFilesConfig(
            directories=["app/static"],
            path="/",
            html_mode=True,
        )
    ],
)

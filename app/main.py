#!/usr/bin/env python3

import requests
from litestar import Litestar, get, post
from litestar.controller import Controller
from litestar.response import Response

from swarm import swarm_listener

MAVLINK2REST_BASE = "http://host.docker.internal/mavlink2rest/v1"

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


class IndexController(Controller):
    @get("/", sync_to_thread=False)
    def index(self) -> Response:
        with open("app/static/index.html", "r", encoding="utf-8") as f:
            return Response(
                content=f.read(),
                media_type="text/html",
            )


class RegisterServiceController(Controller):
    @get("/register_service", sync_to_thread=False)
    def register_service(self) -> dict:
        return {
            "name": "Test GPS",
            "description": "Displays GPS position, lets you switch vehicle modes, and shows live LoRa/TDMA swarm positions",
            "icon": "mdi-map-marker",
            "company": "URI RCUE Lab",
            "version": "1.0.0",
            "webpage": "https://github.com/mckenzieezell/Test-Python",
            "api": "",
        }


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

        # lat/lon come back as exactly 0,0 when there's no GPS fix
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
            return {
                "status": "error",
                "message": f"unknown mode: {mode_name}",
            }

        payload = {
            "header": {
                "system_id": 255,
                "component_id": 0,
                "sequence": 0,
            },
            "message": {
                "type": "COMMAND_LONG",
                "param1": 1,  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
                "param2": mode_num,
                "param3": 0,
                "param4": 0,
                "param5": 0,
                "param6": 0,
                "param7": 0,
                "command": {
                    "type": "MAV_CMD_DO_SET_MODE"
                },
                "target_system": 1,
                "target_component": 1,
                "confirmation": 0,
            },
        }

        response = requests.post(
            f"{MAVLINK2REST_BASE}/mavlink",
            json=payload,
        )
        response.raise_for_status()

        return {
            "status": "ok",
            "mode": mode_name.upper(),
        }

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


class WaypointController(Controller):
    @post("/waypoint", sync_to_thread=True)
    def set_waypoint(self, data: dict) -> dict:
        try:
            lat = float(data["latitude"])
            lon = float(data["longitude"])
        except (KeyError, TypeError, ValueError):
            return {
                "status": "error",
                "message": "latitude and longitude are required",
            }

        # Check for GPS fix before doing anything else
        try:
            gps_response = requests.get(
                f"{MAVLINK2REST_BASE}/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT"
            )
            gps_response.raise_for_status()
            gps_message = gps_response.json()["message"]

            current_lat = gps_message["lat"] / 1e7
            current_lon = gps_message["lon"] / 1e7
            has_fix = not (current_lat == 0 and current_lon == 0)

        except (requests.HTTPError, requests.ConnectionError, KeyError) as e:
            return {
                "status": "error",
                "message": f"could not check GPS status: {e}",
            }

        if not has_fix:
            return {
                "status": "error",
                "message": "no GPS fix — vehicle needs a GPS lock before it can navigate to a waypoint",
            }

        # Switch to GUIDED mode
        mode_payload = {
            "header": {
                "system_id": 255,
                "component_id": 0,
                "sequence": 0,
            },
            "message": {
                "type": "COMMAND_LONG",
                "param1": 1,
                "param2": ROVER_MODES["guided"],
                "param3": 0,
                "param4": 0,
                "param5": 0,
                "param6": 0,
                "param7": 0,
                "command": {
                    "type": "MAV_CMD_DO_SET_MODE"
                },
                "target_system": 1,
                "target_component": 1,
                "confirmation": 0,
            },
        }

        try:
            mode_response = requests.post(
                f"{MAVLINK2REST_BASE}/mavlink",
                json=mode_payload,
            )
            mode_response.raise_for_status()

        except requests.HTTPError as e:
            return {
                "status": "error",
                "message": f"mode switch failed: {e}",
                "mavlink2rest_response": mode_response.text,
            }

        # POSITION_TARGET_TYPEMASK bits:
        # ignore vx, vy, vz, afx, afy, afz, yaw, yaw_rate
        POSITION_ONLY_TYPE_MASK = 0x0DF8

        waypoint_payload = {
            "header": {
                "system_id": 255,
                "component_id": 0,
                "sequence": 0,
            },
            "message": {
                "type": "SET_POSITION_TARGET_GLOBAL_INT",
                "time_boot_ms": 0,
                "target_system": 1,
                "target_component": 1,
                "coordinate_frame": {
                    "type": "MAV_FRAME_GLOBAL_RELATIVE_ALT"
                },
                "type_mask": {
                    "bits": POSITION_ONLY_TYPE_MASK
                },
                "lat_int": int(lat * 1e7),
                "lon_int": int(lon * 1e7),
                "alt": 0,
                "vx": 0,
                "vy": 0,
                "vz": 0,
                "afx": 0,
                "afy": 0,
                "afz": 0,
                "yaw": 0,
                "yaw_rate": 0,
            },
        }

        try:
            response = requests.post(
                f"{MAVLINK2REST_BASE}/mavlink",
                json=waypoint_payload,
            )
            response.raise_for_status()

        except requests.HTTPError as e:
            return {
                "status": "error",
                "message": f"waypoint send failed: {e}",
                "mavlink2rest_response": response.text,
            }

        return {
            "status": "ok",
            "latitude": lat,
            "longitude": lon,
        }

class StopController(Controller):
    @post("/stop", sync_to_thread=True)
    def stop(self) -> dict:
        # HOLD mode: stop navigating to any target, hold current position
        payload = {
            "header": {"system_id": 255, "component_id": 0, "sequence": 0},
            "message": {
                "type": "COMMAND_LONG",
                "param1": 1,
                "param2": ROVER_MODES["hold"],
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
        return {"status": "ok", "mode": "HOLD"}

    @post("/disarm", sync_to_thread=True)
    def disarm(self) -> dict:
        # MAV_CMD_COMPONENT_ARM_DISARM, param1=0 -> disarm
        payload = {
            "header": {"system_id": 255, "component_id": 0, "sequence": 0},
            "message": {
                "type": "COMMAND_LONG",
                "param1": 0,  # 0 = disarm, 1 = arm
                "param2": 0,
                "param3": 0,
                "param4": 0,
                "param5": 0,
                "param6": 0,
                "param7": 0,
                "command": {"type": "MAV_CMD_COMPONENT_ARM_DISARM"},
                "target_system": 1,
                "target_component": 1,
                "confirmation": 0,
            },
        }
        response = requests.post(f"{MAVLINK2REST_BASE}/mavlink", json=payload)
        response.raise_for_status()
        return {"status": "ok", "action": "disarmed"}


class SwarmController(Controller):
    @get("/swarm", sync_to_thread=False)
    def get_swarm(self) -> dict:
        """Latest known position/status for every module heard over the LoRa/TDMA link."""
        return swarm_listener.snapshot()


def start_swarm_listener() -> None:
    swarm_listener.start()


def stop_swarm_listener() -> None:
    swarm_listener.stop()


app = Litestar(
    route_handlers=[
        IndexController,
        RegisterServiceController,
        GPSController,
        ModeController,
        WaypointController,
        StopController,
        SwarmController,
    ],
    on_startup=[start_swarm_listener],
    on_shutdown=[stop_swarm_listener],
)

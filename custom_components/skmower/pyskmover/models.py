"""
Data models for pyskmover.

All fields are derived from the actual JSON payloads observed in
sk-mover-komunikacja.log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class WorkMode(IntEnum):
    """
    Values used in POST /api/app_mower/device/setWorkStatus  {"mode": <N>}.

    Observed in traffic:
      0  – start mowing
      1  – stop
      3  – return to dock
      4  – border / edge mode
    """

    STOP = 0
    MOWING = 1
    DOCK = 2
    BORDER = 4


class WorkStatusCode(IntEnum):
    """workStatusCode reported in the device status response."""

    READY = 0
    MOWING = 1
    RETURNING = 2
    CHARGING = 3
    ERROR = 4
    PAUSED = 5
    BORDER = 7


# ---------------------------------------------------------------------------
# Authentication / user helpers
# ---------------------------------------------------------------------------


@dataclass
class TokenResponse:
    """
    Parsed response from POST /api/auth/oauth/token.

    The request uses HTTP Basic auth with client-id "app:app" (base-64:
    YXBwOmFwcA==) and form body:
        username=<email>&password=<pwd>&grant_type=password&scope=server
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None

    # Additional fields returned by the server are stored as-is.
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "TokenResponse":
        obj = cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            expires_in=data.get("expires_in"),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
        )
        obj.extra = {
            k: v
            for k, v in data.items()
            if k not in ("access_token", "token_type", "expires_in", "refresh_token", "scope")
        }
        return obj


@dataclass
class UserAppInfo:
    """
    Response from GET /api/admin/user/app/info.

    Used to retrieve the appId (e.g. "12385068") that must accompany every
    device command.
    """

    app_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    # Additional fields returned by the server are stored as-is.
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "UserAppInfo":
        obj = cls(
            app_id=str(data["appId"]) if data.get("appId") is not None else None,
            username=data.get("username"),
            email=data.get("email"),
        )
        obj.extra = {
            k: v
            for k, v in data.items()
            if k not in ("appId", "username", "email")
        }
        return obj


# ---------------------------------------------------------------------------
# Device schedule
# ---------------------------------------------------------------------------


@dataclass
class DeviceSchedule:
    """
    One entry from the deviceScheduleList array embedded in both
    DeviceSetting and DeviceStatus responses.

    Fields map directly to the JSON keys observed in the log.
    """

    id: str
    device_id: str
    device_setting_id: str
    day_of_week: int          # 1=Monday … 7=Sunday
    start_at: str             # "HH:MM:SS"
    end_at: str               # "HH:MM:SS"
    trim_flag: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceSchedule":
        return cls(
            id=d["id"],
            device_id=d["deviceId"],
            device_setting_id=d["deviceSettingId"],
            day_of_week=int(d["dayOfWeek"]),
            start_at=d["startAt"],
            end_at=d["endAt"],
            trim_flag=bool(d.get("trimFlag", False)),
            created_at=d.get("createdAt"),
            updated_at=d.get("updatedAt"),
        )


# ---------------------------------------------------------------------------
# Device setting  (GET /api/app_mower/device-setting/{deviceSn})
# ---------------------------------------------------------------------------


@dataclass
class DeviceSetting:
    """
    Full device configuration returned by
    GET /api/app_mower/device-setting/{deviceSn}.

    All fields are populated from the JSON response body observed in the log.
    """

    # Identity
    id: str
    device_id: str
    device_sn: str
    device_name: str

    # Rain settings
    rain_delay_duration: str = "0"
    rain_flag: bool = False

    # Connectivity / UI
    language: int = 0
    ota_flag: Optional[bool] = None
    online_flag: bool = False
    ota_auto_flag: bool = False
    shareable_flag: bool = False

    # Zone settings
    zone_open_flag: bool = False
    zone_automatic_flag: bool = False
    zone_first_percentage: int = 0
    zone_second_percentage: int = 0
    zone_third_percentage: int = 0
    zone_fourth_percentage: int = 0
    zone_ex_flag: int = 0

    # Meter / border lengths
    meter_first: int = 0
    meter_second: int = 0
    meter_third: int = 0
    meter_four: int = 0

    # Zone proportions
    pro_first: int = 25
    pro_second: int = 25
    pro_third: int = 25
    pro_four: int = 25

    # Border
    border_length: int = 0

    # Schedule / automation
    schedule_auto_flag: bool = False

    # LED
    led_flag: bool = False
    led_color_code: Optional[str] = None
    led_mode_code: Optional[str] = None
    led_mode_name: Optional[str] = None
    led_start: Optional[str] = None
    led_end: Optional[str] = None
    led_night_flag: bool = False

    # GPS
    gps_flag: bool = False
    gps_long: Optional[float] = None
    gps_lat: Optional[float] = None

    # Time zone
    time_auto_flag: bool = False
    time_zone_code: Optional[str] = None
    time_zone_flag: bool = False
    time_zone_id: Optional[str] = None
    daylight_time_flag: bool = False
    now_time: Optional[str] = None

    # Misc
    ultra_flag: bool = False
    ultra_lv: int = 0
    pause: bool = False

    # Capability flags (from device-configuration)
    multizone_support: Optional[int] = None
    rain_support: Optional[int] = None
    ultra_support: Optional[int] = None
    led_support: Optional[int] = None
    gps_support: Optional[int] = None

    # Schedules
    device_schedule_list: List[DeviceSchedule] = field(default_factory=list)

    # Timestamps
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceSetting":
        schedules = [
            DeviceSchedule.from_dict(s)
            for s in d.get("deviceScheduleList", [])
        ]
        return cls(
            id=d["id"],
            device_id=d["deviceId"],
            device_sn=d["deviceSn"],
            device_name=d.get("deviceName", ""),
            rain_delay_duration=str(d.get("rainDelayDuration", "0")),
            rain_flag=bool(d.get("rainFlag", False)),
            language=int(d.get("language", 0)),
            ota_flag=d.get("otaFlag"),
            online_flag=bool(d.get("onlineFlag", False)),
            ota_auto_flag=bool(d.get("otaAutoFlag", False)),
            shareable_flag=bool(d.get("shareableFlag", False)),
            zone_open_flag=bool(d.get("zoneOpenFlag", False)),
            zone_automatic_flag=bool(d.get("zoneAutomaticFlag", False)),
            zone_first_percentage=int(d.get("zoneFirstPercentage", 0)),
            zone_second_percentage=int(d.get("zoneSecondPercentage", 0)),
            zone_third_percentage=int(d.get("zoneThirdPercentage", 0)),
            zone_fourth_percentage=int(d.get("zoneFourthPercentage", 0)),
            zone_ex_flag=int(d.get("zoneExFlag", 0)),
            meter_first=int(d.get("meterFirst", 0)),
            meter_second=int(d.get("meterSecond", 0)),
            meter_third=int(d.get("meterThird", 0)),
            meter_four=int(d.get("meterFour", 0)),
            pro_first=int(d.get("proFirst", 25)),
            pro_second=int(d.get("proSecond", 25)),
            pro_third=int(d.get("proThird", 25)),
            pro_four=int(d.get("proFour", 25)),
            border_length=int(d.get("borderLength", 0)),
            schedule_auto_flag=bool(d.get("scheduleAutoFlag", False)),
            led_flag=bool(d.get("ledFlag", False)),
            led_color_code=d.get("ledColorCode"),
            led_mode_code=d.get("ledModeCode"),
            led_mode_name=d.get("ledModeName"),
            led_start=d.get("ledStart"),
            led_end=d.get("ledEnd"),
            led_night_flag=bool(d.get("ledNightFlag", False)),
            gps_flag=bool(d.get("gpsFlag", False)),
            gps_long=d.get("gpsLong"),
            gps_lat=d.get("gpsLat"),
            time_auto_flag=bool(d.get("timeAutoFlag", False)),
            time_zone_code=d.get("timeZoneCode"),
            time_zone_flag=bool(d.get("timeZoneFlag", False)),
            time_zone_id=d.get("timeZoneId"),
            daylight_time_flag=bool(d.get("daylightTimeFlag", False)),
            now_time=d.get("nowTime"),
            ultra_flag=bool(d.get("ultraFlag", False)),
            ultra_lv=int(d.get("ultraLv", 0)),
            pause=bool(d.get("pause", False)),
            multizone_support=d.get("multizone"),
            rain_support=d.get("rain"),
            ultra_support=d.get("ultra"),
            led_support=d.get("led"),
            gps_support=d.get("gps"),
            device_schedule_list=schedules,
            created_at=d.get("createdAt"),
            updated_at=d.get("updatedAt"),
        )


# ---------------------------------------------------------------------------
# Device status  (response from GET /api/app_mower/device-setting/{sn}
#                 — the second, shorter variant observed in the log that
#                   carries real-time operational data)
# ---------------------------------------------------------------------------


@dataclass
class DeviceStatus:
    """
    Real-time operational state returned alongside (or in place of) the full
    DeviceSetting in the periodic poll response.

    Observed JSON fields from the log response payload.
    """

    device_id: str
    device_sn: str
    device_name: str

    # Work state
    work_status_code: str = "0"
    work_status_name: str = "idle"

    # Schedule
    schedule_auto_flag: bool = False

    # Rain
    rain_delay_left: int = 0
    rain_delay_duration: str = "0"
    rain_flag: bool = False
    rain_status_code: str = "0"

    # Fault
    fault_status_code: str = "normal"
    fault_status_name: str = "normal"

    # Connectivity
    station_flag: bool = False
    electricity: int = 0
    bluetooth_flag: Optional[bool] = None
    wifi_flag: bool = False
    wifi_lv: Optional[int] = None
    online_flag: bool = False
    ota_flag: Optional[bool] = None
    app_id: Optional[str] = None

    # Position / GPS
    lat: Optional[float] = None
    lng: Optional[float] = None
    gps: Optional[bool] = None
    charge_pos: Optional[dict] = None
    robot_pos: Optional[dict] = None
    ip_addr: Optional[str] = None

    # Device Info
    model_name: Optional[str] = None
    firmware_version: Optional[str] = None
    device_type: Optional[str] = None
    bound_at: Optional[str] = None
    pause: bool = False

    # Statistics
    area: Optional[int] = None
    on_min: Optional[int] = None
    total_min: Optional[int] = None
    work_area: Optional[int] = None

    # Timestamps
    collected_at: Optional[str] = None
    liveliness_at: Optional[str] = None

    # Schedules
    device_schedule_list: List[DeviceSchedule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceStatus":
        schedules = [
            DeviceSchedule.from_dict(s)
            for s in d.get("deviceScheduleList", [])
        ]
        # Some endpoints use 'id' instead of 'deviceId'
        device_id = d.get("deviceId") or d.get("id")
        return cls(
            device_id=str(device_id) if device_id else "",
            device_sn=d["deviceSn"],
            device_name=d.get("deviceName", ""),
            work_status_code=str(d.get("workStatusCode", "0")),
            work_status_name=d.get("workStatusName", "idle"),
            schedule_auto_flag=bool(d.get("scheduleAutoFlag", False)),
            rain_delay_left=int(d.get("rainDelayLeft", 0)),
            rain_delay_duration=str(d.get("rainDelayDuration", "0")),
            rain_flag=bool(d.get("rainFlag", False)),
            rain_status_code=str(d.get("rainStatusCode", "0")),
            fault_status_code=str(d.get("faultStatusCode", "normal")),
            fault_status_name=str(d.get("faultStatusName", "normal")),
            station_flag=bool(d.get("stationFlag", False)),
            electricity=int(d.get("electricity", 0)),
            bluetooth_flag=d.get("bluetoothFlag"),
            wifi_flag=bool(d.get("wifiFlag", False)),
            wifi_lv=d.get("wifiLv"),
            online_flag=bool(d.get("onlineFlag", False)),
            ota_flag=d.get("otaFlag"),
            app_id=str(d.get("appId")) if d.get("appId") is not None else None,
            lat=d.get("lat"),
            lng=d.get("lng"),
            gps=d.get("gps"),
            charge_pos=d.get("chargePos"),
            robot_pos=d.get("robotPos"),
            ip_addr=d.get("ipAddr"),
            model_name=d.get("modelName") or d.get("deviceModelName"),
            firmware_version=d.get("firmwareVersion"),
            device_type=d.get("deviceTypeName"),
            bound_at=d.get("boundAt"),
            pause=bool(d.get("pause", False)),
            area=d.get("area"),
            on_min=d.get("onMin"),
            total_min=d.get("totalMin"),
            work_area=d.get("workArea"),
            collected_at=d.get("collectedAt"),
            liveliness_at=d.get("livelinessAt"),
            device_schedule_list=schedules,
        )


# ---------------------------------------------------------------------------
# Command request bodies (sent by the client)
# ---------------------------------------------------------------------------


@dataclass
class SetWorkStatusRequest:
    """
    Body for POST /api/app_mower/device/setWorkStatus.

    Observed payload:
        {"appId":"12385068","deviceSn":"2310168001000041843","mode":0}
    """

    app_id: str
    device_sn: str
    mode: WorkMode

    def to_dict(self) -> dict:
        return {
            "appId": self.app_id,
            "deviceSn": self.device_sn,
            "mode": int(self.mode),
        }


@dataclass
class UpdateUserRequest:
    """
    Body for PUT /api/admin/user/edit.

    Observed payload:
        {"fbToken":"<firebase-token>","operatingSystemCode":"android"}
    """

    fb_token: str
    operating_system_code: str = "android"

    def to_dict(self) -> dict:
        return {
            "fbToken": self.fb_token,
            "operatingSystemCode": self.operating_system_code,
        }

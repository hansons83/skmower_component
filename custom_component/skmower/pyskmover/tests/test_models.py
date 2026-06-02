"""
Unit tests for pyskmover.models – no network access required.

Tests cover:
  - TokenResponse.from_dict
  - UserAppInfo.from_dict
  - DeviceSchedule.from_dict
  - DeviceSetting.from_dict
  - DeviceStatus.from_dict
  - SetWorkStatusRequest.to_dict
  - UpdateUserRequest.to_dict
  - WorkMode enum values
"""

import unittest

from pyskmover.models import (
    DeviceSchedule,
    DeviceSetting,
    DeviceStatus,
    SetWorkStatusRequest,
    TokenResponse,
    UpdateUserRequest,
    UserAppInfo,
    WorkMode,
    WorkStatusCode,
)


# ---------------------------------------------------------------------------
# Sample payloads extracted / reconstructed from sk-mover-komunikacja.log
# ---------------------------------------------------------------------------

TOKEN_RESPONSE = {
    "access_token": "3f21b39e-e845-4c44-aab7-c12191e1a698",
    "token_type": "bearer",
    "expires_in": 86399,
    "scope": "server",
}

USER_APP_INFO = {
    "appId": "12385068",
    "username": "kubs83",
    "email": "kubs83@gmail.com",
    "someExtraField": "extra_value",
}

SCHEDULE_ENTRY = {
    "id": "1803137033718280193",
    "deviceId": "1719580267837460482",
    "deviceSettingId": "17195802677913231 38",
    "dayOfWeek": 1,
    "startAt": "09:00:00",
    "endAt": "14:30:00",
    "trimFlag": True,
    "createdAt": "2024-06-18 18:45:44",
    "updatedAt": None,
}

DEVICE_SETTING_DATA = {
    "id": "17195802677913231 38",
    "deviceId": "1719580267837460482",
    "deviceSn": "2310168001000041843",
    "deviceName": "Kosiek",
    "rainDelayDuration": "0",
    "rainFlag": True,
    "language": 0,
    "otaFlag": None,
    "onlineFlag": True,
    "otaAutoFlag": False,
    "shareableFlag": True,
    "zoneOpenFlag": True,
    "zoneAutomaticFlag": False,
    "zoneFirstPercentage": 0,
    "zoneSecondPercentage": 2,
    "zoneThirdPercentage": 0,
    "zoneFourthPercentage": 3,
    "zoneExFlag": 0,
    "meterFirst": 1000,
    "meterSecond": 4499,
    "meterThird": 1000,
    "meterFour": 6748,
    "proFirst": 25,
    "proSecond": 25,
    "proThird": 25,
    "proFour": 25,
    "borderLength": 224954,
    "scheduleAutoFlag": False,
    "ledFlag": True,
    "ledColorCode": None,
    "ledModeCode": "true",
    "ledModeName": None,
    "ledStart": None,
    "ledEnd": None,
    "ledNightFlag": False,
    "gpsFlag": False,
    "gpsLong": None,
    "gpsLat": None,
    "timeAutoFlag": True,
    "timeZoneCode": "GMT+1",
    "timeZoneFlag": True,
    "timeZoneId": "Europe/Warsaw",
    "daylightTimeFlag": True,
    "nowTime": "2024-6-21 13:42:59",
    "ultraFlag": True,
    "ultraLv": 1,
    "pause": False,
    "deviceScheduleList": [SCHEDULE_ENTRY],
    "createdAt": "2023-11-01 05:00:58",
    "updatedAt": "2024-06-15 21:39:59",
}

DEVICE_STATUS_DATA = {
    "deviceId": "1719580267837460482",
    "deviceSn": "2310168001000041843",
    "appId": None,
    "deviceName": "Kosiek",
    "workStatusCode": "0",
    "workStatusName": "idle",
    "scheduleAutoFlag": False,
    "rainDelayLeft": 0,
    "rainDelayDuration": "0",
    "rainFlag": True,
    "faultStatusCode": "normal",
    "stationFlag": False,
    "faultStatusName": "normal",
    "electricity": 68,
    "bluetoothFlag": None,
    "wifiFlag": True,
    "rainStatusCode": "0",
    "collectedAt": "2024-06-21 19:42:41",
    "lat": 51.79329,
    "lng": 19.257982,
    "onlineFlag": True,
    "otaFlag": None,
    "area": 72118,
    "onMin": 72654,
    "totalMin": 72654,
    "workArea": None,
    "chargePos": None,
    "robotPos": None,
    "ipAddr": None,
    "livelinessAt": None,
    "deviceScheduleList": [SCHEDULE_ENTRY],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWorkMode(unittest.TestCase):
    def test_values(self):
        self.assertEqual(int(WorkMode.STOP), 0)
        self.assertEqual(int(WorkMode.MOWING), 1)
        self.assertEqual(int(WorkMode.BORDER), 4)

    def test_names(self):
        self.assertEqual(WorkMode(0).name, "STOP")
        self.assertEqual(WorkMode(1).name, "MOWING")
        self.assertEqual(WorkMode(4).name, "BORDER")


class TestTokenResponse(unittest.TestCase):
    def setUp(self):
        self.token = TokenResponse.from_dict(TOKEN_RESPONSE)

    def test_access_token(self):
        self.assertEqual(self.token.access_token, "3f21b39e-e845-4c44-aab7-c12191e1a698")

    def test_token_type(self):
        self.assertEqual(self.token.token_type, "bearer")

    def test_expires_in(self):
        self.assertEqual(self.token.expires_in, 86399)

    def test_scope(self):
        self.assertEqual(self.token.scope, "server")

    def test_missing_optional_fields(self):
        t = TokenResponse.from_dict({"access_token": "abc"})
        self.assertIsNone(t.expires_in)
        self.assertIsNone(t.refresh_token)


class TestUserAppInfo(unittest.TestCase):
    def setUp(self):
        self.info = UserAppInfo.from_dict(USER_APP_INFO)

    def test_app_id(self):
        self.assertEqual(self.info.app_id, "12385068")

    def test_username(self):
        self.assertEqual(self.info.username, "kubs83")

    def test_email(self):
        self.assertEqual(self.info.email, "kubs83@gmail.com")

    def test_extra_fields_stored(self):
        self.assertIn("someExtraField", self.info.extra)
        self.assertEqual(self.info.extra["someExtraField"], "extra_value")

    def test_none_app_id(self):
        info = UserAppInfo.from_dict({"appId": None})
        self.assertIsNone(info.app_id)


class TestDeviceSchedule(unittest.TestCase):
    def setUp(self):
        self.sched = DeviceSchedule.from_dict(SCHEDULE_ENTRY)

    def test_id(self):
        self.assertEqual(self.sched.id, "1803137033718280193")

    def test_day_of_week(self):
        self.assertEqual(self.sched.day_of_week, 1)

    def test_start_at(self):
        self.assertEqual(self.sched.start_at, "09:00:00")

    def test_end_at(self):
        self.assertEqual(self.sched.end_at, "14:30:00")

    def test_trim_flag(self):
        self.assertTrue(self.sched.trim_flag)

    def test_updated_at_none(self):
        self.assertIsNone(self.sched.updated_at)


class TestDeviceSetting(unittest.TestCase):
    def setUp(self):
        self.setting = DeviceSetting.from_dict(DEVICE_SETTING_DATA)

    def test_device_name(self):
        self.assertEqual(self.setting.device_name, "Kosiek")

    def test_device_sn(self):
        self.assertEqual(self.setting.device_sn, "2310168001000041843")

    def test_rain_flag(self):
        self.assertTrue(self.setting.rain_flag)

    def test_online_flag(self):
        self.assertTrue(self.setting.online_flag)

    def test_border_length(self):
        self.assertEqual(self.setting.border_length, 224954)

    def test_zone_second_percentage(self):
        self.assertEqual(self.setting.zone_second_percentage, 2)

    def test_led_mode_code(self):
        self.assertEqual(self.setting.led_mode_code, "true")

    def test_time_zone_id(self):
        self.assertEqual(self.setting.time_zone_id, "Europe/Warsaw")

    def test_ultra_lv(self):
        self.assertEqual(self.setting.ultra_lv, 1)

    def test_schedules_parsed(self):
        self.assertEqual(len(self.setting.device_schedule_list), 1)
        self.assertEqual(self.setting.device_schedule_list[0].day_of_week, 1)

    def test_pause_false(self):
        self.assertFalse(self.setting.pause)


class TestDeviceStatus(unittest.TestCase):
    def setUp(self):
        self.status = DeviceStatus.from_dict(DEVICE_STATUS_DATA)

    def test_device_name(self):
        self.assertEqual(self.status.device_name, "Kosiek")

    def test_work_status_code(self):
        self.assertEqual(self.status.work_status_code, "0")

    def test_work_status_name(self):
        self.assertEqual(self.status.work_status_name, "idle")

    def test_electricity(self):
        self.assertEqual(self.status.electricity, 68)

    def test_rain_flag(self):
        self.assertTrue(self.status.rain_flag)

    def test_fault_status_code(self):
        self.assertEqual(self.status.fault_status_code, "normal")

    def test_online_flag(self):
        self.assertTrue(self.status.online_flag)

    def test_location(self):
        self.assertAlmostEqual(self.status.lat, 51.79329, places=4)
        self.assertAlmostEqual(self.status.lng, 19.257982, places=4)

    def test_area(self):
        self.assertEqual(self.status.area, 72118)

    def test_total_min(self):
        self.assertEqual(self.status.total_min, 72654)

    def test_schedules_parsed(self):
        self.assertEqual(len(self.status.device_schedule_list), 1)

    def test_app_id_none(self):
        self.assertIsNone(self.status.app_id)

    def test_bluetooth_flag_none(self):
        self.assertIsNone(self.status.bluetooth_flag)


class TestSetWorkStatusRequest(unittest.TestCase):
    def test_stop(self):
        req = SetWorkStatusRequest("12385068", "2310168001000041843", WorkMode.STOP)
        d = req.to_dict()
        self.assertEqual(d["appId"], "12385068")
        self.assertEqual(d["deviceSn"], "2310168001000041843")
        self.assertEqual(d["mode"], 0)

    def test_mowing(self):
        req = SetWorkStatusRequest("12385068", "2310168001000041843", WorkMode.MOWING)
        self.assertEqual(req.to_dict()["mode"], 1)

    def test_border(self):
        req = SetWorkStatusRequest("12385068", "2310168001000041843", WorkMode.BORDER)
        self.assertEqual(req.to_dict()["mode"], 4)


class TestUpdateUserRequest(unittest.TestCase):
    def test_to_dict(self):
        req = UpdateUserRequest(fb_token="myFBToken123", operating_system_code="android")
        d = req.to_dict()
        self.assertEqual(d["fbToken"], "myFBToken123")
        self.assertEqual(d["operatingSystemCode"], "android")

    def test_default_os(self):
        req = UpdateUserRequest(fb_token="tok")
        self.assertEqual(req.to_dict()["operatingSystemCode"], "android")


if __name__ == "__main__":
    unittest.main()
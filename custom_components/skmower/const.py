"""Constants for the SK-Mower integration."""

DOMAIN = "skmover"

# Config-entry keys
CONF_DEVICE_SN = "device_sn"
CONF_POLL_INTERVAL = "poll_interval"

# Default values
POLL_INTERVAL = 30  # seconds – matches pyskmover default

# Manufacturer / model strings
MANUFACTURER = "SK-Robot"
MODEL = "Robotic Mower"

# Fault status codes
FAULT_STATUS_NORMAL = "normal"

# Service names
SERVICE_START_MOWING = "start_mowing"
SERVICE_STOP_MOWING = "stop_mowing"
SERVICE_START_BORDER = "start_border"
SERVICE_RETURN_TO_DOCK = "return_to_dock"
SERVICE_FORCE_POLL = "force_poll"

# Attribute keys exposed on the lawn_mower entity
ATTR_DEVICE_SN = "device_sn"
ATTR_DEVICE_ID = "device_id"
ATTR_FAULT_STATUS = "fault_status"
ATTR_RAIN_FLAG = "rain_flag"
ATTR_RAIN_DELAY_LEFT = "rain_delay_left"
ATTR_STATION_FLAG = "station_flag"
ATTR_WIFI_FLAG = "wifi_flag"
ATTR_ON_MINUTES = "on_minutes"
ATTR_TOTAL_MINUTES = "total_minutes"
ATTR_AREA = "area"
ATTR_COLLECTED_AT = "collected_at"
ATTR_BATTERY = "battery"
ATTR_WORK_STATUS = "work_status"
ATTR_WORK_STATUS_CODE = "work_status_code"
ATTR_RAIN_STATUS = "rain_status"
ATTR_BORDER_LENGTH = "border_length"
ATTR_TIME_ZONE = "time_zone"
ATTR_WIFI_LEVEL = "wifi_level"
ATTR_MODEL_NAME = "model_name"
ATTR_ONLINE_STATUS = "online_status"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_GPS = "gps"
ATTR_FIRMWARE = "firmware_version"
ATTR_IP_ADDRESS = "ip_address"
ATTR_WORK_STATUS_NAME = "work_status_api"
ATTR_BOUND_AT = "bound_at"
ATTR_DEVICE_TYPE = "device_type"
ATTR_LAST_SYNCED = "last_synced"
ATTR_MAP_AREA = "map_area"
ATTR_MAP_PERIMETER = "map_perimeter"
ATTR_SCHEDULE = "schedule"
ATTR_RAIN_DELAY_DURATION = "rain_delay_duration"
ATTR_SCHEDULE_AUTO = "schedule_auto"
ATTR_ZONE_OPEN = "zone_open"
ATTR_NOW_TIME = "now_time"
ATTR_BLUETOOTH_MAC = "bluetooth_mac"
ATTR_DEVICE_MODEL_NAME = "device_model_name"
ATTR_ZONE_FIRST_PERCENTAGE = "zone_first_percentage"
ATTR_ZONE_SECOND_PERCENTAGE = "zone_second_percentage"
ATTR_METER_FIRST = "meter_first"
ATTR_METER_SECOND = "meter_second"
ATTR_TIME_ZONE_CODE = "time_zone_code"

# Time Update from Android

Sync a Debian Linux system’s time, date, and timezone from an Android device over USB (ADB) or Bluetooth (file-based).

## Features

- USB sync via ADB for date/time and timezone
- Bluetooth sync via a shared text file
- Root checks and clear diagnostics
- Robust parsing of Android date output
- Debug logging to `/tmp/timeupdate_debug.log`
- Optional GPS location logging (if available)

## Requirements

- Debian-based Linux
- Python 3
- Root privileges (required to set time/timezone)
- For USB/ADB mode: Android Debug Bridge (ADB) installed and device authorized

## Installation

1. Ensure Python 3 is available.
2. Install ADB if you plan to use USB mode.
3. Place the script in a directory.

## Usage

> Note: Bluetooth mode is untested and may not work in all environments.

### USB (ADB) mode (default)

Run as root:

```
sudo python3 update_time_from_android.py
```

This will:

- Read time and timezone from the connected Android device
- Set the system timezone first
- Set the system time

### Bluetooth file mode

Create or transfer a file containing time data (see format below), then run:

```
sudo python3 update_time_from_android.py --bluetooth --btfile /tmp/bluetooth/timeinfo.txt
```

### Bluetooth file format

Create a text file with the following format:

```
DATE=YYYY-MM-DD
TIME=HH:MM:SS
TZ=Region/City
LAT=12.3456
LON=-98.7654
```

`TZ`, `LAT`, and `LON` are optional. If omitted, only the time and date are updated.

Example:

```
DATE=2026-01-27
TIME=15:42:00
TZ=America/New_York
LAT=40.7128
LON=-74.0060
```

## Logging

The script logs to:

- Standard output
- `/tmp/timeupdate_debug.log`

When available, GPS coordinates are logged alongside the time update event.

## Troubleshooting

- **ADB not found**: Install ADB and ensure it’s in PATH.
- **Device not authorized**: On Android, confirm the USB debugging prompt.
- **Time did not change**: NTP or virtualization can override manual time updates. Consider disabling NTP via `timedatectl set-ntp false`.
- **Timezone not set**: Ensure the Android device has a valid `persist.sys.timezone` value or provide `TZ` in the Bluetooth file.

## Security Notes

- The script must run as root to set system time and timezone.
- Use Bluetooth file mode only with trusted inputs.

## License

MIT License (or specify your preferred license).

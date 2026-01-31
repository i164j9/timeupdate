#!/usr/bin/env python3
"""Sync Debian system time and timezone from an Android device."""
import sys
import subprocess
import re
import os
import argparse
import datetime
import time
import traceback
import calendar


def debug_log(msg):
    """Log a message to stdout and append it to a debug log file."""
    print(msg, flush=True)
    try:
        with open("/tmp/timeupdate_debug.log", "a", encoding="utf-8") as dbg:
            dbg.write(f"{datetime.datetime.now()} {msg}\n")
    except OSError:
        pass


def format_adb_error(exc):
    """Return a helpful error string for adb subprocess failures."""
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = []
        if stdout:
            details.append(f"stdout: {stdout}")
        if stderr:
            details.append(f"stderr: {stderr}")
        detail_str = f" ({'; '.join(details)})" if details else ""
        return f"exit status {exc.returncode}{detail_str}"
    return str(exc)


def check_python_version():
    """Ensure the script is running on Python 3."""
    if sys.version_info[0] < 3:
        debug_log("This script requires Python 3. Please run with python3.")
        sys.exit(1)


def check_root():
    """Exit if the script is not running as root on Linux."""
    if not (sys.platform.startswith('linux') and os.geteuid() == 0):
        debug_log("This script must be run as root on Linux.")
        sys.exit(1)


def check_adb():
    """Validate that ADB is installed and available in PATH."""
    try:
        subprocess.run(
            ["adb", "version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        debug_log(
            "ADB (Android Debug Bridge) is not installed or not in PATH."
        )
        sys.exit(1)


def check_adb_device():
    """Ensure an authorized, online ADB device is connected."""
    try:
        devices = subprocess.run(
            ["adb", "devices"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        debug_log(f"Failed to list ADB devices: {e}")
        sys.exit(1)

    lines = [line.strip() for line in devices.stdout.splitlines()]
    device_lines = [line for line in lines if line and not line.startswith("List of devices")]
    if not device_lines:
        debug_log("No ADB devices detected. Is the device connected and USB debugging enabled?")
        sys.exit(1)

    statuses = [line.split() for line in device_lines if line.split()]
    offline = [s for s in statuses if len(s) >= 2 and s[1] == "offline"]
    unauthorized = [s for s in statuses if len(s) >= 2 and s[1] == "unauthorized"]
    if unauthorized:
        debug_log("ADB device unauthorized. Unlock the phone and accept the USB debugging prompt.")
        sys.exit(1)
    if offline:
        debug_log("ADB device is offline. Replug the device or restart ADB (adb kill-server).")
        sys.exit(1)


def get_android_time():
    """Return Android device time as 'YYYY-MM-DD HH:MM:SS' via ADB."""
    # Try custom format first
    try:
        result = subprocess.run(
            ["adb", "shell", "date", "+%Y-%m-%d %H:%M:%S"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        return output
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        debug_log(f"Custom date format failed: {format_adb_error(e)}")
        # Fallback: try default date output and parse
        try:
            result = subprocess.run(
                ["adb", "shell", "date"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            output = result.stdout.strip()
            debug_log(f"Raw Android date output: {output}")
            # Parse: 'Tue Jan 27 20:37:13 EST 2026' (ignore timezone)
            m = re.match(
                r"\w+ (\w+) (\d+) (\d{2}):(\d{2}):(\d{2}) \w+ (\d{4})", output)
            if m:
                month_str, day, hour, minute, second, year = m.groups()
                try:
                    month = list(calendar.month_abbr).index(month_str)
                except ValueError:
                    debug_log(f"Unknown month abbreviation: {month_str}")
                    sys.exit(1)
                formatted = (
                    f"{year}-{month:02d}-{int(day):02d} "
                    f"{hour}:{minute}:{second}"
                )
                return formatted
            else:
                debug_log(f"Could not parse Android date output: {output}")
                sys.exit(1)
        except (FileNotFoundError, subprocess.CalledProcessError) as e3:
            debug_log(
                "Failed to get date/time from Android device: "
                f"{format_adb_error(e3)}"
            )
            debug_log(
                "Troubleshooting: ensure the device is unlocked, USB debugging "
                "is enabled/authorized, and try reconnecting the cable or "
                "restarting ADB (adb kill-server)."
            )
            sys.exit(1)


def get_bluetooth_timeinfo(filepath="/tmp/bluetooth/timeinfo.txt"):
    """Read date/time and optional timezone/location from a Bluetooth file."""
    if not os.path.exists(filepath):
        debug_log(f"Bluetooth time info file not found: {filepath}")
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    date, time_str, tz = None, None, None
    lat, lon = None, None
    for line in lines:
        if line.startswith("DATE="):
            date = line.strip().split("=", 1)[1]
        elif line.startswith("TIME="):
            time_str = line.strip().split("=", 1)[1]
        elif line.startswith("TZ="):
            tz = line.strip().split("=", 1)[1]
        elif line.startswith("LAT="):
            lat = line.strip().split("=", 1)[1]
        elif line.startswith("LON="):
            lon = line.strip().split("=", 1)[1]
    if not (date and time_str):
        debug_log("Bluetooth time info file missing DATE or TIME.")
        sys.exit(1)
    return date + " " + time_str, tz, lat, lon


def get_android_timezone():
    """Return the Android device timezone via ADB."""
    try:
        result = subprocess.run(
            ["adb", "shell", "getprop", "persist.sys.timezone"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        tz = result.stdout.strip()
        return tz
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        debug_log(f"Failed to get timezone from Android device: {e}")
        sys.exit(1)


def get_android_location():
    """Return last known Android location as (lat, lon) strings."""
    try:
        result = subprocess.run(
            ["adb", "shell", "dumpsys", "location"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        output = result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        debug_log(f"Failed to get location from Android device: {e}")
        return None, None

    patterns = [
        r"last location=Location\[\w+ (-?\d+\.\d+),(-?\d+\.\d+)",
        r"Location\[\w+ (-?\d+\.\d+),(-?\d+\.\d+)",
        r"\s(-?\d+\.\d+),(-?\d+\.\d+)\s*\(\w+\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1), match.group(2)
    return None, None


def set_system_time(datetime_str):
    """Set the system clock to the provided datetime string."""
    def get_sys_time():
        """Return the current system time as 'YYYY-MM-DD HH:MM:SS'."""
        result = subprocess.run(
            ["date", "+%Y-%m-%d %H:%M:%S"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()
    before = get_sys_time()
    debug_log(f"System time before: {before}")
    changed = False
    try:
        subprocess.run(
            ["timedatectl", "set-ntp", "false"],
            check=True,
            capture_output=True,
        )
        out2 = subprocess.run(
            ["timedatectl", "set-time", datetime_str],
            check=True,
            capture_output=True,
            text=True,
        )
        debug_log(
            "timedatectl output: "
            f"{out2.stdout.strip()} {out2.stderr.strip()}"
        )
        changed = True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        debug_log(f"timedatectl failed: {e}")
        try:
            out3 = subprocess.run(
                ["date", "-s", datetime_str],
                check=True,
                capture_output=True,
                text=True,
            )
            debug_log(
                "date command output: "
                f"{out3.stdout.strip()} {out3.stderr.strip()}"
            )
            changed = True
        except (FileNotFoundError, subprocess.CalledProcessError) as e2:
            debug_log(
                "Failed to set system time with both "
                f"timedatectl and date: {e2}"
            )
            sys.exit(1)
    time.sleep(1)
    after = get_sys_time()
    debug_log(f"System time after: {after}")
    if before == after:
        debug_log(
            "Warning: System time did not change! This may be due to "
            "virtualization, NTP, or permissions."
        )
    elif changed:
        debug_log(f"System time set to {datetime_str}.")


def set_system_timezone(tz):
    """Set the system timezone using timedatectl."""
    try:
        subprocess.run(["timedatectl", "set-timezone", tz], check=True)
        debug_log(f"System timezone set to {tz}")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        debug_log(f"Failed to set system timezone: {e}")
        sys.exit(1)


def main():
    """Parse arguments and update system time/timezone."""
    check_python_version()
    debug_log(f"Python version: {sys.version}")
    debug_log(f"sys.executable: {sys.executable}")
    debug_log(f"sys.argv: {sys.argv}")
    try:
        debug_log("main() entered")
        check_root()
        parser = argparse.ArgumentParser(
            description=(
                "Update system time/date/timezone from Android over USB "
                "or Bluetooth."
            )
        )
        parser.add_argument(
            "--bluetooth",
            action="store_true",
            help="Use Bluetooth file method instead of ADB",
        )
        parser.add_argument(
            "--btfile",
            type=str,
            default="/tmp/bluetooth/timeinfo.txt",
            help="Bluetooth time info file path",
        )
        args = parser.parse_args()

        if args.bluetooth:
            debug_log(
                f"Getting time and timezone from Bluetooth file: {args.btfile}"
            )
            datetime_str, android_tz, lat, lon = get_bluetooth_timeinfo(
                args.btfile
            )
            if android_tz:
                set_system_timezone(android_tz)
            else:
                debug_log("No timezone info found in Bluetooth file.")
            set_system_time(datetime_str)
            if lat and lon:
                debug_log(
                    "Location at update (Bluetooth): "
                    f"lat={lat}, lon={lon}"
                )
            else:
                debug_log("No location info found in Bluetooth file.")
        else:
            check_adb()
            check_adb_device()
            debug_log(
                "Getting time and timezone from Android device over USB "
                "(ADB)..."
            )
            android_time = get_android_time()
            android_tz = get_android_timezone()
            lat, lon = get_android_location()
            match = re.match(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", android_time)
            if not match:
                debug_log(
                    f"Unexpected date format from Android: {android_time}")
                sys.exit(1)
            datetime_str = match.group(1)
            if android_tz:
                set_system_timezone(android_tz)
            else:
                debug_log("No timezone info found on Android device.")
            set_system_time(datetime_str)
            if lat and lon:
                debug_log(
                    "Location at update (ADB): "
                    f"lat={lat}, lon={lon}"
                )
            else:
                debug_log("No location info found from Android device.")
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        debug_log(f"Top-level exception: {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

# Device 013: ID 18d1:4ee7 Google Inc. Nexus/Pixel Device (charging + debug)
#
# Create a udev rule that triggers a systemd service on USB connect, and a
# service unit that runs the script as root.

# 1) systemd service unit
# Create etc/systemd/system/timeupdate-android.service with:

# [Unit]
# Description=Sync time/timezone from Android over ADB
# After=network.target

# [Service]
# Type=oneshot
# ExecStart=/usr/bin/python3 /home/dev/timeupdate/update_time_from_android.py

# [Install]
# WantedBy=multi-user.target

# 2) udev rule
# Create etc/udev/rules.d/99-android-timeupdate.rules with
# (replace idVendor with your device’s vendor ID):
# ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="118d1", TAG+="systemd",
# ENV{SYSTEMD_WANTS}="timeupdate-android.service"

# 3) Reload udev and systemd, then replug the device.

# Notes:

# USB debugging must be enabled and the device authorized.
# If you want to support multiple vendors, add more rules with their idVendor
# values.
#

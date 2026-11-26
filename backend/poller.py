import signal
import sys
import threading
import time
import traceback

import getrouterstats

POLL_INTERVAL = 10  # seconds between fetches (a full fetch cycle takes ~12s)
IDLE_REFRESH_INTERVAL = 600  # seconds; refresh anyway when nobody is watching
USER_CONFLICT_RETRY_DELAY = 180  # seconds to wait before retrying login
RETRY_BACKOFF_MAX = 300  # cap for the exponential backoff on connection/auth failures
MAX_FAILURES_BEFORE_EXIT = 5  # then exit non-zero so systemd restarts the whole app

# main.py sends SIGUSR1
_wake_event = threading.Event()
signal.signal(signal.SIGUSR1, lambda signum, frame: _wake_event.set())


def main():
    print(
        f"[poller] Starting — fetching every {POLL_INTERVAL}s while the dashboard "
        f"is being viewed, and every {IDLE_REFRESH_INTERVAL}s when idle"
    )
    failures = 0
    conflicts = 0
    idle_logged = False
    last_fetch = 0.0  # 0 forces one fetch at startup so there's data to serve
    while True:
        idle = not getrouterstats.viewer_present()
        if idle and time.monotonic() - last_fetch < IDLE_REFRESH_INTERVAL:
            # Nobody is looking and no idle refresh is due: leave the router
            # alone. Check once a second so a new tab is picked up quickly.
            if not idle_logged:
                print("[poller] Idle — waiting for a viewer or the 10-minute refresh")
                idle_logged = True
            _wake_event.wait(1)
            _wake_event.clear()
            continue
        if idle:
            print("[poller] Idle refresh — updating data despite no viewer")
        elif idle_logged:
            print("[poller] Viewer detected — resuming fetches")
        idle_logged = False
        try:
            getrouterstats.get_stats_json()
            # Count the attempt, not just success, so a failed idle refresh
            # can't bypass its error backoff.
            last_fetch = time.monotonic()
            print(f"[poller] OK — {getrouterstats.JSON_PATH} updated")
            failures = 0
            conflicts = 0
        except RuntimeError as e:
            if "user conflict" in str(e).lower():
                # Another admin session (usually the router's web UI) holds
                # the single available slot. This isn't our fault and doesn't
                # count towards the fatal-failure limit.
                conflicts += 1
                delay = USER_CONFLICT_RETRY_DELAY
                print(
                    f"[poller] Router busy — another admin session is active; "
                    f"retrying in {delay}s (conflict #{conflicts})"
                )
            else:
                failures += 1
                if failures >= MAX_FAILURES_BEFORE_EXIT:
                    print(f"[poller] {e} — {failures} failures in a row, exiting")
                    sys.exit(1)
                # don't hammer the login endpoint or trip its lockout.
                delay = min(POLL_INTERVAL * 2**failures, RETRY_BACKOFF_MAX)
                print(f"[poller] {e} — retrying in {delay}s (failure #{failures})")
            # Don't let viewer pings shorten a backoff: repeated failed
            # logins can trip the router's ~2h admin lockout.
            time.sleep(delay)
            continue
        except Exception:
            print("[poller] ERROR during fetch:")
            traceback.print_exc()
        _wake_event.wait(POLL_INTERVAL)
        _wake_event.clear()


if __name__ == "__main__":
    main()

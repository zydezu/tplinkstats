import signal
import sys
import threading
import traceback

import getrouterstats

POLL_INTERVAL = 8  # seconds between fetches (a full fetch cycle already takes ~12s)
USER_CONFLICT_RETRY_DELAY = 180  # seconds to wait before retrying login
RETRY_BACKOFF_MAX = 300  # cap for the exponential backoff on connection/auth failures
MAX_FAILURES_BEFORE_EXIT = 5  # then exit non-zero so systemd restarts the whole app

# main.py sends SIGUSR1 (e.g. when a browser window first loads the page) to
# skip the rest of the wait and start fetching immediately.
_wake_event = threading.Event()
signal.signal(signal.SIGUSR1, lambda signum, frame: _wake_event.set())


def main():
    print(f"[poller] Starting — fetching every {POLL_INTERVAL}s")
    failures = 0
    while True:
        try:
            getrouterstats.get_stats_json()
            print(f"[poller] OK — {getrouterstats.JSON_PATH} updated")
            failures = 0
        except RuntimeError as e:
            if "user conflict" in str(e).lower():
                # Wait as another user has accessed the router's web UI
                delay = USER_CONFLICT_RETRY_DELAY
            else:
                failures += 1
                if failures >= MAX_FAILURES_BEFORE_EXIT:
                    print(f"[poller] {e} — {failures} failures in a row, exiting")
                    sys.exit(1)
                # Outages and router-side login glitches (e.g. "lan mac is nil"
                # while it's still booting) clear up on their own; back off so
                # we don't hammer the login endpoint or trip its lockout.
                delay = min(POLL_INTERVAL * 2**failures, RETRY_BACKOFF_MAX)
            print(f"[poller] {e} — retrying in {delay}s (failure #{failures})")
            _wake_event.wait(delay)
            _wake_event.clear()
            continue
        except Exception:
            print("[poller] ERROR during fetch:")
            traceback.print_exc()
        _wake_event.wait(POLL_INTERVAL)
        _wake_event.clear()


if __name__ == "__main__":
    main()

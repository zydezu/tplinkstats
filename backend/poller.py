import signal
import sys
import threading
import traceback

import getrouterstats

POLL_INTERVAL = 8  # seconds between fetches (a full fetch cycle already takes ~12s)

# main.py sends SIGUSR1 (e.g. when a browser window first loads the page) to
# skip the rest of the wait and start fetching immediately.
_wake_event = threading.Event()
signal.signal(signal.SIGUSR1, lambda signum, frame: _wake_event.set())


def main():
    print(f"[poller] Starting — fetching every {POLL_INTERVAL}s")
    while True:
        try:
            getrouterstats.get_stats_json()
            print(f"[poller] OK — {getrouterstats.JSON_PATH} updated")
        except RuntimeError as e:
            print(f"[poller] FATAL: {e} — stopping")
            sys.exit(1)
        except Exception:
            print("[poller] ERROR during fetch:")
            traceback.print_exc()
        _wake_event.wait(POLL_INTERVAL)
        _wake_event.clear()


if __name__ == "__main__":
    main()

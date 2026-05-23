import sys
import time
import traceback

import getrouterstats

POLL_INTERVAL = 2  # seconds between fetches


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
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

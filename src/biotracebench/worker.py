"""Background worker: one run, event-only local error notification, no polling."""
import argparse
import subprocess
import sys
import os
import traceback
from pathlib import Path
from .common import now, write, read, digest
from .runner import run


def notify_error(output, completed=False):
    root=Path(output)
    state=read(root/'status.json') if (root/'status.json').exists() else read(root/'error.json') if (root/'error.json').exists() else {}
    event_id=digest({'tasks':state.get('tasks'),'failure':state.get('failure',state.get('status')),'completed':completed})
    if (root/'notification.json').exists() and read(root/'notification.json').get('event_id')==event_id:
        return

    result = {"attempted_at": now(), "channel": "local_desktop", "status": "unavailable", "event_id": event_id, "event": "completed" if completed else "stopped"}
    if sys.platform == "darwin":
        try:
            process = subprocess.run(["/usr/bin/osascript", "-e",
                'display notification '+ ('"Submission finished. Open management/overview.html for execution and answer status." with title "BioTraceBench completed"' if completed else '"Execution paused. Open error.json and management/overview.html in the run directory." with title "BioTraceBench stopped"')],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            result["status"] = "submitted_to_os" if process.returncode == 0 else "unavailable"
        except (OSError, subprocess.TimeoutExpired):
            pass
    write(Path(output)/"notification.json", result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    try:
        result = run(args.manifest, args.out)
        write(Path(args.out)/"worker.json", {"pid":os.getpid(),"status":"stopped" if result["failure"] else "finished",
              "ended_at":now(),"notification_policy":"completion_or_actionable_stop_only"})
        if result["failure"]:
            notify_error(args.out)
            return 1
        states=[value for case in result.get("tasks",{}).values() for value in case.values()]
        if states and all(value in {"completed","invalid_output"} for value in states):
            notify_error(args.out, completed=True)
        elif states and any(value.startswith(("paused","deferred")) for value in states):
            notify_error(args.out)
        return 0
    except Exception as exc:
        write(Path(args.out)/"error.json", {"status": getattr(exc, "status", "failed_worker"),
              "exception_type": type(exc).__name__, "stack": [{"file": f.filename, "line": f.lineno, "function": f.name} for f in traceback.extract_tb(exc.__traceback__)], "message": "Worker stopped before a complete run; inspect saved status and archives", "time": now()})
        write(Path(args.out)/"worker.json", {"pid":os.getpid(),"status":"failed_worker","ended_at":now()})
        notify_error(args.out)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

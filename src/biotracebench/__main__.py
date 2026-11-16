from .cli import main
from .common import Stop
import json
import sys

try:
    raise SystemExit(main())
except (Stop, ValueError, OSError) as exc:
    print(json.dumps({"status": getattr(exc, "status", "failed_local"), "error": str(exc)}), file=sys.stderr)
    raise SystemExit(1)

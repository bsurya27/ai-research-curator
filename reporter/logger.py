import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "reporter"


class ReporterLogger:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.started_at = datetime.now(timezone.utc).isoformat()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOG_DIR / f"{self.started_at[:10]}_{self.session_id[:8]}.json"
        self._entries = []
        self._write()

    def log(self, event: str, data: dict) -> None:
        entry = {
            "session_id": self.session_id,
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._entries.append(entry)
        self._write()

    def _write(self) -> None:
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "session_id": self.session_id,
                    "started_at": self.started_at,
                    "entries": self._entries,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

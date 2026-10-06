"""
JSON log formatter (Phase E - Production readiness).

`LOG_FORMAT=json` (env) switches every console handler in
config/settings/base.py to one-line JSON records on stdout -- the shape
container log collectors expect (docker logs -> node/agent -> Loki/
Elastic/whatever the host uses), while `LOG_FORMAT=plain` (default)
keeps the human-readable format for development.

One JSON object per line, always these keys:
    {"time": "...", "level": "INFO", "logger": "payments", "message": "..."}
plus "exc_info" when the record carries an exception. ensure_ascii=False
so Persian log content stays readable in the stream.
"""
import json
import logging


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

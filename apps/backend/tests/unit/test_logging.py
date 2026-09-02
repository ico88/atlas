"""Unit tests for structured JSON logging."""

from __future__ import annotations

import json
import logging

from app.core.context import set_request_id, set_task_id
from app.core.logging import JsonFormatter


def _record(**kwargs) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=kwargs.pop("msg", "hello"),
        args=(),
        exc_info=None,
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_required_fields():
    set_request_id("req-123")
    set_task_id("task-abc")
    formatter = JsonFormatter(service="backend")

    output = json.loads(formatter.format(_record(event="unit_event")))

    assert output["level"] == "INFO"
    assert output["service"] == "backend"
    assert output["request_id"] == "req-123"
    assert output["task_id"] == "task-abc"
    assert output["event"] == "unit_event"
    assert output["message"] == "hello"
    assert "timestamp" in output


def test_json_formatter_includes_context():
    set_request_id(None)
    set_task_id(None)
    formatter = JsonFormatter()

    output = json.loads(
        formatter.format(_record(context={"node_id": "node-1", "load": 0.5}))
    )

    assert output["context"] == {"node_id": "node-1", "load": 0.5}
    assert output["request_id"] is None

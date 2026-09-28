import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_task_webhook_secret_is_required(monkeypatch):
    monkeypatch.delenv("TASK_WEBHOOK_SECRET", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, task_webhook_secret="")

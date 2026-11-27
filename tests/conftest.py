import os, sys, tempfile, threading, time
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
os.environ["DATA_DIR"] = tempfile.mkdtemp()
import pytest, uvicorn


@pytest.fixture(scope="session")
def dashboard_url():
    from sample_dashboard.main import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=9876, log_level="error")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(50):
        if srv.started: break
        time.sleep(0.1)
    yield "http://127.0.0.1:9876"
    srv.should_exit = True


class FakeLLM:
    """Replays scripted replies instead of calling an AI service."""
    def __init__(self, replies): self.replies, self.sent, self.last_provider = list(replies), [], "fake"
    def chat(self, messages, tools=None, **kw):
        self.sent.append(messages); return self.replies.pop(0)


def tool_call(name, **args):
    import json
    return {"id": "c" + name, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

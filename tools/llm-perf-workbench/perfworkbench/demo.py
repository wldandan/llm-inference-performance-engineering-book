"""Opt-in localhost protocol fixture. Never a real model or performance evidence."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def example_spec():
    from .config import ExperimentSpec

    return ExperimentSpec.model_validate(
        {
            "name": "本地协议演示（不是模型性能）",
            "protocol_fixture": True,
            "endpoint": {
                "base_url": "http://127.0.0.1:9010/v1",
                "model": "protocol-fixture",
                "environment": {"source": "local protocol fixture; no model"},
            },
            "dataset": [
                {
                    "id": f"example-{size}",
                    "category": str(size),
                    "messages": [
                        {"role": "user", "content": f"协议验证标签：{size} 篇报告，不包含实际文章。"}
                    ],
                }
                for size in (20, 50, 100, 200, 400)
            ],
            "load": {"count": 10, "concurrency": 2},
            "generation": {"max_tokens": 32},
            "quality": {"required_text": ["协议"]},
            "telemetry": {
                "interval_s": 0.2,
                "sources": [{"name": "demo-fixture", "url": "http://127.0.0.1:9010/metrics"}],
            },
            "notes": "固定文本与 usage，只验证软件链路，不代表任何模型或硬件性能。",
        }
    ).model_dump(mode="json")


class ProtocolHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._json({"data": [{"id": "protocol-fixture", "max_model_len": 4096}]})
        elif self.path == "/metrics":
            body = b"# Protocol-only fixture, no real hardware\nvllm:num_requests_waiting 0\nvllm:num_requests_running 1\nvllm:kv_cache_usage_perc 0.2\n"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._json({"error": "not found"}, 404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 1024 * 1024:
                self._json({"error": "invalid request size"}, 413)
                return
            request = json.loads(self.rfile.read(size))
            if request.get("model") != "protocol-fixture":
                self._json({"error": "This fixture serves only protocol-fixture, not a real model"}, 404)
                return
            usage = {"prompt_tokens": 32, "completion_tokens": 8, "total_tokens": 40}
            if not request.get("stream", False):
                self._json(
                    {
                        "object": "chat.completion",
                        "model": "protocol-fixture",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "这是协议测试，不是模型性能。"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": usage,
                    }
                )
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for piece in ("这是协议测试，", "不是", "模型性能。"):
                time.sleep(0.02)
                event = {
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                }
                self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                self.wfile.flush()
            for event in (
                {
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
                {"choices": [], "usage": usage},
            ):
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
        except (ValueError, BrokenPipeError, ConnectionResetError):
            return


def create_server(port=9010):
    server = ThreadingHTTPServer(("127.0.0.1", port), ProtocolHandler)
    server.daemon_threads = True
    return server

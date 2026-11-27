# /// script
# requires-python = ">=3.10"
# ///
"""LLM simulé pour le dev local : API compatible OpenAI (/v1/models, /v1/chat/completions, en flux ou
non) qui répond sans modèle. Sert à essayer Open WebUI, le pipe, le service et OpenCode sans LiteLLM
ni crédit. Bibliothèque standard seule.

Usage : python llm_simule.py [--port 4000]
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def answer(request: dict) -> str:
    messages = request.get("messages") or []
    last = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    content = last.get("content")
    if isinstance(content, list):  # parties de message (texte, images)
        content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    excerpt = " ".join(str(content or "").split())[:120]
    return (f"Réponse simulée (aucun modèle) au message « {excerpt} ». "
            f"Conversation de {len(messages)} messages, modèle demandé : {request.get('model')}.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self.send_json({"object": "list", "data": [{"id": m, "object": "model"} for m in
                                                               ("claude-haiku", "claude-sonnet", "claude-opus")]})
        return self.send_json({"status": "ok"})

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        text, model, now = answer(request), request.get("model"), int(time.time())
        usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        if not request.get("stream"):
            return self.send_json({"id": "simule", "object": "chat.completion", "created": now, "model": model,
                                   "choices": [{"index": 0, "finish_reason": "stop",
                                                "message": {"role": "assistant", "content": text}}],
                                   "usage": usage})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunks = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": text}}]},
                  {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage}]
        for chunk in chunks:
            body = {"id": "simule", "object": "chat.completion.chunk", "created": now, "model": model, **chunk}
            self.wfile.write(b"data: " + json.dumps(body, ensure_ascii=False).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=4000)
    args = parser.parse_args()
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

"""Vercel serverless: GET /api/leaderboard"""
from http.server import BaseHTTPRequestHandler
from _shared import respond, get_submissions, get_best


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        all_subs = get_submissions()
        best_obj = get_best()
        best_score = best_obj["score"] if best_obj else None

        # Best entry per user
        by_user: dict = {}
        for s in all_subs:
            u = s.get("user", "?")
            if u not in by_user or s["score"] > by_user[u]["score"]:
                by_user[u] = s

        board = sorted(by_user.values(), key=lambda s: s["score"], reverse=True)
        for i, entry in enumerate(board):
            entry["rank"] = i + 1

        # History: score + time for chart (no PII beyond score)
        history = sorted(
            [{"score": s["score"], "submitted_at": s["submitted_at"], "promoted": s.get("promoted", False)}
             for s in all_subs],
            key=lambda s: s["submitted_at"],
        )

        respond(self, 200, {
            "leaderboard": board,
            "history": history,
            "best_score": best_score,
            "total_submissions": len(all_subs),
        }, cache="public, max-age=15")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass

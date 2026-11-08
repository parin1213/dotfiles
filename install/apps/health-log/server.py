"""健康記録を新規Markdownとして保存するローカル専用サーバー。"""
import argparse
import hashlib
import importlib.util
import sys
import html
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from threading import Lock
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

KINDS = {"meal": "食事", "weight": "体重", "steps": "歩数"}


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("記録の形式が不正です")
    if set(data) - {"id", "kind", "occurred_at", "text", "value"}:
        raise ValueError("対応していない項目があります")
    record_id = str(UUID(data.get("id", "")))
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError("食事・体重・歩数を選んでください")
    raw_time = data.get("occurred_at", "")
    if not isinstance(raw_time, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", raw_time):
        raise ValueError("記録日時には秒とタイムゾーンを指定してください")
    stamp = datetime.fromisoformat(raw_time)
    if stamp.utcoffset() is None:
        raise ValueError("タイムゾーンが必要です")
    text = data.get("text", "")
    if not isinstance(text, str) or len(text) > 2000 or any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise ValueError("メモは2000文字以内で入力してください")
    value = data.get("value")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("数値を確認してください")
        if kind == "meal" or (kind == "weight" and not 0 < value <= 500) or (kind == "steps" and (not 0 <= value <= 200000 or int(value) != value)):
            raise ValueError("数値の範囲を確認してください")
    if not text.strip() and value is None:
        raise ValueError("ひとこと、または数値を入力してください。不明な数値は空欄で大丈夫です")
    return {"id": record_id, "kind": kind, "occurred_at": stamp.isoformat(), "text": text.strip(), "value": value}


def record_folders(root, *, create=False):
    """既存ログと機械原記録だけを扱い、リンクやVault外への解決を拒否する。"""
    root = Path(root).resolve(strict=True)
    legacy = root / "ログ"
    paths = [legacy]
    current = root
    for part in ("Attachments", "health", "records"):
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("健康記録のディレクトリにリンクは使えません")
        if create:
            current.mkdir(exist_ok=True)
        if current.exists() and (not current.is_dir() or not current.resolve().is_relative_to(root)):
            raise ValueError("健康記録の保存先が不正です")
    paths.append(current)
    for path in paths:
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("健康記録のディレクトリにリンクは使えません")
        if path.exists() and (not path.is_dir() or not path.resolve().is_relative_to(root)):
            raise ValueError("健康記録の保存先が不正です")
    return [path for path in paths if path.is_dir()]


def refresh_dashboard(root):
    """保存成功と表示生成の成否を分離。例外や入力値は外へ出さない。"""
    try:
        path = Path(__file__).resolve().with_name("dashboard.py")
        name = "health_dashboard_generator"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        module.generate(Path(root))
        return "success"
    except Exception:
        return "error"


class Store:
    def __init__(self, vault):
        self.root = Path(vault).resolve(strict=True)
        self.legacy_folder = self.root / "ログ"
        self.folder = self.legacy_folder
        if not self.folder.is_dir() or self.folder.is_symlink() or self.folder.resolve().parent != self.root:
            raise ValueError("既存Vault内の実ディレクトリ「ログ」が必要です")
        self.folder = record_folders(self.root, create=True)[-1]
        self.lock = Lock()
        git_dir = self.root / ".git"
        if git_dir.exists() and (not git_dir.is_dir() or git_dir.is_symlink()):
            raise ValueError("通常の.gitディレクトリを持つVaultを指定してください")
        self.staging = git_dir if git_dir.is_dir() else self.root
        self.sync_lock = self.staging / "obsidian-vault-sync.lock"

    @contextmanager
    def exclude_sync(self):
        try:
            self.sync_lock.mkdir()
        except FileExistsError:
            raise OSError("同期または保存の処理中です。少し待って再試行してください") from None
        try:
            yield
        finally:
            self.sync_lock.rmdir()

    def save(self, data):
        with self.lock, self.exclude_sync():
            saved = self._save(data)
            return {**saved, "dashboard_status": refresh_dashboard(self.root)}

    def record_paths(self, pattern):
        return sorted(path for folder in record_folders(self.root) for path in folder.glob(pattern))

    def _save(self, data, *, record_day=None, provenance=None):
        record = validate(data)
        stamp = datetime.fromisoformat(record["occurred_at"])
        note_day = record_day or str(stamp.date())
        matches = self.record_paths(f"*_健康記録_*_{record['id']}.md")
        if len(matches) > 1:
            raise ValueError("同じIDの記録が複数あります")
        target = matches[0] if matches else self.folder / f"{note_day}_健康記録_{stamp:%H%M}_{record['id']}.md"
        hash_input = record if provenance is None else {"record": record, "date": note_day, "provenance": provenance}
        digest = hashlib.sha256(json.dumps(hash_input, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        value = "null" if record["value"] is None else str(record["value"])
        unit = {"meal": "", "weight": "kg", "steps": "steps"}[record["kind"]]
        literal = re.sub(r"([\\!\[\]()`*_#|~])", r"\\\1", html.escape(record["text"], quote=False))
        quoted = "\n".join("> " + line for line in literal.splitlines()) or "> メモなし"
        source = "manual" if provenance is None else "google_health"
        extra = "" if provenance is None else "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in sorted(provenance.items()))
        body = (f"---\ntype: log\ndate: {note_day}\ntags: [健康, アプリ記録]\n"
                f"record_id: {record['id']}\nkind: {record['kind']}\n"
                f"occurred_at: {record['occurred_at']}\nsource: {source}\n"
                f"value: {value}\nunit: {json.dumps(unit)}\n{extra}content_hash: {digest}\n---\n\n"
                f"# {KINDS[record['kind']]}の記録\n\n"
                f"記録日時: {record['occurred_at']}\n\n"
                f"数値: {'未記録' if record['value'] is None else str(record['value']) + ' ' + unit}\n\n"
                f"## {'本人から受け取った内容' if provenance is None else 'APIから取得した内容'}\n\n{quoted}\n\n"
                "関連: [[健康づくりの開始計画と記録ルール]]\n")
        # .git内で全量を書き終えてから、新規ファイルとして一度に公開する。
        descriptor, temporary = tempfile.mkstemp(prefix=".health-log-", dir=self.staging)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as out:
                out.write(body)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.is_symlink() or target.read_text(encoding="utf-8") != body:
                    raise ValueError("同じIDの別内容があります。元の記録を上書きしません") from None
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {"path": target.relative_to(self.root).as_posix(), "message": "残せたことを大切にしよう。忙しい日は、これだけで大丈夫。"}


def make_server(store, port=8787, *, public_origin=None, tailnet_user=None):
    static = Path(__file__).parent
    if bool(public_origin) != bool(tailnet_user):
        raise ValueError("HTTPSのoriginと本人のTailscaleログイン名を両方指定してください")
    if public_origin:
        parsed = urlsplit(public_origin)
        if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".ts.net")
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("Tailscale内HTTPSのoriginだけを指定してください")
        if not tailnet_user.isascii() or any(c.isspace() for c in tailnet_user):
            raise ValueError("本人のTailscaleログイン名を指定してください")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # 健康データや入力値をアクセスログに残さない。

        def send(self, status, body, mime="application/json; charset=utf-8"):
            raw = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            hosts = {f"127.0.0.1:{self.server.server_port}"}
            if public_origin:
                hosts.add(urlsplit(public_origin).netloc)
                # Tailscale Serveが上書きする認証ヘッダーを、loopbackプロキシだけで受ける。
                if self.headers.get_all("Tailscale-User-Login") != [tailnet_user]:
                    return False
            return self.headers.get_all("Host") in [[host] for host in hosts]

        def do_GET(self):
            if not self.allowed():
                return self.send(403, '{}')
            path = urlsplit(self.path).path
            if path == "/api/status":
                from sync_state import describe
                state = describe()
                return self.send(200, json.dumps({"steps": state["steps_connection"], **state, "storage": "Vaultへの新規保存", "sync": "Git同期の完了は未確認"}, ensure_ascii=False))
            assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                      "/sw.js": ("sw.js", "text/javascript"),
                      "/icon-192.png": ("icon-192.png", "image/png"), "/icon-512.png": ("icon-512.png", "image/png"),
                      "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json")}
            if path not in assets:
                return self.send(404, '{}')
            name, mime = assets[path]
            self.send(200, (static / name).read_bytes(), mime)

        def do_POST(self):
            origin = public_origin or f"http://127.0.0.1:{self.server.server_port}"
            if not self.allowed() or self.headers.get_all("Origin") != [origin]:
                return self.send(403, '{}')
            if self.path != "/api/records":
                return self.send(404, '{}')
            try:
                if self.headers.get("Content-Type") != "application/json":
                    raise ValueError("JSONで送信してください")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ValueError("入力サイズを確認してください")
                result = store.save(json.loads(self.rfile.read(size)))
                self.send(200, json.dumps(result, ensure_ascii=False))
            except (ValueError, TypeError, AttributeError, OverflowError):
                self.send(400, json.dumps({"error": "入力を確認してください。同じIDの内容変更は保存できません。入力は画面に残っています。"}, ensure_ascii=False))
            except OSError:
                self.send(503, json.dumps({"error": "保存できませんでした。入力を残しているので、再度お試しください。"}, ensure_ascii=False))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="健康記録。外部公開せずローカルだけで起動します")
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--port", default=8787, type=int)
    parser.add_argument("--public-origin", help="承認後に使うTailscale ServeのHTTPS origin")
    parser.add_argument("--tailnet-user", help="許可する本人のTailscaleログイン名（完全一致）")
    args = parser.parse_args()
    service = make_server(Store(args.vault), args.port, public_origin=args.public_origin, tailnet_user=args.tailnet_user)
    print(f"健康記録: http://127.0.0.1:{service.server_port} （歩数連携は未接続）")
    service.serve_forever()

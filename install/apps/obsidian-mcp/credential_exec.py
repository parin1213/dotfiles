"""暗号化資格情報を実行時ディレクトリへ展開してゲートウェイを起動する。"""

import os
from pathlib import Path
import subprocess
import sys


CREDENTIALS = ("github-client-secret", "jwt-signing-key", "storage-encryption-key")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("起動するPythonファイルを指定してください")
    runtime_value = os.environ.get("RUNTIME_DIRECTORY")
    if not runtime_value:
        raise SystemExit("systemdのRuntimeDirectoryが必要です")
    runtime = Path(runtime_value)
    if not runtime.is_absolute() or not runtime.is_dir() or runtime.stat().st_uid != os.getuid():
        raise SystemExit("実行時ディレクトリの所有者とパスを確認してください")
    runtime = runtime / "credentials"
    runtime.mkdir(mode=0o700, exist_ok=True)
    source = Path.home() / ".local/share/obsidian-mcp/credentials"
    for name in CREDENTIALS:
        target = runtime / name
        try:
            result = subprocess.run(
                ["systemd-creds", "decrypt", "--user", f"--name={name}",
                 str(source / f"{name}.cred"), str(target)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise SystemExit(f"資格情報の展開に失敗しました: {name}") from None
        if result.returncode != 0:
            raise SystemExit(f"資格情報を復号できません: {name}")
        target.chmod(0o600)
    os.environ["CREDENTIALS_DIRECTORY"] = str(runtime)
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])


if __name__ == "__main__":
    main()

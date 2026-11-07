"""承認後の同期サービス専用。暗号化資格情報を実行時だけ復号する。"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit("起動する同期プログラムが必要です")
    runtime_value = os.environ.get("RUNTIME_DIRECTORY")
    if not runtime_value or os.name != "posix":
        raise SystemExit("systemdユーザーサービスの実行時ディレクトリが必要です")
    runtime = Path(runtime_value)
    source = Path.home() / ".local/share/health-steps-sync/credentials/google-health.cred"
    try:
        if (not runtime.is_absolute() or not runtime.is_dir() or runtime.is_symlink()
                or runtime.stat().st_uid != os.getuid() or source.is_symlink()
                or not source.is_file() or source.stat().st_uid != os.getuid()
                or source.stat().st_mode & 0o077):
            raise ValueError()
        target_folder = runtime / "credentials"
        target_folder.mkdir(mode=0o700, exist_ok=True)
        if target_folder.is_symlink() or target_folder.stat().st_uid != os.getuid():
            raise ValueError()
        target_folder.chmod(0o700)
        target = target_folder / "google-health.json"
        if target.is_symlink():
            raise ValueError()
        result = subprocess.run(["systemd-creds", "decrypt", "--user", "--name=google-health", str(source), str(target)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode:
            raise ValueError()
        target.chmod(0o600)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise SystemExit("同期用資格情報を安全に展開できません。内容は出力しません") from None
    os.environ["CREDENTIALS_DIRECTORY"] = str(target_folder)
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])


if __name__ == "__main__":
    main()

#!/usr/bin/python3
"""Ubuntu Live の RAM 上で、保守用の鍵認証 SSH 接続を用意する。"""
import glob
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


if os.geteuid() != 0 or "boot=casper" not in Path("/proc/cmdline").read_text().split():
    raise SystemExit("Ubuntu Live から root で実行してください")
if subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "/"], text=True).strip() != "overlay":
    raise SystemExit("RAM 上の Live 環境ではないため中止します")

media = Path(sys.argv[1]).resolve()
if not media.is_relative_to(Path("/cdrom")):
    raise SystemExit("保守ファイルの場所が USB 起動メディアではありません")
config = json.loads((media / "config.json").read_text())
for name in ["root_uuid", "wifi_uuid"]:
    if not re.fullmatch(r"[0-9a-f-]{36}", config[name]):
        raise SystemExit("UUID の形式が不正です")
peer = str(ipaddress.IPv4Address(config["peer_ipv4"]))
public_key = config["public_key"].strip()
if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?", public_key):
    raise SystemExit("SSH 公開鍵の形式が不正です")

work = Path("/run/dotfiles-maintenance")
work.mkdir(mode=0o700, exist_ok=True)
installed = work / "installed"
installed.mkdir(exist_ok=True)
network_run = work / "network-run"
network_run.mkdir(exist_ok=True)
device = Path("/dev/disk/by-uuid") / config["root_uuid"]
def restore_network():
    mounted = bound = False
    try:
        run("mount", "-o", "ro,noload", str(device), str(installed))
        mounted = True
        run("mount", "--bind", str(network_run), str(installed / "run"))
        bound = True
        # 秘密情報を表示・抽出せず、公式 CLI で接続設定を RAM 上に生成して読む。
        with (work / "network.log").open("w") as log:
            run("netplan", "generate", "--root-dir", str(installed), stdout=log, stderr=log)
            profiles = glob.glob(str(network_run / "NetworkManager/system-connections" / ("*" + config["wifi_uuid"] + "*.nmconnection")))
            if len(profiles) != 1:
                raise RuntimeError("指定した Wi-Fi 接続設定を一意に特定できません")
            run("nmcli", "connection", "load", profiles[0], stdout=log, stderr=log)
            run("nmcli", "--wait", "60", "connection", "up", "uuid", config["wifi_uuid"], stdout=log, stderr=log)
    finally:
        if bound:
            run("umount", str(installed / "run"))
        if mounted:
            run("umount", str(installed))

# /run は noexec のため、実行ファイルは Live 環境の overlay に置く。
# 認証ファイルは、他ユーザーが書き込めない /run 配下に保持する。
tools = Path("/opt/dotfiles-maintenance-tools")
tools.mkdir(mode=0o700, exist_ok=True)
packages = sorted((media / "packages").glob("*.deb"))
if not packages:
    raise SystemExit("保守用パッケージがありません")
for package in packages:
    run("dpkg-deb", "-x", str(package), str(tools))
shutil.copy2(tools / "etc/pam.d/sshd", "/etc/pam.d/sshd")
try:
    pwd.getpwnam("sshd")
except KeyError:
    run("useradd", "--system", "--no-create-home", "--home-dir", "/run/sshd", "--shell", "/usr/sbin/nologin", "sshd")
Path("/run/sshd").mkdir(mode=0o755, exist_ok=True)
key = work / "host_ed25519"
if not key.exists():
    run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key))
authorized = work / "authorized_keys"
authorized.write_text(f'from="{peer}",no-agent-forwarding,no-port-forwarding,no-X11-forwarding {public_key}\n')
authorized.chmod(0o600)
sshd_config = work / "sshd_config"
sshd_config.write_text(f"""Port 2222
HostKey {key}
PidFile {work}/sshd.pid
AuthorizedKeysFile {authorized}
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AllowUsers root
AllowTcpForwarding no
X11Forwarding no
UsePAM yes
Subsystem sftp internal-sftp
""")
env = os.environ.copy()
env["LD_LIBRARY_PATH"] = str(tools / "usr/lib/x86_64-linux-gnu")
sshd = tools / "usr/sbin/sshd"
run(str(sshd), "-t", "-f", str(sshd_config), env=env)
run(str(sshd), "-f", str(sshd_config), env=env)
print("保守用 SSH をポート 2222 で起動しました。", flush=True)
try:
    restore_network()
except subprocess.CalledProcessError as error:
    print(f"Wi-Fi の自動接続処理で {error.cmd[0]} が終了コード {error.returncode} を返しました。")
    print("Ubuntu の画面から Wi-Fi に接続してください。SSH は起動済みです。")
else:
    print("Wi-Fi に接続しました。内蔵ディスクはアンマウント済みです。")

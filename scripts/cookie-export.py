"""从 Chrome 专用 profile 导出 cookie：Netscape cookies.txt、合并 all.txt、单行 cookie 字符串。

只支持 Windows：依赖 DPAPI 解开 Chrome 的 Local State 密钥。

用法：
    python scripts/cookie-export.py
    python scripts/cookie-export.py --profile-dir "%LOCALAPPDATA%\\tools\\chrome-ytdlp"
    python scripts/cookie-export.py --profile-dir "D:\\chrome-profile" --out "D:\\视频下载\\.cookies"

--profile-dir 可以给 Chrome 的 user-data-dir，也可以直接给 Default 目录。
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DOMAINS = {
    "douyin": ["douyin.com"],
    "xiaohongshu": ["xiaohongshu.com", "xhscdn.com"],
    "bilibili": ["bilibili.com", "bilibili.cn", "hdslb.com"],
}


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def dpapi_unprotect(data: bytes) -> bytes:
    """用当前 Windows 用户的 DPAPI 解开一段密文。"""
    buf_in = DATA_BLOB(
        len(data),
        ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)),
    )
    buf_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(buf_in), None, None, None, None, 0, ctypes.byref(buf_out)
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(buf_out.pbData, buf_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(buf_out.pbData)


def get_key(profile_dir: Path) -> bytes:
    """从 user-data-dir 的 Local State 里取 Chrome 的 AES 密钥。"""
    state_path = profile_dir.parent / "Local State"
    with state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)
    enc = base64.b64decode(state["os_crypt"]["encrypted_key"])
    if enc[:5] != b"DPAPI":
        raise RuntimeError(f"unexpected encrypted_key prefix: {enc[:5]!r}")
    return dpapi_unprotect(enc[5:])


def decrypt(blob: bytes, key: bytes, host: str) -> str:
    """解开 Chrome 的 cookie 密文，返回明文值。"""
    if not blob:
        return ""
    if blob[:3] in (b"v10", b"v20"):
        nonce, payload = blob[3:15], blob[15:]
        plain = AESGCM(key).decrypt(nonce, payload, None)
        # Chrome 130+ 在明文头部塞了 host_key 的 SHA256 前 32 字节
        digest = hashlib.sha256(host.encode("utf-8")).digest()
        if plain[:32] == digest:
            plain = plain[32:]
        return plain.decode("utf-8", "replace")
    # 很老的 Chrome 或非 Windows 平台会用 DPAPI 直接加密
    return dpapi_unprotect(blob).decode("utf-8", "replace")


def resolve_profile(path: Path) -> Path:
    """接受 user-data-dir 或 Default 目录，返回真正含 Network/Cookies 的目录。"""
    path = path.expanduser().resolve()
    if (path / "Network" / "Cookies").exists():
        return path
    if (path / "Default" / "Network" / "Cookies").exists():
        return path / "Default"
    raise SystemExit(
        f"找不到 cookie 数据库：{path}\\Network\\Cookies\n"
        "确认 Chrome profile 路径，并至少打开过一次该 profile。"
    )


def chrome_time(expires_utc: int | None) -> int:
    """Chrome 的 1601 纪秒转 Unix 秒。"""
    if not expires_utc:
        return 0
    return max(int(expires_utc / 1_000_000 - 11644473600), 0)


def main() -> None:
    default_profile = Path(os.environ.get("LOCALAPPDATA", "")) / "tools" / "chrome-ytdlp"
    default_out = Path(__file__).resolve().parent.parent / ".cookies"

    parser = argparse.ArgumentParser(description="导出 Chrome cookie 给 yt-dlp 使用")
    parser.add_argument(
        "--profile-dir",
        default=str(default_profile),
        help="Chrome user-data-dir 或 Default 目录",
    )
    parser.add_argument("--out", default=str(default_out), help="输出目录")
    args = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("这个脚本依赖 Windows DPAPI，只能在 Windows 上运行。")

    profile_dir = resolve_profile(Path(args.profile_dir))
    out_dir = Path(args.out).expanduser().resolve()
    db_src = profile_dir / "Network" / "Cookies"
    key = get_key(profile_dir)

    tmp_dir = Path(tempfile.gettempdir()) / "video-download-pipeline"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_tmp = tmp_dir / "cookie_export.db"
    shutil.copy2(db_src, db_tmp)

    con = sqlite3.connect(db_tmp)
    try:
        rows = con.execute(
            "select host_key, name, encrypted_value, path, expires_utc, is_secure "
            "from cookies"
        ).fetchall()
    finally:
        con.close()

    decoded = []
    for host, name, blob, path, expires, secure in rows:
        try:
            value = decrypt(blob, key, host)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! 解密失败 {host} {name}: {exc}", file=sys.stderr)
            continue
        if not value:
            continue
        decoded.append((host, name, value, path, expires, secure))

    out_dir.mkdir(parents=True, exist_ok=True)
    header = [
        "# Netscape HTTP Cookie File",
        f"# exported {time.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    all_lines = list(header)
    all_seen: set[tuple[str, str, str]] = set()

    for slug, suffixes in DOMAINS.items():
        picked = [
            c
            for c in decoded
            if any(c[0].lstrip(".").endswith(s) for s in suffixes)
        ]
        if not picked:
            continue

        lines = list(header)
        for host, name, value, path, expires, secure in picked:
            flag = "TRUE" if host.startswith(".") else "FALSE"
            line = "\t".join(
                [
                    host,
                    flag,
                    path or "/",
                    "TRUE" if secure else "FALSE",
                    str(chrome_time(expires)),
                    name,
                    value,
                ]
            )
            lines.append(line)
            key3 = (host, name, path or "/")
            if key3 not in all_seen:
                all_seen.add(key3)
                all_lines.append(line)

        (out_dir / f"{slug}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )

        # 单行 cookie 字符串，同名 cookie 只留过期时间最晚的一个
        best: dict[str, tuple] = {}
        for c in picked:
            if c[0].lstrip(".").count(".") > 1:
                continue
            if c[1] not in best or (c[4] or 0) > (best[c[1]][4] or 0):
                best[c[1]] = c
        cookie_str = "; ".join(f"{n}={v}" for _, n, v, *_ in best.values())
        (out_dir / f"{slug}.str").write_text(
            cookie_str + "\n", encoding="utf-8", newline="\n"
        )

        print(f"[{slug}] {len(picked)} cookies -> {slug}.txt ({len(cookie_str)} chars in .str)")

    (out_dir / "all.txt").write_text(
        "\n".join(all_lines) + "\n", encoding="utf-8", newline="\n"
    )

    now = int(time.time())
    expired = [c for c in decoded if chrome_time(c[4]) and chrome_time(c[4]) < now]
    print(
        f"\n解密 {len(decoded)} 条，已过期 {len(expired)} 条，"
        f"all.txt 写入 {len(all_lines) - 3} 条，输出目录：{out_dir}"
    )
    if not decoded:
        print("没有解出任何 cookie：确认 Chrome 已登录，且关闭了该 profile 的所有窗口。")


if __name__ == "__main__":
    main()

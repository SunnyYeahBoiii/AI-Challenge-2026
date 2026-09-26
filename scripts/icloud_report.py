#!/usr/bin/env python3
"""Báo cáo dung lượng iCloud Drive, chạy định kỳ bằng launchd (macOS)."""

from __future__ import annotations

import argparse
import os
import plistlib
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ICLOUD_ROOT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
REPORT_DIR = Path(__file__).resolve().parent / "logs" / "icloud"
LABEL = "com.frameseeker.icloud-report"
PLIST_PATH = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
UF_DATALESS = 0x4000000
BLOCK_SIZE = 512
TOP_N_DEFAULT = 10
WEEKDAY = 1
RUN_HOUR = 9
SIZE_UNITS = ("B", "KB", "MB", "GB", "TB")
PERMISSION_HINT = (
    "Khong doc duoc iCloud Drive (PermissionError).\n"
    "Cap Full Disk Access cho /usr/bin/python3:\n"
    "System Settings > Privacy & Security > Full Disk Access > + > /usr/bin/python3\n"
    "roi chay lai: launchctl kickstart -p gui/$(id -u)/" + LABEL
)


@dataclass
class Usage:
    """Dung lượng một cây thư mục: kích thước logic, dung lượng thật và số file."""

    file_count: int = 0
    logical_bytes: int = 0
    on_disk_bytes: int = 0
    dataless_count: int = 0

    def add(self, file_stat: os.stat_result) -> None:
        self.file_count += 1
        self.logical_bytes += file_stat.st_size
        self.on_disk_bytes += getattr(file_stat, "st_blocks", 0) * BLOCK_SIZE
        if getattr(file_stat, "st_flags", 0) & UF_DATALESS:
            self.dataless_count += 1


def format_size(num_bytes: int) -> str:
    """Đổi số byte sang đơn vị dễ đọc."""
    size = float(num_bytes)
    for unit in SIZE_UNITS:
        if size < 1024 or unit == SIZE_UNITS[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {SIZE_UNITS[-1]}"


def measure(path: Path) -> Usage:
    """Cộng dồn dung lượng mọi file thông thường dưới `path`."""
    usage = Usage()
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                file_stat = os.lstat(os.path.join(dirpath, name))
            except OSError:
                continue
            if stat.S_ISREG(file_stat.st_mode):
                usage.add(file_stat)
    return usage


def usage_of(path: Path, is_dir: bool) -> Usage:
    """Đo một mục cấp cao nhất, bỏ qua mục không đọc được."""
    if is_dir:
        return measure(path)
    try:
        file_stat = path.lstat()
    except OSError:
        return Usage()
    usage = Usage()
    if stat.S_ISREG(file_stat.st_mode):
        usage.add(file_stat)
    return usage


def top_entries(root: Path, limit: int) -> list[tuple[int, str]]:
    """Trả về `limit` mục lớn nhất cấp cao nhất, lớn nhất đứng trước."""
    entries: list[tuple[int, str]] = []
    with os.scandir(root) as scan:
        for entry in scan:
            usage = usage_of(Path(entry.path), entry.is_dir(follow_symlinks=False))
            if usage.logical_bytes:
                entries.append((usage.logical_bytes, entry.name))
    entries.sort(reverse=True)
    return entries[:limit]


def render(root: Path, limit: int) -> str:
    """Dựng nội dung báo cáo dạng văn bản."""
    total = measure(root)
    lines = [
        f"iCloud Drive: {root}",
        f"Thoi diem: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Dung luong that:   {format_size(total.on_disk_bytes)}",
        f"Kich thuoc logic: {format_size(total.logical_bytes)}",
        f"So file:          {total.file_count}",
        f"Chua tai ve (cloud only): {total.dataless_count}",
        "",
        f"Top {limit} muc lon nhat:",
    ]
    lines.extend(f"  {format_size(size):>10}  {name}" for size, name in top_entries(root, limit))
    return "\n".join(lines) + "\n"


def write_report(content: str) -> Path:
    """Lưu báo cáo theo timestamp và cập nhật `latest.txt`."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report_path = REPORT_DIR / f"icloud-{stamp}.txt"
    report_path.write_text(content, encoding="utf-8")
    (REPORT_DIR / "latest.txt").write_text(content, encoding="utf-8")
    return report_path


def build_plist() -> dict[str, object]:
    """Sinh nội dung LaunchAgent chạy script hằng tuần."""
    return {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/python3", str(Path(__file__).resolve()), "--quiet"],
        "StartCalendarInterval": {"Weekday": WEEKDAY, "Hour": RUN_HOUR, "Minute": 0},
        "StandardOutPath": str(REPORT_DIR / "launchd.out.log"),
        "StandardErrorPath": str(REPORT_DIR / "launchd.err.log"),
        "RunAtLoad": False,
    }


def install() -> int:
    """Đăng ký LaunchAgent cho user hiện tại."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(build_plist(), handle)
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{LABEL}"], check=False, capture_output=True
    )
    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(PLIST_PATH)], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"launchctl bootstrap that bai: {result.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"Da cai LaunchAgent: {PLIST_PATH} (chay moi thu {RUN_HOUR}:00)")
    return 0


def uninstall() -> int:
    """Gỡ LaunchAgent và xoá plist."""
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{LABEL}"], check=False, capture_output=True
    )
    PLIST_PATH.unlink(missing_ok=True)
    print("Da go LaunchAgent.")
    return 0


def status() -> int:
    """In trạng thái đăng ký của LaunchAgent."""
    domain = f"gui/{os.getuid()}"
    result = subprocess.run(
        ["launchctl", "print", f"{domain}/{LABEL}"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Chua chay: {LABEL} (chay: python3 {Path(__file__).name} --install)")
        return 1
    for line in result.stdout.splitlines():
        if "state" in line or "last exit code" in line:
            print(line.strip())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ICLOUD_ROOT)
    parser.add_argument("--top", type=int, default=TOP_N_DEFAULT)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.install:
        return install()
    if args.uninstall:
        return uninstall()
    if args.status:
        return status()
    if not args.root.is_dir():
        print(f"Khong tim thay iCloud Drive: {args.root}", file=sys.stderr)
        return 1
    try:
        content = render(args.root, args.top)
    except PermissionError:
        print(PERMISSION_HINT, file=sys.stderr)
        return 2
    if not args.quiet:
        print(content, end="")
    write_report(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

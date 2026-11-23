"""台账完整性检查：track/predictions.jsonl 只允许在末尾追加。
与上一次提交（git HEAD）相比，已有的每一行必须逐字不变，否则退出码 1（CI 失败，不推送）。"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = "track/predictions.jsonl"


def main():
    try:
        old = subprocess.run(["git", "show", f"HEAD:{PATH}"], cwd=ROOT, capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout.splitlines()
    except subprocess.CalledProcessError:
        print("台账尚未提交过，跳过检查")
        return 0
    new = open(os.path.join(ROOT, PATH), encoding="utf-8").read().splitlines()
    if len(new) < len(old) or new[: len(old)] != old:
        bad = next((i for i, (a, b) in enumerate(zip(old, new)) if a != b), min(len(old), len(new)))
        print(f"台账被改写：第 {bad + 1} 行与已提交版本不同（已提交 {len(old)} 行，现在 {len(new)} 行）")
        return 1
    dates = [line.split('"signal_date": "')[1][:10] for line in new if line.strip()]
    if len(dates) != len(set(dates)) or dates != sorted(dates):
        print("台账信号日重复或乱序")
        return 1
    print(f"台账检查通过：已提交 {len(old)} 行未变，新增 {len(new) - len(old)} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())

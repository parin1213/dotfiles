"""健康台帳からプラグイン不要のObsidian表示を生成する（外部通信なし）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

MAX_NOTE = 2_000_000
RAW_DIRS = ("ログ", "Attachments/health/records")


def safe_path(root, relative):
    root = Path(root).resolve(strict=True)
    p = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Vault外のパスは使えません")
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("リンクされた保存先は使えません")
    if not p.resolve().is_relative_to(root):
        raise ValueError("Vault外のパスは使えません")
    return p


def read_note(root, relative):
    p = safe_path(root, relative)
    if not p.exists():
        return ""
    if not p.is_file() or p.stat().st_size > MAX_NOTE:
        raise ValueError("ノートが大きすぎるか形式が不正です")
    return p.read_text(encoding="utf-8-sig")


def cells(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def calorie_display(row):
    """同じ上下限は単一値で表示し、推定範囲は保持する。"""
    return f'{row["low"]:g}' if row["low"] == row["high"] else f'{row["low"]:g}〜{row["high"]:g}'


def calorie_range(text):
    text = text.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*[〜～–−-]\s*(\d+(?:\.\d+)?)", text)
    if m:
        lo, hi = map(float, m.groups())
    else:
        m = re.search(r"\d+(?:\.\d+)?", text)
        if not m:
            return None
        lo = hi = float(m.group())
    if not 0 <= lo <= hi <= 20000:
        raise ValueError("食事の熱量範囲が不正です")
    return lo, hi


def parse_meals(body):
    """最新一覧だけがデータ正本。本文の旧値・提案・詳細は再加算しない。"""
    active = False
    result = {}
    for line in body.splitlines():
        if line.startswith("## 最近の食事"):
            active = True
            continue
        if active and line.startswith("## "):
            break
        if not active or not line.startswith("|"):
            continue
        row = cells(line)
        if len(row) != 6:
            continue
        match = re.search(r"\d{4}-\d{2}-\d{2}", row[0])
        if not match:
            continue
        day = date.fromisoformat(match.group())
        values = calorie_range(row[-1])
        if values is None:
            continue
        # 同じ日が複数あれば最後の明示値で置き換え、足さない。
        result[day] = {"date": day, "low": values[0], "high": values[1],
                       "partial": any("未記録" in c or "未確認" in c for c in row[1:]) or "1食" in row[-1] or "※" in row[-1]}
    return [result[k] for k in sorted(result)]


def parse_weights(body):
    result = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        row = cells(line)
        if len(row) != 3 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0]):
            continue
        try:
            day, value = date.fromisoformat(row[0]), float(row[2])
        except ValueError:
            continue
        if not math.isfinite(value) or not 1 <= value <= 500:
            raise ValueError("体重の値が不正です")
        condition = row[1]
        result[(day, condition)] = {"date": day, "value": value, "condition": condition}
    return sorted(result.values(), key=lambda r: (r["date"], 2 if "就寝" in r["condition"] or "夜" in r["condition"] else 1 if "起床" in r["condition"] or "朝" in r["condition"] else 0, r["condition"]))


def parse_snapshot(body, kind="steps"):
    if not body.startswith("---\n"):
        return None
    fields = {}
    for line in body.split("---", 2)[1].splitlines():
        k, sep, v = line.partition(":")
        if sep:
            fields[k.strip()] = v.strip()
    if kind not in {"steps", "sleep"} or fields.get("kind") != kind:
        return None
    try:
        day = date.fromisoformat(fields.get("window_date", fields.get("date", "")).strip('"'))
        stamp = datetime.fromisoformat(fields["occurred_at"])
        value = json.loads(fields["value"])
        if stamp.utcoffset() is None or isinstance(value, bool) or (value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0)):
            return None
        item = {"date": day, "stamp": stamp, "value": value}
        if kind == "sleep":
            state = fields.get("missing_state", '"present"').strip('"')
            if state not in {"present", "no_sessions", "summary_missing", "overlapping_sessions"}:
                return None
            item["missing_state"] = state
            if state != "present":
                item["value"] = None
        return item
    except (ValueError, TypeError, KeyError):
        return None


def load_snapshots(root, kind):
    latest = {}
    for folder in RAW_DIRS:
        path = safe_path(root, folder)
        if not path.exists():
            continue
        notes = sorted(path.glob("*_健康記録_*_*.md"))
        if len(notes) > 50000:
            raise ValueError("健康記録が多すぎます")
        for note in notes:
            item = parse_snapshot(read_note(root, note.relative_to(root)), kind)
            if not item:
                continue
            old = latest.get(item["date"])
            if old is None or item["stamp"] > old["stamp"]:
                latest[item["date"]] = item
            elif item["stamp"] == old["stamp"] and (item["value"] != old["value"] or item.get("missing_state") != old.get("missing_state")):
                # 同時刻の矛盾は優劣を決めず欠測として表示する。
                old["value"] = None
                if kind == "sleep":
                    old["missing_state"] = "conflict"
    return [latest[k] for k in sorted(latest)]


def load_steps(root):
    return load_snapshots(root, "steps")


def load_sleep(root):
    return load_snapshots(root, "sleep")


def sleep_display(row):
    if row["value"] is not None:
        return f'{row["value"] / 60:.2f}'.rstrip("0").rstrip(".")
    reason = {"no_sessions": "睡眠記録なし", "summary_missing": "時間不明",
              "overlapping_sessions": "記録の重複", "conflict": "同時刻の値が不一致"}.get(row.get("missing_state"))
    return f"欠測（{reason}）" if reason else "欠測"


def text(x, y, value, size=18, color="#334155", anchor="start"):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(str(value))}</text>'


def svg_start(title, subtitle):
    return ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 350" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>',
            '<rect width="760" height="350" rx="16" fill="#f8fafc"/>',
            '<g font-family="sans-serif">', text(24, 35, title, 24, "#0f172a"), text(24, 64, subtitle, 16)]


def chart(title, subtitle, data, kind):
    parts = svg_start(title, subtitle)
    if not data:
        return "".join(parts + [text(380, 190, "記録なし（0ではありません）", 22, anchor="middle"), "</g></svg>"])
    first, last = min(x["date"] for x in data), max(x["date"] for x in data)
    numeric = [r["value"] for r in data if r.get("value") is not None] if kind != "calories" else [r["high"] for r in data]
    low = math.floor(min(numeric) - 1) if numeric and kind == "weight" else 0
    high = math.ceil(max(numeric) + 1) if numeric and kind == "weight" else max(100, math.ceil(max(numeric, default=0) / 100) * 100)
    if kind == "steps":
        high = max(1000, math.ceil(high / 1000) * 1000)
    elif kind == "sleep":
        high = max(4, math.ceil(max(numeric, default=0) / 4) * 4)
    def x(day):
        return 88 + 620 * (day - first).days / max(1, (last - first).days) if first != last else 398
    def y(value):
        return 270 - (value - low) / max(1, high - low) * 170
    for i in range(5):
        v = low + (high - low) * i / 4
        yy = y(v)
        parts += [f'<path d="M78 {yy}H720" stroke="#cbd5e1"/>', text(68, yy + 5, f"{v:g}", 15, anchor="end")]
    # ラベルが狭くならないよう、最大4日を均等に表示。
    dates = sorted({r["date"] for r in data})
    labels = {first + timedelta(days=round(i * (last - first).days / 3)) for i in range(4)} if (last - first).days >= 3 else set(dates)
    for day in sorted(labels):
        parts.append(text(x(day), 300, day.strftime("%m/%d"), 17, anchor="middle"))
    for row in data:
        xx = x(row["date"])
        if kind == "calories":
            col = "#d97706" if row["partial"] else "#2563eb"
            parts.append(f'<path d="M{xx} {y(row["low"])}V{y(row["high"])}" stroke="{col}" stroke-width="12" stroke-linecap="round"/>')
            parts.append(f'<circle cx="{xx}" cy="{y((row["low"] + row["high"]) / 2)}" r="4" fill="#ffffff"/>')
        elif row.get("value") is None:
            parts.append(text(xx, 252, "欠測", 16, "#64748b", "middle"))
        elif kind in {"steps", "sleep"}:
            yy = y(row["value"])
            col = "#a855f7" if kind == "sleep" else "#0891b2"
            label = f'{row["value"]:.2f}'.rstrip("0").rstrip(".") if kind == "sleep" else f'{row["value"]:g}'
            parts.append(f'<rect x="{xx-12}" y="{yy}" width="24" height="{max(1,270-yy)}" rx="4" fill="{col}"/>')
            parts.append(text(xx, yy - 8, label, 16, "#7e22ce" if kind == "sleep" else "#0e7490", "middle"))
        else:
            col = "#2563eb" if "起床" in row["condition"] or "朝" in row["condition"] else "#a855f7"
            parts.append(f'<circle cx="{xx}" cy="{y(row["value"])}" r="6" fill="{col}"><title>{row["date"]} {escape(row["condition"])} {row["value"]}kg</title></circle>')
    footer = "橙：一部未確認 ／ 縦線：推定の下限〜上限" if kind == "calories" else "青：朝・起床時 ／ 紫：その他　欠測期間は線で結びません" if kind == "weight" else "各日の最新累積値のみ。途中取得は終日確定ではありません"
    if kind == "sleep":
        footer = "起床日ごとの最新取得値のみ。欠測は0時間にしません"
    parts += [text(24, 333, footer, 16), "</g></svg>"]
    return "".join(parts)


def write_changed(root, relative, content):
    target = safe_path(root, relative)
    if target.exists() and target.read_text(encoding="utf-8") == content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_path(root, relative)
    fd, temp = tempfile.mkstemp(prefix=".health-view-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True


def generate(vault, *, today=None, now=None):
    root = Path(vault).resolve(strict=True)
    now = now or datetime.now(timezone(timedelta(hours=9)))
    if now.utcoffset() is None:
        raise ValueError("更新日時にはタイムゾーンが必要です")
    now = now.astimezone(timezone(timedelta(hours=9)))
    today = today or now.date()
    meals = parse_meals(read_note(root, "ログ/食事ログ.md"))
    weights = parse_weights(read_note(root, "ログ/体重記録.md"))
    steps = load_steps(root)
    sleep = load_sleep(root)
    recent_weights = [r for r in weights if today - timedelta(days=29) <= r["date"] <= today]
    recent_meals = [r for r in meals if today - timedelta(days=29) <= r["date"] <= today]
    recent_steps = [r for r in steps if today - timedelta(days=13) <= r["date"] <= today]
    recent_sleep = [{**r, "value": r["value"] / 60 if r["value"] is not None else None}
                    for r in sleep if today - timedelta(days=13) <= r["date"] <= today]
    latest_weight = weights[-1] if weights else None
    weight_status = f'最終実測：{latest_weight["date"]}、{latest_weight["value"]:g}kg（{latest_weight["condition"]}）' if latest_weight else "体重の実測なし"
    if latest_weight and (today - latest_weight["date"]).days > 30:
        weight_status += "。30日以上前の記録で、現在の体重ではありません。"
    meal_status = f'{meals[-1]["date"]}：記録分 {calorie_display(meals[-1])} kcal' if meals else "食事の記録なし"
    latest_step = steps[-1] if steps else None
    step_status = f'{latest_step["date"]}：' + (f'{latest_step["value"]:g}歩' if latest_step["value"] is not None else "欠測（0歩ではありません）") if latest_step else "歩数の記録なし"
    latest_observation = max((r["stamp"] for r in steps), default=None)
    acquisition_status = latest_observation.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S JST") if latest_observation else "取得記録なし"
    latest_sleep = sleep[-1] if sleep else None
    sleep_status = (f'{latest_sleep["date"]}起床：{sleep_display(latest_sleep)}' +
                    ("時間" if latest_sleep["value"] is not None else "（0時間ではありません）")) if latest_sleep else "睡眠の記録なし"
    sleep_observation = max((r["stamp"] for r in sleep), default=None)
    sleep_acquisition = sleep_observation.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S JST") if sleep_observation else "取得記録なし"
    outputs = {
        "Attachments/health/weight.svg": chart("体重の実測推移", "kg / 直近30日の実測。測定条件を区別", recent_weights, "weight"),
        "Attachments/health/calories.svg": chart("食事の記録分カロリー", "kcal / 直近30日。推定範囲で表示", recent_meals, "calories"),
        "Attachments/health/steps.svg": chart("日別歩数", "歩 / 直近14日。欠測は0にしない", recent_steps, "steps"),
        "Attachments/health/sleep.svg": chart("睡眠時間", "時間 / 直近14日。日本時間の起床日で集計", recent_sleep, "sleep"),
    }
    rows = []
    meal_map, step_map = {r["date"]: r for r in meals}, {r["date"]: r for r in steps}
    sleep_map = {r["date"]: r for r in sleep}
    for day in sorted(set(meal_map) | set(step_map) | set(sleep_map), reverse=True)[:14]:
        m, s, sl = meal_map.get(day), step_map.get(day), sleep_map.get(day)
        kcal = calorie_display(m) + ("（部分記録）" if m["partial"] else "（記録分）") if m else "未記録"
        walk = f'{s["value"]:g}' if s and s["value"] is not None else "欠測" if s else "未記録"
        rest = sleep_display(sl) if sl else "未記録"
        rows.append(f"| {day} | {kcal} | {walk} | {rest} |")
    outputs["ログ/健康ダッシュボード.md"] = "\n".join([
        "---", "type: log", "tags: [健康, ダッシュボード]", "generated: true", "---", "# 健康ダッシュボード", "",
        "体重・食事・歩数・睡眠を同じ入口で振り返るページ。グラフは台帳から生成し、ここへ手入力はしません。", "",
        "## 最新の記録", f"- **体重**：{weight_status}", f"- **食事**：{meal_status}", f"- **歩数**：{step_status}", f"- **睡眠**：{sleep_status}",
        f"- **歩数の最終取得日時**：{acquisition_status}（保存された観測の時刻。同期の最終試行時刻ではありません）",
        f"- **睡眠の最終取得日時**：{sleep_acquisition}（保存された観測の時刻。同期の最終試行時刻ではありません）",
        f'- **食事の最新記録日**：{meals[-1]["date"] if meals else "未記録"}',
        f'- **体重の最新実測日**：{latest_weight["date"] if latest_weight else "未記録"}', "",
        "[[食事ログ|食事を確認・訂正]] · [[体重記録|体重を記録]]",
        "[[健康方針|目標・生活方針]] · [[健診記録|健診・受診の記録]]", "",
        "## 体重（直近30日）", "![[Attachments/health/weight.svg]]", "",
        "直近30日の実測だけを拡大表示。過去の記録は[[体重記録]]に保持しています。", "",
        "93〜95kgという記憶による申告は実測点にしません。同条件の記録が増えるまで減量ペースを判定しません。", "",
        "## 食事カロリー", "![[Attachments/health/calories.svg]]", "",
        "記録分の合計で、摂取目標ではありません。未確認の油・間食などは含まれない場合があります。未記録日を0kcalに補完しません。", "",
        "## 歩数", "![[Attachments/health/steps.svg]]", "",
        "同じ日の取得値は足さず、取得時刻が最も新しい値を採用。Google Healthの値で、Google Fitとの同一性や終日確定を保証しません。", "",
        "## 睡眠", "![[Attachments/health/sleep.svg]]", "",
        "Google Healthの睡眠時間を日本時間の起床日ごとに表示。同じ日の取得値は足さず、最も新しい取得を採用します。睡眠記録なし・時間不明・記録の重複は欠測とし、0時間にしません。", "",
        "## 数値一覧", "| 日付（睡眠は起床日） | 食事の記録分 kcal | 歩数 | 睡眠時間 h |", "|---|---:|---:|---:|", *rows, "",
        "## 更新について", "食事・体重の台帳と歩数・睡眠の原記録から再生成する表示です。生成されたグラフを直接直さず、元の記録を訂正してください。", "",
    ])
    # 内容ハッシュには日時を含めず、表示内容が変わった時だけ更新日時を進める。
    dashboard_path = "ログ/健康ダッシュボード.md"
    digest = hashlib.sha256(json.dumps(outputs, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    previous = read_note(root, dashboard_path)
    old_hash = re.search(r"^semantic_sha256: ([0-9a-f]{64})$", previous, re.M)
    old_updated = re.search(r"^updated_at: ([^\n]+)$", previous, re.M)
    updated = now.isoformat(timespec="seconds")
    if old_hash and old_hash.group(1) == digest and old_updated:
        try:
            old_time = datetime.fromisoformat(old_updated.group(1))
            if old_time.utcoffset() is not None:
                updated = old_time.isoformat(timespec="seconds")
        except ValueError:
            pass
    outputs[dashboard_path] = outputs[dashboard_path].replace(
        "generated: true\n", f"generated: true\nupdated_at: {updated}\nsemantic_sha256: {digest}\n", 1)
    updated_display = datetime.fromisoformat(updated).astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S JST")
    outputs[dashboard_path] = outputs[dashboard_path].replace(
        "## 更新について\n", f"## 更新について\n表示内容の最終更新：{updated_display}。内容が同じ再生成では更新日時を変えません。\n\n", 1)
    changed = [path for path, body in outputs.items() if write_changed(root, path, body)]
    return {"changed": changed, "meal_days": len(meals), "weight_measurements": len(weights), "step_days": len(steps), "sleep_days": len(sleep)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Obsidianの健康ダッシュボードを再生成")
    parser.add_argument("--vault", required=True)
    args = parser.parse_args()
    result = generate(args.vault)
    print(f'健康ダッシュボード: {len(result["changed"])}ファイル更新')

"""Проверка labels.jsonl во всех партиях по spec/label.schema.json. Без внешних зависимостей.

Запуск: python3 tools/validate.py
Код возврата 1, если есть ошибки.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "spec" / "label.schema.json").read_text())
PROPS = SCHEMA["properties"]
VALUE_RE = re.compile(r"^[0-9.\-]*$")


ENERGY_UNITS = {"gcal", "kwh", "mwh", "gj"}


def consistency(label: dict) -> list[str]:
    """Те же правила, что labelConsistencyErrors в основном проекте."""
    errors, o = [], label.get("outcome")
    if o == "read":
        if label.get("screenType") != "energy":
            errors.append("outcome=read — только для screenType=energy")
        if not label.get("readable"):
            errors.append("outcome=read, но readable=false")
        if not label.get("valueText"):
            errors.append("outcome=read — нужен valueText")
        if label.get("unit") not in ENERGY_UNITS:
            errors.append(f"outcome=read — единица энергии {sorted(ENERGY_UNITS)}")
    if o == "wrong_screen" and label.get("screenType") == "energy":
        errors.append("outcome=wrong_screen, но screenType=energy")
    if o == "unreadable" and label.get("readable"):
        errors.append("outcome=unreadable, но readable=true")
    return errors


def check_label(label: dict) -> list[str]:
    errors = []
    missing = set(SCHEMA["required"]) - set(label)
    extra = set(label) - set(PROPS)
    if missing:
        errors.append(f"нет полей: {sorted(missing)}")
    if extra:
        errors.append(f"лишние поля: {sorted(extra)}")
    for key in ("outcome", "meterModel", "screenType", "unit"):
        if key in label and label[key] not in PROPS[key]["enum"]:
            errors.append(f"{key}={label[key]!r} не из списка {PROPS[key]['enum']}")
    if not isinstance(label.get("readable"), bool):
        errors.append("readable должно быть true/false")
    for key in ("valueText", "uncertainDigits", "apartmentSticker", "notes"):
        if not isinstance(label.get(key), str):
            errors.append(f"{key} должно быть строкой")
    if isinstance(label.get("valueText"), str) and not VALUE_RE.match(label["valueText"]):
        errors.append(f"valueText={label['valueText']!r}: только цифры, '.', '-'")
    issues = label.get("qualityIssues")
    allowed = PROPS["qualityIssues"]["items"]["enum"]
    if not isinstance(issues, list) or any(i not in allowed for i in issues):
        errors.append(f"qualityIssues: список из {allowed}")
    bbox = label.get("displayBbox")
    if bbox is not None:
        ok = isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in bbox)
        if not ok or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            errors.append(f"displayBbox={bbox}: [x0, y0, x1, y1] в 0..1, x1>x0, y1>y0")
    return errors + consistency(label)


def main() -> int:
    total_errors = labeled = expected = 0
    for batch in sorted((ROOT / "batches").glob("*/")):
        if (batch / "IMPORTED.md").exists():
            continue  # партия уже импортирована в панель — её правят там
        manifest = [json.loads(l) for l in (batch / "manifest.jsonl").read_text().splitlines() if l.strip()]
        ids = {m["id"] for m in manifest}
        expected += len(ids)
        labels_path = batch / "labels.jsonl"
        if not labels_path.exists():
            continue
        seen = set()
        for n, line in enumerate(labels_path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            where = f"{batch.name}/labels.jsonl:{n}"
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"{where}: не JSON ({e})")
                total_errors += 1
                continue
            problems = []
            if row.get("id") not in ids:
                problems.append(f"id {row.get('id')!r} нет в manifest")
            if row.get("id") in seen:
                problems.append("повтор id")
            seen.add(row.get("id"))
            problems += check_label(row.get("label") or {})
            for p in problems:
                print(f"{where}: {p}")
            total_errors += len(problems)
            labeled += 1
    print(f"Размечено {labeled} из {expected}, ошибок: {total_errors}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())

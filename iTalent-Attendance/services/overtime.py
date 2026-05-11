from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from math import ceil
from typing import Any


@dataclass(frozen=True)
class AttendanceRow:
    date: str
    first_card: str
    last_card: str
    date_type: str
    status: str
    overtime_minutes: int
    applied_overtime_minutes: int
    absence_minutes: int
    leave_minutes: int
    is_workday: bool
    note: str
    remark: str

    @property
    def net_minutes(self) -> int:
        return self.overtime_minutes + self.applied_overtime_minutes - self.absence_minutes - self.leave_minutes


@dataclass(frozen=True)
class AttendanceSummary:
    rows: list[AttendanceRow]
    total_minutes: int
    workday_overtime_minutes: int
    restday_overtime_minutes: int
    applied_overtime_minutes: int
    absence_minutes: int
    leave_minutes: int

    @property
    def total_hours(self) -> float:
        return round(self.total_minutes / 60, 2)


def merge_overtime_records(
    attendance_data: dict[str, Any],
    overtime_data: dict[str, Any],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    result = deepcopy(attendance_data)
    attendance_rows = result.setdefault("biz_data", [])
    row_by_date: dict[str, dict[str, Any]] = {}
    for row in attendance_rows:
        date_text = _field_value(row, "SwipingCardDate") or _field_text(row, "SwipingCardDate")
        normalized = _normalize_date_text(date_text)
        if normalized:
            row_by_date[normalized] = row

    for date_text, remarks in _overtime_remarks_by_date(overtime_data, start_date, end_date).items():
        merged_remark = "；".join(remarks)
        row = row_by_date.get(date_text)
        if row:
            current = _field_text(row, "RetroactiveRemark")
            row["RetroactiveRemark"] = _field(current + "；" + merged_remark if current else merged_remark)
        else:
            attendance_rows.append(_synthetic_overtime_row(date_text, merged_remark))
    return result


def summarize_attendance(
    response_data: dict[str, Any],
    workday_end: str = "17:30",
    lunch_start: str = "12:00",
    lunch_end: str = "13:00",
) -> AttendanceSummary:
    rows: list[AttendanceRow] = []
    for raw in response_data.get("biz_data", []):
        row = _parse_row(raw, workday_end, lunch_start, lunch_end)
        if row:
            rows.append(row)

    total = sum(row.net_minutes for row in rows)
    workday_total = sum(row.overtime_minutes for row in rows if row.is_workday)
    restday_total = sum(row.overtime_minutes for row in rows if not row.is_workday)
    applied_total = sum(row.applied_overtime_minutes for row in rows)
    absence_total = sum(row.absence_minutes for row in rows)
    leave_total = sum(row.leave_minutes for row in rows)
    return AttendanceSummary(
        rows=rows,
        total_minutes=total,
        workday_overtime_minutes=workday_total,
        restday_overtime_minutes=restday_total,
        applied_overtime_minutes=applied_total,
        absence_minutes=absence_total,
        leave_minutes=leave_total,
    )


def _overtime_remarks_by_date(overtime_data: dict[str, Any], start_date: str, end_date: str) -> dict[str, list[str]]:
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)
    remarks: dict[str, list[str]] = {}
    for row in overtime_data.get("biz_data", []):
        if _field_value(row, "ApproveStatus") not in {"", "2"}:
            continue
        if _field_value(row, "IsCancel") not in {"", "0"}:
            continue
        date_text = _normalize_date_text(_field_value(row, "OverTimeDate") or _field_text(row, "OverTimeDate"))
        row_date = _parse_date(date_text)
        if not date_text or row_date is None:
            continue
        if start_dt and row_date < start_dt:
            continue
        if end_dt and row_date > end_dt:
            continue

        start_text = _time_text(_field_text(row, "StartTime") or _field_value(row, "StartTime"))
        stop_text = _time_text(_field_text(row, "StopTime") or _field_value(row, "StopTime"))
        status_text = _field_text(row, "ApproveStatus") or "通过"
        duration_text = _field_text(row, "OverTimeDurationIncludeUnit") or _field_value(row, "OverTimeDurationIncludeUnit")
        time_range = f"{start_text}-{stop_text}" if start_text and stop_text else duration_text
        duration = f"（{duration_text}）" if duration_text and duration_text != time_range else ""
        remark = f"加班 {time_range}{duration}[{status_text}]"
        remarks.setdefault(date_text, []).append(remark)
    return remarks


def _parse_row(
    raw: dict[str, Any],
    workday_end: str,
    lunch_start: str,
    lunch_end: str,
) -> AttendanceRow | None:
    first_text = _field_text(raw, "ActualForFirstCard")
    last_text = _field_text(raw, "ActualForLastCard")
    date_text = _field_value(raw, "SwipingCardDate") or _field_text(raw, "SwipingCardDate")
    if not date_text:
        return None

    first_dt = _parse_datetime(first_text)
    last_dt = _parse_datetime(last_text)
    date_type_value = _field_value(raw, "DateType")
    date_type_text = _field_text(raw, "DateType")
    status_text = _field_text(raw, "AttendanceStatus")
    remark_text = _field_text(raw, "RetroactiveRemark")
    row_date = _parse_date(date_text)
    is_saturday = row_date.weekday() == 5 if row_date else False
    is_workday = date_type_value == "1" and not is_saturday
    is_today = date_text == datetime.today().strftime("%Y/%m/%d")
    effective_first_dt, effective_last_dt = _apply_remark_work_times(first_dt, last_dt, remark_text, row_date)

    minutes = 0
    applied_minutes = 0
    note = ""
    if is_today:
        note = "当天未结束，不计算奋斗值"
    elif effective_first_dt and effective_last_dt and effective_last_dt > effective_first_dt:
        if is_workday:
            minutes = _workday_overtime_minutes(effective_first_dt, effective_last_dt, workday_end)
            note = "工作日 08:30 前 + 17:30 后"
        else:
            minutes = _restday_overtime_minutes(effective_first_dt, effective_last_dt, lunch_start, lunch_end)
            note = "非工作日打卡时长（扣午休）"

    if not is_today:
        applied_minutes = _parse_applied_overtime_minutes(remark_text, lunch_start, lunch_end)

    if is_today:
        absence_minutes = 0
        leave_minutes = 0
    else:
        absence_minutes = _round_up_half_hour(_parse_int_minutes(_field_value(raw, "AbsenceDuration")))
        if _has_business_trip(remark_text):
            absence_minutes = 0
        leave_minutes = _parse_leave_minutes(remark_text, lunch_start, lunch_end)

    return AttendanceRow(
        date=date_text,
        first_card=first_text,
        last_card=last_text,
        date_type=date_type_text,
        status=status_text,
        overtime_minutes=minutes,
        applied_overtime_minutes=applied_minutes,
        absence_minutes=absence_minutes,
        leave_minutes=leave_minutes,
        is_workday=is_workday,
        note=note,
        remark=remark_text,
    )


def _field_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key) or {}
    return str(value.get("text") or "")


def _field_value(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key) or {}
    return str(value.get("value") or "")


def _field(text: str, value: str | None = None, name: str = "") -> dict[str, Any]:
    return {"name": name, "text": text, "textlist": None, "num": "", "value": text if value is None else value}


def _normalize_date_text(value: str) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%Y/%m/%d") if parsed else ""


def _time_text(value: str) -> str:
    match = re.search(r"\d{1,2}:\d{2}", value or "")
    if not match:
        return ""
    return match.group(0)


def _synthetic_overtime_row(date_text: str, remark: str) -> dict[str, Any]:
    row_date = _parse_date(date_text)
    is_workday = row_date.weekday() < 5 if row_date else True
    return {
        "SwipingCardDate": _field(date_text, name="SwipingCardDate"),
        "ActualForFirstCard": _field("", name="ActualForFirstCard"),
        "ActualForLastCard": _field("", name="ActualForLastCard"),
        "DateType": _field("工作日" if is_workday else "公休日", "1" if is_workday else "2", "DateType"),
        "AttendanceStatus": _field("正常", name="AttendanceStatus"),
        "RetroactiveRemark": _field(remark, name="RetroactiveRemark"),
        "AbsenceDuration": _field("", "0", "AbsenceDuration"),
    }


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_date(value: str) -> datetime | None:
    match = re.search(r"\d{4}[/\-]\d{1,2}[/\-]\d{1,2}", value)
    if not match:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(match.group(0), fmt)
        except ValueError:
            continue
    return None


def _parse_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _workday_overtime_minutes(first_dt: datetime, last_dt: datetime, workday_end: str) -> int:
    standard_start = datetime.combine(first_dt.date(), _parse_time("08:30"))
    standard_end = datetime.combine(last_dt.date(), _parse_time(workday_end))
    morning = max(0, int((standard_start - first_dt).total_seconds() // 60))
    evening = max(0, int((last_dt - standard_end).total_seconds() // 60))
    return morning + evening


def _restday_overtime_minutes(first_dt: datetime, last_dt: datetime, lunch_start: str, lunch_end: str) -> int:
    standard_start = datetime.combine(first_dt.date(), _parse_time("08:30"))
    standard_end = datetime.combine(first_dt.date(), _parse_time("17:30"))
    late_start = datetime.combine(first_dt.date(), _parse_time("18:30"))

    early = _minutes_between(first_dt, min(last_dt, standard_start))
    base = _overlap_datetime_minutes(first_dt, last_dt, standard_start, standard_end)
    base -= _overlap_minutes(max(first_dt, standard_start), min(last_dt, standard_end), lunch_start, lunch_end)
    late = _minutes_between(max(first_dt, late_start), last_dt)
    return max(0, early + base + late)


def _overlap_minutes(start: datetime, end: datetime, range_start: str, range_end: str) -> int:
    if end <= start:
        return 0
    left = datetime.combine(start.date(), _parse_time(range_start))
    right = datetime.combine(start.date(), _parse_time(range_end))
    return _overlap_datetime_minutes(start, end, left, right)


def _overlap_datetime_minutes(start: datetime, end: datetime, left: datetime, right: datetime) -> int:
    overlap_start = max(start, left)
    overlap_end = min(end, right)
    if overlap_end <= overlap_start:
        return 0
    return int((overlap_end - overlap_start).total_seconds() // 60)


def _minutes_between(start: datetime, end: datetime) -> int:
    if end <= start:
        return 0
    return int((end - start).total_seconds() // 60)


def _parse_int_minutes(value: str) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _parse_leave_minutes(remark: str, lunch_start: str, lunch_end: str) -> int:
    if not remark or "假" not in remark or "年假" in remark or "初始化假期" in remark:
        return 0
    if _has_business_trip(remark):
        return 0
    return sum(_time_range_minutes(remark, lunch_start, lunch_end))


def _parse_applied_overtime_minutes(remark: str, lunch_start: str, lunch_end: str) -> int:
    if not remark or "加班" not in remark:
        return 0
    duration_minutes = _overtime_duration_minutes(remark)
    if duration_minutes:
        return sum(duration_minutes)
    return sum(_time_range_minutes(remark, lunch_start, lunch_end))


def _overtime_duration_minutes(remark: str) -> list[int]:
    minutes: list[int] = []
    pattern = r"加班[^；;\n]*[（(]\s*(\d+(?:\.\d+)?)\s*小时(?:\s*(\d+)\s*分钟)?\s*[）)]"
    for hours, extra_minutes in re.findall(pattern, remark):
        total = int(float(hours) * 60)
        if extra_minutes:
            total += int(extra_minutes)
        minutes.append(total)
    return minutes


def _time_range_minutes(remark: str, lunch_start: str, lunch_end: str) -> list[int]:
    minutes: list[int] = []
    for start, end in re.findall(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", remark):
        start_time = datetime.strptime(start, "%H:%M")
        end_time = datetime.strptime(end, "%H:%M")
        if end_time < start_time:
            end_time += timedelta(days=1)
        if end_time > start_time:
            total = int((end_time - start_time).total_seconds() // 60)
            total -= _overlap_minutes(start_time, end_time, lunch_start, lunch_end)
            minutes.append(max(0, total))
    return minutes


def _round_up_half_hour(minutes: int) -> int:
    if minutes <= 0:
        return 0
    return int(ceil(minutes / 30) * 30)


def _has_business_trip(remark: str) -> bool:
    return any(keyword in remark for keyword in ("公出", "出差", "外出"))


def _apply_remark_work_times(
    first_dt: datetime | None,
    last_dt: datetime | None,
    remark: str,
    row_date: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    if not remark:
        return first_dt, last_dt
    candidates: list[datetime] = []
    for value in re.findall(r"补签\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2})", remark):
        for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                candidates.append(datetime.strptime(value, fmt))
                break
            except ValueError:
                continue
    if _has_business_trip(remark) and row_date:
        for start, end in re.findall(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", remark):
            start_dt = datetime.combine(row_date.date(), _parse_time(start))
            end_dt = datetime.combine(row_date.date(), _parse_time(end))
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
            candidates.extend([start_dt, end_dt])

    effective_first = first_dt
    effective_last = last_dt
    for candidate in candidates:
        if effective_first is None or candidate < effective_first:
            effective_first = candidate
        if effective_last is None or candidate > effective_last:
            effective_last = candidate
    return effective_first, effective_last


def format_minutes(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return f"{sign}{hours} 小时"
    return f"{sign}{hours} 小时 {rest} 分钟"

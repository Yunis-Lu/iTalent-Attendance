from __future__ import annotations

import base64
from copy import deepcopy
import time
from typing import Any
import uuid

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding


LOGIN_URL = "https://login.italent.cn/Account/Login"
ATTENDANCE_URL = "https://cloud.italent.cn/api/v2/UI/TableList"
DEFAULT_TENANT_ID = "102407"

ATTENDANCE_QUERY_PARAMS = {
    "viewName": "Attendance.SingleObjectListView.EmpAttendanceDataList",
    "metaObjName": "Attendance.AttendanceStatistics",
    "app": "Attendance",
    "PaaS-SourceApp": "Attendance",
    "PaaS-CurrentView": "Attendance.AttendanceDataRecordNavView",
    "frontendVersion": "2025121900",
    "shadow_context": '{appModel:"italent",uppid:"1"}',
    "_qsrcapp": "attendance",
}

OVERTIME_QUERY_PARAMS = {
    "viewName": "Attendance.SingleObjectListView.EmployeeOverTime",
    "metaObjName": "Attendance.OverTime",
    "app": "Attendance",
    "PaaS-SourceApp": "Attendance",
    "PaaS-CurrentView": "Attendance.EmployeeOverTimeView",
    "frontendVersion": "2025121900",
    "shadow_context": '{appModel:"italent",uppid:"1"}',
    "_qsrcapp": "attendance",
}

PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCCAGUAYFFTqlMwndAkJbO6GoOi
PTPMreeYJ6JfWbx5rliI4PevlmMZNISOtmZm6Sv44wlA4l+1y1wqAE31jPhH2bZ2
qqbJdiPB7VXpR5nQeSZGcNCSCK7N62A5b8ssEjbWd5jMBiqD/erLkc87/jQ0iqd3
42Oixc9y4LFn//ABWwIDAQAB
-----END PUBLIC KEY-----
"""


class ItalentClient:
    def __init__(self) -> None:
        self.user_id = ""
        self.session = requests.Session()
        self._reset_session()

    def _reset_session(self) -> None:
        self.session.close()
        self.session = requests.Session()
        self.session.cookies.set("iTalent-tenantId", DEFAULT_TENANT_ID, domain=".italent.cn")
        self.session.cookies.set("isItalentLogin", "", domain=".italent.cn")
        self.session.cookies.set("italentLoginSync", str(int(time.time() * 1000)), domain=".italent.cn")
        self.session.cookies.set(f"user_polling_timespace_{DEFAULT_TENANT_ID}", "0", domain=".italent.cn")

    def login(self, username: str, password: str) -> dict[str, Any]:
        payload = {
            "UseLoginGeetest": False,
            "Remember": "",
            "Domin": "",
            "ReturnUrl": "",
            "UseLoginMutex": False,
            "MutexToken": "",
            "LoginType": 0,
            "UserName": username.strip(),
            "Password": encrypt_password(password),
            "lt": "zh_CN",
        }

        data: dict[str, Any] = {}
        for attempt in range(2):
            trace_id = str(uuid.uuid4())
            response = self.session.post(LOGIN_URL, json=payload, headers=_login_headers(trace_id), timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get("Code") == 1:
                break
            message = str(data.get("Message") or data.get("MessageCode") or "登录失败")
            if attempt == 0 and _requires_geetest(message):
                self._reset_session()
                continue
            raise RuntimeError(_login_error_message(message))

        login_data = data.get("Data") or {}
        self.user_id = str(login_data.get("UserId") or login_data.get("UserID") or "")
        if not self.user_id:
            raise RuntimeError("登录成功，但响应里没有找到用户 ID，无法查询考勤。")
        return data

    def query_attendance(self, start_date: str, end_date: str, username: str = "") -> dict[str, Any]:
        if not self.user_id:
            raise RuntimeError("请先登录，再查询考勤。")

        payload = _attendance_payload(
            staff_id=self.user_id,
            username=username,
            start_date=start_date,
            end_date=end_date,
        )
        response = self.session.post(
            ATTENDANCE_URL,
            params=ATTENDANCE_QUERY_PARAMS,
            json=payload,
            headers=_attendance_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def query_overtime(self, username: str = "") -> dict[str, Any]:
        if not self.user_id:
            raise RuntimeError("请先登录，再查询加班。")

        payload = _overtime_payload(staff_id=self.user_id, username=username)
        response = self.session.post(
            ATTENDANCE_URL,
            params=OVERTIME_QUERY_PARAMS,
            json=payload,
            headers=_attendance_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


def encrypt_password(password: str) -> str:
    public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM)
    encrypted = public_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode("ascii")


def _login_headers(trace_id: str) -> dict[str, str]:
    return {
        "Accept": "application/json, application/xml, text/play, text/html, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/json;charset=utf-8",
        "EagleEye-TraceID": trace_id,
        "Origin": "https://www.italent.cn",
        "Referer": "https://www.italent.cn/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": _user_agent(),
        "X-Sourced-By": "ajax",
        "fal": "",
        "fan": "",
        "fpl": "",
        "fpn": "",
        "ftc": trace_id,
        "fver": "",
        "sec-ch-ua": '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


def _attendance_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, application/xml, text/play, text/html, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Origin": "https://www.italent.cn",
        "Referer": "https://www.italent.cn/",
        "User-Agent": _user_agent(),
        "X-Sourced-By": "ajax",
    }


def _user_agent() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0"
    )


def _requires_geetest(message: str) -> bool:
    return "极验" in message or "Geetest" in message


def _login_error_message(message: str) -> str:
    if _requires_geetest(message):
        return "iTalent 临时要求登录验证。请等待几秒后重新登录；如果仍然失败，请先在网页登录一次后再回到软件。"
    return message


def _attendance_payload(staff_id: str, username: str, start_date: str, end_date: str) -> dict[str, Any]:
    payload = deepcopy(_ATTENDANCE_TEMPLATE)
    staff_text = f"({username})" if username else ""
    date_range = f"{start_date}-{end_date}"
    for item in payload["search_data"]["items"]:
        name = item["name"]
        if name == "Attendance.AttendanceStatistics.StaffId":
            item["text"] = staff_text
            item["value"] = staff_id
        elif name == "Attendance.AttendanceStatistics.SwipingCardDate":
            item["text"] = date_range
            item["value"] = date_range
    return payload


def _overtime_payload(staff_id: str, username: str) -> dict[str, Any]:
    payload = deepcopy(_OVERTIME_TEMPLATE)
    staff_text = f"({username})" if username else ""
    for item in payload["search_data"]["items"]:
        if item["name"] == "Attendance.OverTime.StaffId":
            item["text"] = staff_text
            item["value"] = staff_id
    return payload


_ATTENDANCE_TEMPLATE: dict[str, Any] = {
    "table_data": {
        "advance": {"cmp_render": {"viewPath": "MyAttendanceStatisticsTable", "status": "enable"}},
        "hasCheckColumn": True,
        "ext_data": {"ListViewLabel": ""},
        "isEnableGlobleCheck": False,
        "hasRowHandler": True,
        "paging": {"total": 0, "capacity": 100, "page": 0, "capacityList": [15, 30, 60, 100]},
        "isAvatars": True,
        "viewName": "Attendance.SingleObjectListView.EmpAttendanceDataList",
        "operateColumWidth": 140,
        "extendsParam": "",
        "isSyncRowHandler": True,
        "isFrozenOperationColumnHandler": False,
        "isCustomListViewExisted": False,
        "getTreeNodeUrl": None,
        "sort_fields": [{"sort_column": "SwipingCardDate", "sort_dir": "desc"}],
        "description": "",
        "metaObjName": "Attendance.AttendanceStatistics",
        "isCustomListView": True,
        "navViewIsCustom": False,
        "navViewName": "Attendance.AttendanceDataRecordNavView",
        "navViewVersion": "0",
    },
    "search_data": {
        "metaObjName": "Attendance.AttendanceStatistics",
        "searchView": "Attendance.EmpAttendanceDataSearch",
        "items": [
            {
                "name": "Attendance.AttendanceStatistics.StaffId",
                "text": "",
                "value": "",
                "num": "1",
                "metaObjName": "",
                "metaFieldRelationIDPath": "",
                "queryAreaSubNodes": False,
            },
            {
                "name": "Attendance.AttendanceStatistics.StdIsDeleted",
                "text": "",
                "value": "0",
                "num": "5",
                "metaObjName": "",
                "metaFieldRelationIDPath": "",
                "queryAreaSubNodes": False,
            },
            {
                "name": "Attendance.AttendanceStatistics.Status",
                "text": "",
                "value": "1",
                "num": "6",
                "metaObjName": "",
                "metaFieldRelationIDPath": "",
                "queryAreaSubNodes": False,
            },
            {
                "name": "Attendance.AttendanceStatistics.SwipingCardDate",
                "text": "",
                "value": "",
                "num": "",
                "metaObjName": "",
                "metaFieldRelationIDPath": "",
                "queryAreaSubNodes": False,
            },
        ],
        "searchFormFilterJson": None,
    },
}


_OVERTIME_TEMPLATE: dict[str, Any] = {
    "table_data": {
        "advance": {"cmp_render": {"viewPath": "OverTimeRecordTableWithLoadingControl", "status": "enable"}},
        "hasCheckColumn": False,
        "ext_data": {"ListViewLabel": ""},
        "isEnableGlobleCheck": False,
        "hasRowHandler": True,
        "paging": {"total": 0, "capacity": 100, "page": 0, "capacityList": [15, 30, 60, 100]},
        "isAvatars": True,
        "viewName": "Attendance.SingleObjectListView.EmployeeOverTime",
        "operateColumWidth": 140,
        "extendsParam": "",
        "isSyncRowHandler": True,
        "isFrozenOperationColumnHandler": False,
        "isCustomListViewExisted": False,
        "getTreeNodeUrl": None,
        "sort_fields": [
            {"sort_column": "StartTime", "sort_dir": "desc"},
            {"sort_column": "CreatedTime", "sort_dir": "desc"},
        ],
        "description": "",
        "metaObjName": "Attendance.OverTime",
        "isCustomListView": True,
        "navViewIsCustom": False,
        "navViewName": "Attendance.EmployeeOverTimeView",
        "navViewVersion": "0",
    },
    "search_data": {
        "metaObjName": "Attendance.OverTime",
        "searchView": "Attendance.EmployeeSearchViewForm",
        "items": [
            {
                "name": "Attendance.OverTime.StaffId",
                "text": "",
                "value": "",
                "num": "1",
                "metaObjName": "",
                "metaFieldRelationIDPath": "",
                "queryAreaSubNodes": False,
            },
            {
                "name": "Attendance.OverTime.StdIsDeleted",
                "text": "",
                "value": "0",
                "num": "7",
                "metaObjName": "",
                "metaFieldRelationIDPath": "",
                "queryAreaSubNodes": False,
            },
            {
                "name": "Attendance.OverTime.Invalid",
                "text": "",
                "value": "1",
                "num": "10",
                "metaObjName": "",
                "metaFieldRelationIDPath": "",
                "queryAreaSubNodes": False,
            },
        ],
        "searchFormFilterJson": None,
    },
}

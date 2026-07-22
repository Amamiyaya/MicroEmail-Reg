"""
Microsoft Outlook 纯协议注册（精简版）

只保留注册流程，已去掉：
  - OAuth2 授权
  - 多线程批量
  - mail_manager 导入
  - fix-auth 补授权

注册流程:
  1. GET  /signup                    -> ServerData (apiCanary, uaid, DFP/PX)
  2. POST CheckAvailableSigninNames  -> 检查用户名
  3. POST risk/initialize            -> continuationToken
  4. CaptchaRun PxCaptcha2           -> silentToken
  5. POST risk/verify (1st)          -> riskChallengeRequired
  6. CaptchaRun pressToken           -> _px3/_pxde/_pxvid
  7. POST risk/verify (2nd)          -> final continuationToken
  8. POST CreateAccount              -> 创建账号

依赖:
  pip install curl_cffi requests

用法:
  python outlook_register_only.py --cr-token YOUR_TOKEN --proxy http://user:pass@host:port
  python outlook_register_only.py --cr-token YOUR_TOKEN --proxy-file proxies.txt --country US
"""

from __future__ import annotations

import argparse
import json
import random
import re
import string
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests as req
from curl_cffi import requests as cffi_requests


# ============================================================
#  常量
# ============================================================

CAPTCHARUN_API = "https://api.captcha-run.com/v2/tasks"
SIGNUP_BASE = "https://signup.live.com"
SIGNUP_PATH = (
    "/signup?sru=https%3a%2f%2flogin.live.com%2foauth20_authorize.srf"
    "%3flc%3d2052%26client_id%3d9199bf20-a13f-4107-85dc-02114787ef48"
    "%26cobrandid%3dab0455a0-8d03-46b9-b18b-df2f57b9e44c"
    "%26mkt%3dZH-CN%26opid%3d{opid}%26opidt%3d{opidt}"
    "%26uaid%3d{uaid}%26contextid%3d{contextid}%26opignore%3d1"
    "&mkt=ZH-CN&uiflavor=web&fl=dob%2cflname%2cwld"
    "&cobrandid=ab0455a0-8d03-46b9-b18b-df2f57b9e44c"
    "&client_id=9199bf20-a13f-4107-85dc-02114787ef48"
    "&uaid={uaid}&suc=9199bf20-a13f-4107-85dc-02114787ef48"
    "&fluent=2&lic=1"
)
RISK_BASE = "https://login.microsoftonline.com"
RISK_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
SITE_ID = "00000000487A244A"
DOMAINS = ("outlook.com", "hotmail.com")
_EDGE_MAJOR = 136

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Daniel", "Nancy", "Matthew", "Lisa",
    "Anthony", "Betty", "Mark", "Helen", "Steven", "Sandra", "Andrew", "Donna",
    "Joshua", "Carol", "Kenneth", "Ruth", "Kevin", "Sharon", "Brian", "Michelle",
    "George", "Laura", "Edward", "Emily", "Jason", "Carolyn", "Ryan", "Anna",
    "Eric", "Emma", "Jonathan", "Samantha", "Justin", "Rachel", "Brandon", "Catherine",
    "Samuel", "Janet", "Frank", "Maria", "Patrick", "Julie", "Jack", "Victoria",
    "Aaron", "Christina", "Henry", "Joan", "Adam", "Megan", "Nathan", "Hannah",
    "Kyle", "Martha", "Sean", "Jean", "Ethan", "Alice", "Austin", "Judy",
    "Noah", "Grace", "Jesse", "Denise", "Bryan", "Marilyn",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
    "Cook", "Rogers", "Morgan", "Cooper", "Bailey", "Reed", "Kelly", "Howard",
    "Kim", "Cox", "Ward", "Watson", "Brooks", "Wood", "James", "Bennett",
    "Gray", "Ruiz", "Hughes", "Price", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Powell", "Jenkins", "Perry", "Russell", "Sullivan", "Bell",
]


# ============================================================
#  日志
# ============================================================

C_DIM = "\033[90m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_CYAN = "\033[96m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"
_LEVEL_COLOR = {"INFO": C_DIM, "OK": C_GREEN, "WARN": C_YELLOW, "ERROR": C_RED}


def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    color = _LEVEL_COLOR.get(level, C_DIM)
    print(f"{C_DIM}{ts}{C_RESET} {color}[{level}]{C_RESET} {msg}")


def log_step(step: str, msg: str, status: str = "") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    icon = {
        "OK": f"{C_GREEN}✓{C_RESET}",
        "WARN": f"{C_YELLOW}!{C_RESET}",
        "ERROR": f"{C_RED}✗{C_RESET}",
        "": f"{C_DIM}→{C_RESET}",
    }.get(status, "")
    print(f"{C_DIM}{ts}{C_RESET} {icon} {C_CYAN}{step}{C_RESET} {msg}")


def log_box(title: str, lines: list[str], color: str = C_CYAN) -> None:
    width = max(len(title), max((len(line) for line in lines), default=0)) + 4
    border = f"{color}{'─' * (width + 2)}{C_RESET}"
    print(border)
    print(f"{color}│{C_RESET} {C_BOLD}{title}{C_RESET}{' ' * (width - len(title) - 1)}{color}│{C_RESET}")
    for line in lines:
        print(f"{color}│{C_RESET} {line}{' ' * (width - len(line) - 1)}{color}│{C_RESET}")
    print(border)


# ============================================================
#  工具
# ============================================================

def parse_proxy_url(proxy_url: str) -> dict:
    """解析代理 URL: http://user:pass@host:port -> 组件字典"""
    parsed = urlparse(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
    return {
        "host": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "login": parsed.username or "",
        "password": parsed.password or "",
    }


def normalize_proxy(line: str) -> str:
    """把多种代理格式统一成 http://login:pass@host:port"""
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    if line.startswith("http://") or line.startswith("https://"):
        return line
    if "@" in line:
        auth_part, host_part = line.rsplit("@", 1)
        proxy_login, proxy_pass = auth_part.split(":", 1)
        host, port = host_part.split(":", 1)
        return f"http://{proxy_login}:{proxy_pass}@{host}:{port}"
    parts = line.split(":")
    if len(parts) == 4:
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    return ""


def detect_proxy_geo(proxy_url: str) -> tuple[str, str]:
    """通过代理检测 IP 地理位置，失败时回退 US。"""
    try:
        proxy_str = proxy_url if proxy_url.startswith("http") else f"http://{proxy_url}"
        r = cffi_requests.get("http://ip-api.com/json", proxy=proxy_str, timeout=15)
        data = r.json()
        country = data.get("countryCode", "US")
        tz = data.get("timezone", "America/New_York")
        log_step("Proxy", f"IP {data.get('query', '')} → {country}, {tz}, {data.get('city', '')}", "OK")
        return country, tz
    except Exception as e:
        log_step("Proxy", f"IP 检测失败, 使用默认 US: {e}", "WARN")
        return "US", "America/New_York"


def gen_edge_ua() -> tuple[str, str]:
    """生成 Edge UA / sec-ch-ua。"""
    build = random.randint(1000, 9999)
    patch = random.randint(1, 99)
    ver = f"{_EDGE_MAJOR}.0.{build}.{patch}"
    ua = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{ver} Safari/537.36 Edg/{ver}"
    )
    sec_ch = (
        f'"Chromium";v="{_EDGE_MAJOR}", "Microsoft Edge";v="{_EDGE_MAJOR}", '
        f'"Not/A)Brand";v="99"'
    )
    return ua, sec_ch


def extract_server_data(html: str) -> dict:
    """从注册页 HTML 提取 ServerData JSON。"""
    for pattern in [
        r"var\s+ServerData\s*=\s*(\{.*?\});\s*</script>",
        r"var\s+ServerData\s*=\s*(\{.*?\});",
    ]:
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            continue
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
    raise ValueError("无法从页面中提取 ServerData")


def build_query_string(server_data: dict) -> str:
    ct = int(time.time())
    return (
        f"lcid=2052&wa=wsignin1.0&rpsnv=13&ct={ct}"
        "&rver=7.0.6730.0&wp=MBI_SSL"
        "&wreply=https%3a%2f%2foutlook.live.com%2fmail%2f"
        "&id=292841&CBCXT=out&lw=1&fl=dob%2Cflname%2Cwld"
        "&cobrandid=ab0455a0-8d03-46b9-b18b-df2f57b9e44c"
        f"&uaid={server_data.get('sUnauthSessionID', '')}"
        "&lic=1"
    )


def build_headers(server_data: dict, use_api_canary: bool = True) -> dict:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "hpgid": str(server_data.get("hpgid", 200225)),
        "hpgact": str(server_data.get("hpgact", 0)),
    }
    canary = server_data.get("apiCanary", "")
    if use_api_canary and canary:
        headers["canary"] = canary
    corr_id = server_data.get("sUnauthSessionID", "")
    if corr_id:
        headers["correlationId"] = corr_id
        headers["client-request-id"] = corr_id
    return headers


def format_birthdate(day: int, month: int, year: int) -> str:
    return f"{str(day).zfill(2)}:{str(month).zfill(2)}:{year}"


def random_username() -> str:
    prefix = "".join(random.choices(string.ascii_lowercase, k=random.randint(6, 8)))
    suffix = "".join(random.choices(string.digits, k=random.randint(3, 5)))
    return prefix + suffix


def random_password() -> str:
    upper = random.choice(string.ascii_uppercase)
    lower = "".join(random.choices(string.ascii_lowercase, k=6))
    digit = "".join(random.choices(string.digits, k=3))
    symbol = random.choice("!@#$%^&*")
    chars = list(upper + lower + digit + symbol)
    random.shuffle(chars)
    return "".join(chars)


def random_birthdate() -> tuple[int, int, int]:
    return random.randint(1975, 2005), random.randint(1, 12), random.randint(1, 28)


# ============================================================
#  CaptchaRun
# ============================================================

class CaptchaRunSolver:
    """CaptchaRun PxCaptcha2 求解器。"""

    def __init__(
        self,
        token: str,
        proxy_host: str = "",
        proxy_port: str = "",
        proxy_login: str = "",
        proxy_password: str = "",
        user_agent: str = "",
        country: str = "US",
        timezone_str: str = "America/New_York",
    ):
        self.token = token
        self.proxy_host = proxy_host
        self.proxy_port = str(proxy_port)
        self.proxy_login = proxy_login
        self.proxy_password = proxy_password
        self.user_agent = user_agent
        self.country = country
        self.timezone = timezone_str
        self.task_id: Optional[str] = None

    @classmethod
    def from_proxy_url(
        cls,
        token: str,
        proxy_url: str,
        country: str = "",
        timezone_str: str = "",
        user_agent: str = "",
    ) -> "CaptchaRunSolver":
        p = parse_proxy_url(proxy_url)
        if not country or not timezone_str:
            det_country, det_tz = detect_proxy_geo(proxy_url)
            country = country or det_country
            timezone_str = timezone_str or det_tz
        return cls(
            token=token,
            proxy_host=p["host"],
            proxy_port=p["port"],
            proxy_login=p["login"],
            proxy_password=p["password"],
            user_agent=user_agent,
            country=country,
            timezone_str=timezone_str,
        )

    def create_task(self, uaid: str, px_uuid: str = "", px_vid: str = "") -> str:
        body = {
            "captchaType": "PxCaptcha2",
            "uaid": uaid,
            "country": self.country,
            "timezone": self.timezone,
            "host": self.proxy_host,
            "port": self.proxy_port,
            "login": self.proxy_login,
            "password": self.proxy_password,
        }
        if self.user_agent:
            body["userAgent"] = self.user_agent
        if px_uuid:
            body["uuid"] = px_uuid
        if px_vid:
            body["vid"] = px_vid

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        log_step("CaptchaRun", f"创建任务 uaid={uaid[:16]}...")
        resp = req.post(CAPTCHARUN_API, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self.task_id = data.get("taskId")
        if not self.task_id:
            raise ValueError(f"CaptchaRun 返回无 taskId: {data}")
        log_step("CaptchaRun", f"taskId={self.task_id}", "OK")
        return self.task_id


# ============================================================
#  注册器
# ============================================================

class MicrosoftSignupProtocol:
    """Microsoft Outlook 纯协议注册器（仅注册）。"""

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: int = 30,
        user_agent: Optional[str] = None,
        sec_ch_ua: Optional[str] = None,
    ):
        proxies = {"http": proxy, "https": proxy} if proxy else None
        self.client = cffi_requests.Session(
            impersonate="chrome136",
            timeout=timeout,
            proxies=proxies,
        )
        if user_agent and sec_ch_ua:
            self.user_agent = user_agent
            self.sec_ch_ua = sec_ch_ua
        else:
            self.user_agent, self.sec_ch_ua = gen_edge_ua()
        self.server_data: Optional[dict] = None
        self.query_string: Optional[str] = None
        self.accept_language = "zh-CN,zh;q=0.9"

    def close(self) -> None:
        self.client.close()

    def step1_fetch_signup_page(self) -> dict:
        """GET signup 页，提取 ServerData，并加载 DFP / PX iframe。"""
        ct = int(time.time())
        pre_uaid = uuid.uuid4().hex
        opid = uuid.uuid4().hex.upper()[:16] + uuid.uuid4().hex.upper()[:8]
        opidt = str(ct)
        contextid = uuid.uuid4().hex.upper()[:16] + uuid.uuid4().hex.upper()[:8]
        url = SIGNUP_BASE + SIGNUP_PATH.format(
            uaid=pre_uaid, opid=opid, opidt=opidt, contextid=contextid
        )

        log_step("Step 1", "GET signup.live.com")
        resp = self.client.get(url)
        resp.raise_for_status()

        sd = extract_server_data(resp.text)
        self.server_data = sd
        self.query_string = build_query_string(sd)
        log_step("Step 1", f"uaid={sd.get('sUnauthSessionID', '')}", "OK")

        captcha_info = sd.get("oCaptchaInfo", {})
        dfp_url = captcha_info.get("urlDfp", "")
        if dfp_url:
            try:
                self.client.get(
                    dfp_url,
                    headers={
                        "Referer": url,
                        "Sec-Fetch-Dest": "iframe",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "cross-site",
                        "Upgrade-Insecure-Requests": "1",
                    },
                )
                log_step("Step 1", "DFP loaded", "OK")
            except Exception as e:
                log_step("Step 1", f"DFP load failed: {e}", "WARN")

        human_iframe_url = sd.get("urlHumanIframe", "")
        if human_iframe_url:
            try:
                self.client.get(
                    human_iframe_url,
                    headers={
                        "Referer": url,
                        "Sec-Fetch-Dest": "iframe",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "cross-site",
                        "Upgrade-Insecure-Requests": "1",
                    },
                )
                log_step("Step 1", "PX iframe loaded", "OK")
            except Exception as e:
                log_step("Step 1", f"PX iframe load failed: {e}", "WARN")

        return sd

    def step2_check_username(self, email: str) -> dict:
        """检查用户名是否可用。"""
        assert self.server_data is not None
        url = self.server_data.get(
            "urlCheckAvailableSigninNames",
            SIGNUP_BASE + "/API/CheckAvailableSigninNames",
        )
        url_with_qs = f"{url}?{self.query_string}"
        log_step("Step 2", f"CheckAvailableSigninNames → {email}")

        body = {
            "includeSuggestions": True,
            "signInName": email,
            "uiflvr": self.server_data.get("iUiFlavor", 1001),
            "scid": self.server_data.get("iScenarioId", 100118),
            "uaid": self.server_data.get("sUnauthSessionID", ""),
            "hpgid": self.server_data.get("hpgid", 200225),
        }
        headers = build_headers(self.server_data)
        resp = self.client.post(url_with_qs, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if "apiCanary" in data:
            self.server_data["apiCanary"] = data["apiCanary"]

        if data.get("isAvailable", False):
            log_step("Step 2", f"可用 ({data.get('type', '')})", "OK")
        else:
            log_step("Step 2", "用户名已被占用", "ERROR")
        return data

    def step3_risk_initialize(self) -> dict:
        """风险初始化，获取 continuationToken。"""
        assert self.server_data is not None
        path = self.server_data.get(
            "urlRiskInitialize",
            f"/{RISK_TENANT}/api/v1.0/risk/initialize",
        )
        url = RISK_BASE + path
        log_step("Step 3", "POST risk/initialize")

        headers = build_headers(self.server_data)
        headers.update({
            "Referer": f"{SIGNUP_BASE}/",
            "Origin": SIGNUP_BASE,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Sec-GPC": "1",
            "Priority": "u=0",
            "Accept-Language": self.accept_language,
        })

        try:
            resp = self.client.post(url, json={"continuationToken": ""}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("continuationToken", "")
            log_step("Step 3", f"continuationToken={token[:32]}...", "OK")
            return data
        except Exception as e:
            log_step("Step 3", f"risk/initialize 失败 (非致命): {e}", "WARN")
            return {}

    def _risk_verify_headers(self) -> dict:
        headers = build_headers(self.server_data or {})
        headers.update({
            "Referer": f"{SIGNUP_BASE}/",
            "Origin": SIGNUP_BASE,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "X-Edge-Shopping-Flag": "0",
            "Accept-Language": self.accept_language,
        })
        return headers

    def _clear_microsoftonline_cookies(self) -> None:
        to_remove = [
            c for c in self.client.cookies.jar
            if "login.microsoftonline.com" in (c.domain or "")
        ]
        for cookie in to_remove:
            try:
                self.client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
            except Exception:
                pass
        if to_remove:
            log_step("Cookies", f"清除 {len(to_remove)} 个 microsoftonline.com cookies")

    def step4_risk_verify_first(
        self,
        continuation_token: str,
        email: str,
        country: str,
        birth_date: str,
        first_name: str,
        last_name: str,
    ) -> dict:
        """第一次 risk/verify：不带 PX token，通常触发 challenge。"""
        assert self.server_data is not None
        path = self.server_data.get(
            "urlRiskVerify",
            f"/{RISK_TENANT}/api/v1.0/risk/verify",
        )
        url = RISK_BASE + path
        log_step("Step 4", "risk/verify (1st, 无 PX tokens)")

        body = {
            "continuationToken": continuation_token,
            "msaRiskVerifySignature": {
                "memberName": email,
                "siteId": SITE_ID,
                "uiFlavor": "Web",
                "appId": SITE_ID,
                "birthdate": birth_date,
                "firstName": first_name,
                "lastName": last_name,
                "countryCode": country,
                "verificationCode": "",
                "deviceDetails": {"isRdm": False},
                "action": "SignUp",
            },
        }

        self._clear_microsoftonline_cookies()
        resp = self.client.post(url, json=body, headers=self._risk_verify_headers())
        if resp.status_code >= 400:
            log_step("Step 4", f"HTTP {resp.status_code}: {resp.text[:300]}", "ERROR")
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", "")
        log_step("Step 4", f"state={state}", "OK" if state else "WARN")
        return data

    def step5_risk_verify_second(self, continuation_token: str, px_cookies: dict) -> dict:
        """第二次 risk/verify：提交 PX press token。"""
        assert self.server_data is not None
        path = self.server_data.get(
            "urlRiskVerify",
            f"/{RISK_TENANT}/api/v1.0/risk/verify",
        )
        url = RISK_BASE + path
        log_step("Step 5", "risk/verify (2nd, challengeSolution)")

        body = {
            "continuationToken": continuation_token,
            "challengeSolution": {
                "challengeType": "HumanCaptcha",
                "px3": px_cookies.get("_px3", ""),
                "pxde": px_cookies.get("_pxde", ""),
                "pxvid": px_cookies.get("_pxvid", ""),
            },
        }

        self._clear_microsoftonline_cookies()
        resp = self.client.post(url, json=body, headers=self._risk_verify_headers())
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", "")
        log_step("Step 5", f"state={state}", "OK" if state == "continue" else "WARN")
        return data

    def _wait_silent_token(self, solver: CaptchaRunSolver) -> dict:
        url = f"{CAPTCHARUN_API}/{solver.task_id}?captchaType=silent"
        headers = {"Authorization": f"Bearer {solver.token}"}
        max_wait, interval, elapsed = 60, 3, 0

        log_step("CaptchaRun", f"等待 silentToken (最多 {max_wait}s)...")
        while elapsed < max_wait:
            resp = req.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            response = data.get("response", {})

            if response.get("silentToken"):
                log_step("CaptchaRun", f"silentToken 已获取 ({elapsed}s)", "OK")
                return response["silentToken"]
            if data.get("status") == "Fail":
                raise ValueError(f"CaptchaRun silent 失败: {data.get('reason', '')}")

            time.sleep(interval)
            elapsed += interval
        raise TimeoutError(f"CaptchaRun silentToken 超时 ({max_wait}s)")

    def _wait_press_token(self, solver: CaptchaRunSolver) -> dict:
        url = f"{CAPTCHARUN_API}/{solver.task_id}?captchaType=press"
        headers = {"Authorization": f"Bearer {solver.token}"}
        max_wait, interval, elapsed = 120, 3, 0

        log_step("CaptchaRun", f"等待 pressToken (最多 {max_wait}s)...")
        while elapsed < max_wait:
            try:
                resp = req.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
            except req.exceptions.HTTPError:
                if resp.status_code == 404:
                    time.sleep(interval)
                    elapsed += interval
                    continue
                raise

            data = resp.json()
            response = data.get("response", {})
            if response.get("pressToken"):
                log_step("CaptchaRun", f"pressToken 已获取 ({elapsed}s)", "OK")
                return response["pressToken"]
            if data.get("status") == "Fail":
                raise ValueError("打码失败")

            time.sleep(interval)
            elapsed += interval
        raise TimeoutError(f"CaptchaRun pressToken 超时 ({max_wait}s)")

    def step6_create_account(
        self,
        email: str,
        password: str,
        country: str,
        birth_day: int,
        birth_month: int,
        birth_year: int,
        first_name: str,
        last_name: str,
        continuation_token: str = "",
    ) -> dict:
        """创建账号。"""
        assert self.server_data is not None
        url = self.server_data.get(
            "urlCreateAccount",
            SIGNUP_BASE + "/API/CreateAccount",
        )
        url_with_qs = f"{url}?{self.query_string}"
        log_step("Step 6", f"CreateAccount → {email}")

        body = {
            "BirthDate": format_birthdate(birth_day, birth_month, birth_year),
            "CheckAvailStateMap": [f"{email}:false"],
            "Country": country,
            "EvictionWarningShown": [],
            "FirstName": first_name,
            "IsRDM": False,
            "IsOptOutEmailDefault": True,
            "IsOptOutEmailShown": 1,
            "IsOptOutEmail": True,
            "IsUserConsentedToChinaPIPL": country == "CN",
            "LastName": last_name,
            "LW": 1,
            "MemberName": email,
            "RequestTimeStamp": datetime.now(timezone.utc).isoformat(),
            "ReturnUrl": "",
            "SignupReturnUrl": self.server_data.get("sSignupReturnUrl", ""),
            "SuggestedAccountType": self.server_data.get("sSuggestedAccountType", "EASI"),
            "SiteId": SITE_ID,
            "VerificationCodeSlt": "",
            "PrivateAccessToken": "",
            "WReply": self.server_data.get("sWReply", ""),
            "MemberNameChangeCount": 1,
            "MemberNameAvailableCount": 1,
            "MemberNameUnavailableCount": 0,
            "Password": password,
            "ContinuationToken": continuation_token,
            "uiflvr": self.server_data.get("iUiFlavor", 1001),
            "scid": self.server_data.get("iScenarioId", 100118),
            "uaid": self.server_data.get("sUnauthSessionID", ""),
            "hpgid": self.server_data.get("hpgid", 200225),
        }

        headers = build_headers(self.server_data)
        resp = self.client.post(url_with_qs, json=body, headers=headers)
        if resp.status_code >= 400:
            log_step("Step 6", f"HTTP {resp.status_code}: {resp.text[:300]}", "ERROR")
        data = resp.json()

        if "error" in data:
            err = data["error"]
            log_step("Step 6", f"失败: code={err.get('code')}", "ERROR")
        elif "redirectUrl" in data:
            log_step("Step 6", "注册成功!", "OK")
        else:
            log_step("Step 6", f"未知响应: {json.dumps(data)[:150]}", "WARN")
        return data

    def register(
        self,
        username: str,
        domain: str,
        password: str,
        country: str = "US",
        birth_year: int = 1995,
        birth_month: int = 6,
        birth_day: int = 15,
        first_name: str = "John",
        last_name: str = "Smith",
        cr_solver: Optional[CaptchaRunSolver] = None,
    ) -> dict:
        """执行完整注册流程。"""
        email = f"{username}@{domain}"
        print(f"\n{C_BOLD}{'━' * 46}{C_RESET}")
        print(f"{C_BOLD}  Outlook 注册{C_RESET} {C_DIM}|{C_RESET} {email}")
        print(f"{C_BOLD}{'━' * 46}{C_RESET}")

        try:
            self.step1_fetch_signup_page()

            check = self.step2_check_username(email)
            if not check.get("isAvailable", False):
                return {"success": False, "error": "username_unavailable", "email": email}

            risk_init = self.step3_risk_initialize()
            continuation_token = risk_init.get("continuationToken", "")
            birth_date = format_birthdate(birth_day, birth_month, birth_year)

            if not cr_solver:
                log_step("Captcha", "需要 --cr-token 参数", "ERROR")
                return {"success": False, "error": "no_captcha_solver", "email": email}

            uaid = (self.server_data or {}).get("sUnauthSessionID", "")
            if not uaid:
                raise ValueError("无 uaid, 无法创建验证任务")

            cr_solver.create_task(uaid)
            self._wait_silent_token(cr_solver)

            verify1 = self.step4_risk_verify_first(
                continuation_token=continuation_token,
                email=email,
                country=country,
                birth_date=birth_date,
                first_name=first_name,
                last_name=last_name,
            )
            state = verify1.get("state", "")
            new_token = verify1.get("continuationToken", "")

            if state == "riskChallengeRequired":
                press = self._wait_press_token(cr_solver)
                px_cookies = {
                    k: v for k, v in press.items()
                    if k in ("_px3", "_pxde", "_pxvid") and v
                }
                verify2 = self.step5_risk_verify_second(
                    continuation_token=new_token,
                    px_cookies=px_cookies,
                )
                final_token = verify2.get("continuationToken", "")
            else:
                final_token = new_token

            result = self.step6_create_account(
                email=email,
                password=password,
                country=country,
                birth_day=birth_day,
                birth_month=birth_month,
                birth_year=birth_year,
                first_name=first_name,
                last_name=last_name,
                continuation_token=final_token,
            )

            success = "redirectUrl" in (result or {})
            if success:
                log_box(
                    "注册成功",
                    [
                        f"邮箱:  {email}",
                        f"密码:  {password}",
                        f"姓名:  {first_name} {last_name}",
                        f"生日:  {birth_year}-{birth_month}-{birth_day}",
                    ],
                    C_GREEN,
                )
            return {
                "success": success,
                "email": email,
                "password": password,
                "first_name": first_name,
                "last_name": last_name,
                "result": result,
            }
        except Exception as e:
            log_step("ERROR", str(e), "ERROR")
            return {"success": False, "error": str(e), "email": email}
        finally:
            self.close()


# ============================================================
#  CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Microsoft Outlook 纯协议注册（仅注册）")
    parser.add_argument("--username", default="", help="邮箱用户名 (留空随机)")
    parser.add_argument("--domain", default="outlook.com", choices=DOMAINS, help="邮箱域名")
    parser.add_argument("--password", default="", help="密码 (留空随机)")
    parser.add_argument("--country", default="US", help="国家 ISO 代码 (默认 US)")
    parser.add_argument("--year", type=int, default=0, help="出生年份 (留空随机)")
    parser.add_argument("--month", type=int, default=0, help="出生月份 (留空随机)")
    parser.add_argument("--day", type=int, default=0, help="出生日期 (留空随机)")
    parser.add_argument("--firstname", default="", help="名字 (留空随机)")
    parser.add_argument("--lastname", default="", help="姓氏 (留空随机)")
    parser.add_argument("--proxy", default=None, help="代理, 如 http://user:pass@host:port")
    parser.add_argument("--proxy-file", default=None, help="代理列表文件 (随机取一行)")
    parser.add_argument("--cr-token", required=True, help="CaptchaRun API token")
    parser.add_argument("--output", default="accounts.txt", help="成功账号输出文件")
    args = parser.parse_args()

    proxy_url = None
    if args.proxy_file:
        with open(args.proxy_file, "r", encoding="utf-8") as f:
            proxies = [normalize_proxy(line) for line in f]
        proxies = [p for p in proxies if p]
        if not proxies:
            raise SystemExit(f"代理文件为空或格式无效: {args.proxy_file}")
        proxy_url = random.choice(proxies)
        log(f"从代理文件随机选取: {proxy_url.split('@')[-1]}")
    elif args.proxy:
        proxy_url = normalize_proxy(args.proxy)
        if not proxy_url:
            raise SystemExit(f"代理格式无效: {args.proxy}")

    if not proxy_url:
        raise SystemExit("注册需要代理，请传 --proxy 或 --proxy-file")

    username = args.username or random_username()
    password = args.password or random_password()
    first_name = args.firstname or random.choice(FIRST_NAMES)
    last_name = args.lastname or random.choice(LAST_NAMES)
    if args.year and args.month and args.day:
        birth_year, birth_month, birth_day = args.year, args.month, args.day
    else:
        birth_year, birth_month, birth_day = random_birthdate()

    ua, sec_ch = gen_edge_ua()
    cr_solver = CaptchaRunSolver.from_proxy_url(
        token=args.cr_token,
        proxy_url=proxy_url,
        user_agent=ua,
    )

    signup = MicrosoftSignupProtocol(
        proxy=proxy_url,
        user_agent=ua,
        sec_ch_ua=sec_ch,
    )
    result = signup.register(
        username=username,
        domain=args.domain,
        password=password,
        country=args.country,
        birth_year=birth_year,
        birth_month=birth_month,
        birth_day=birth_day,
        first_name=first_name,
        last_name=last_name,
        cr_solver=cr_solver,
    )

    if result.get("success"):
        line = f"{result['email']}----{result['password']}\n"
        with open(args.output, "a", encoding="utf-8") as f:
            f.write(line)
        log(f"已写入 {args.output}: {result['email']}", "OK")
    else:
        log(f"注册失败: {result.get('error', 'unknown')}", "ERROR")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

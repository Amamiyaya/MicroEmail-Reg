# Outlook Protocol Register (Lite)

基于纯 HTTP 协议的 Microsoft Outlook / Hotmail 注册脚本精简版。  
不启动浏览器，直接调用 Microsoft 注册相关接口，并通过 CaptchaRun 处理 PerimeterX（PxCaptcha2）人机验证。

> 本项目从完整注册机中抽取了**仅注册**流程，已移除 OAuth2 授权、多线程批量、账号导入等附加能力。

对应脚本：`outlook_register_only.py`

---

## 功能特性

- **纯协议注册**：使用 `curl_cffi` 模拟浏览器 TLS/HTTP 指纹，无需 Selenium / Playwright
- **自动过 PX 验证**：对接 CaptchaRun `PxCaptcha2`（silentToken → pressToken）
- **代理支持**：支持单代理或代理列表文件
- **随机资料**：用户名、密码、姓名、生日可自动生成
- **结果落盘**：注册成功后追加写入本地文件

---

## 注册流程

```text
1. GET  signup.live.com
   └─ 提取 ServerData（apiCanary / uaid）
   └─ 加载 DFP + PX iframe

2. POST CheckAvailableSigninNames
   └─ 检查邮箱用户名是否可用

3. POST risk/initialize
   └─ 获取 continuationToken

4. CaptchaRun 创建 PxCaptcha2 任务
   └─ 等待 silentToken

5. POST risk/verify（第 1 次）
   └─ 通常返回 riskChallengeRequired

6. CaptchaRun 等待 pressToken
   └─ 拿到 _px3 / _pxde / _pxvid

7. POST risk/verify（第 2 次）
   └─ 提交 challengeSolution，获取最终 token

8. POST CreateAccount
   └─ 创建账号
```

---

## 环境要求

- Python 3.9+
- 可用的 HTTP 代理（住宅代理更稳）
- CaptchaRun 账号与 API Token（需支持 `PxCaptcha2`）

### 依赖安装

```bash
pip install curl_cffi requests
```

---

## 快速开始

### 1. 获取 CaptchaRun Token

1. 打开官网：https://captcha.run/
2. 注册并登录控制台
3. 复制 API Token（Bearer Token）
4. 确认账户有余额，且支持 `PxCaptcha2`

### 2. 准备代理

单代理示例：

```text
http://username:password@host:port
```

代理文件 `proxies.txt`（每行一个，支持以下格式）：

```text
http://user:pass@1.2.3.4:8080
user:pass@1.2.3.4:8080
1.2.3.4:8080:user:pass
1.2.3.4:8080
```

### 3. 运行注册

```bash
python outlook_register_only.py \
  --cr-token YOUR_CAPTCHARUN_TOKEN \
  --proxy http://user:pass@host:port
```

或从代理文件随机取一个：

```bash
python outlook_register_only.py \
  --cr-token YOUR_CAPTCHARUN_TOKEN \
  --proxy-file proxies.txt \
  --country US
```

---

## 命令行参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--cr-token` | ✅ | 无 | CaptchaRun API Token |
| `--proxy` | 二选一 | 无 | 单个代理地址 |
| `--proxy-file` | 二选一 | 无 | 代理列表文件（随机取一行） |
| `--username` | ❌ | 随机 | 邮箱用户名（不含域名） |
| `--password` | ❌ | 随机 | 账号密码 |
| `--domain` | ❌ | `outlook.com` | 域名：`outlook.com` / `hotmail.com` |
| `--country` | ❌ | `US` | 国家 ISO 代码（如 `US` / `CN`） |
| `--year` / `--month` / `--day` | ❌ | 随机 | 出生日期 |
| `--firstname` | ❌ | 随机 | 名 |
| `--lastname` | ❌ | 随机 | 姓 |
| `--output` | ❌ | `accounts.txt` | 成功账号输出文件 |

> 注意：`--proxy` 与 `--proxy-file` 至少提供一个，脚本强制要求代理。

---

## 使用示例

### 完全随机注册

```bash
python outlook_register_only.py \
  --cr-token YOUR_TOKEN \
  --proxy-file proxies.txt
```

### 指定邮箱与密码

```bash
python outlook_register_only.py \
  --cr-token YOUR_TOKEN \
  --proxy http://user:pass@host:port \
  --username mytestuser123 \
  --password 'Aa123456!' \
  --domain outlook.com \
  --country US \
  --firstname John \
  --lastname Smith \
  --year 1998 --month 5 --day 12
```

### 指定输出文件

```bash
python outlook_register_only.py \
  --cr-token YOUR_TOKEN \
  --proxy-file proxies.txt \
  --output success_accounts.txt
```

---

## 输出格式

注册成功后，账号会以追加方式写入 `--output` 指定文件：

```text
xxx@outlook.com----Password123!
yyy@hotmail.com----Abcd4567!
```

格式：

```text
email----password
```

控制台成功时会打印类似：

```text
────────────────────────────────────────
│ 注册成功
│ 邮箱:  xxx@outlook.com
│ 密码:  xxxxxxxx
│ 姓名:  John Smith
│ 生日:  1998-5-12
────────────────────────────────────────
```

失败时退出码为 `1`，并打印错误原因，例如：

- `username_unavailable`：用户名已被占用
- `no_captcha_solver`：未提供 CaptchaRun token
- 打码超时 / 打码失败
- 网络或接口异常

---

## 项目结构（核心类）

```text
outlook_register_only.py
├── CaptchaRunSolver          # CaptchaRun PxCaptcha2 打码
├── MicrosoftSignupProtocol   # Microsoft 注册协议实现
│   ├── step1_fetch_signup_page
│   ├── step2_check_username
│   ├── step3_risk_initialize
│   ├── step4_risk_verify_first
│   ├── step5_risk_verify_second
│   ├── step6_create_account
│   └── register              # 串联完整流程
└── main()                    # CLI 入口
```

---

## 与完整版的区别

| 能力 | 本精简版 | 完整版注册机 |
|------|----------|--------------|
| 协议注册 | ✅ | ✅ |
| CaptchaRun PX 打码 | ✅ | ✅ |
| OAuth2 拿 refresh_token | ❌ | ✅ |
| 多线程批量 | ❌ | ✅ |
| 导入 mail_manager | ❌ | ✅ |
| 补授权 fix-auth | ❌ | ✅ |

本仓库目标：**流程清晰、依赖少、只做注册。**

---

## 常见问题

### 1. 提示需要代理？

脚本默认强制走代理。请使用 `--proxy` 或 `--proxy-file`。

### 2. CaptchaRun 一直失败？

检查：

- Token 是否正确（`Authorization: Bearer ...`）
- 账户余额是否充足
- 是否支持 `PxCaptcha2`
- 代理是否可用，且与 CaptchaRun 任务使用同一代理信息

### 3. 用户名不可用？

换一个 `--username`，或留空让脚本随机生成。

### 4. 注册成功率不稳定？

常见影响因素：

- 代理质量（数据中心代理通常更差）
- 地区与 `--country` 是否匹配
- CaptchaRun 解题耗时与成功率
- Microsoft 风控策略变化

---

## 免责声明

本项目仅供协议研究、接口学习与个人测试。  
请遵守 Microsoft 服务条款及当地法律法规。  
因滥用自动化注册导致的封号、封 IP、账号损失等，作者不承担任何责任。

---

## License

MIT

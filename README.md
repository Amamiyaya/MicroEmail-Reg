# Outlook Protocol Register

基于纯 HTTP 协议的 Microsoft Outlook / Hotmail **自动注册 + OAuth 授权** 工具。  
不依赖浏览器 UI，直接调用 Microsoft 注册 / 登录相关接口，并通过 CaptchaRun 处理 PerimeterX（PxCaptcha2）人机验证。

注册成功后会自动走 OAuth2 授权，获取可用于邮件收发的 `refresh_token`，并支持写入本地文件、多线程批量、补授权、导入外部邮件管理系统。

对应脚本：`outlook注册机.py`

> ⚠️ 本项目涉及自动化账号注册与接口模拟，请仅用于合法、授权的研究与测试。请遵守 Microsoft 服务条款与当地法律法规。

---

## 功能特性

- **纯协议注册**：`curl_cffi` 模拟浏览器 TLS/HTTP 指纹，无需 Selenium / Playwright
- **CaptchaRun 打码**：自动处理 `PxCaptcha2`（silentToken → pressToken）
- **注册后 OAuth2 授权**：模拟浏览器登录，获取 `access_token` / `refresh_token`
- **多线程批量**：`--threads` 并发注册，线程间随机代理与随机资料
- **代理池**：支持单代理 / 代理文件，自动解析多种代理格式
- **代理地理探测**：根据代理 IP 自动识别国家 / 时区，供打码使用
- **结果落盘**：`email----password----client_id----refresh_token`
- **补授权模式**：`--fix-auth` 扫描旧账号文件，补全缺失的 refresh_token
- **可选导入 mail_manager**：注册+授权成功后自动 POST 到外部管理系统

---

## 整体流程

```text
┌──────────────────────────────────────────────┐
│ 1. 注册阶段                                   │
│   GET signup.live.com                         │
│   → 提取 ServerData / DFP / PX iframe         │
│   → CheckAvailableSigninNames                 │
│   → risk/initialize                           │
│   → CaptchaRun PxCaptcha2                     │
│   → risk/verify (1st / 2nd)                   │
│   → CreateAccount                             │
└──────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│ 2. OAuth2 授权阶段                            │
│   GET oauth2/v2.0/authorize                   │
│   → GetCredentialType                         │
│   → login.live.com 密码页                     │
│   → checkpassword.srf                         │
│   → ppsecure/post.srf                         │
│   → 跳过 passkey / KMSI / Consent             │
│   → code 换 token                             │
└──────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│ 3. 落盘 / 导入                                │
│   写入 accounts.json                          │
│   可选导入 mail_manager                       │
└──────────────────────────────────────────────┘
```

---

## 环境要求

- Python 3.9+
- 可用 HTTP 代理（建议住宅代理）
- CaptchaRun 账号与 API Token（需支持 `PxCaptcha2`）

### 安装依赖

```bash
pip install curl_cffi requests
```

---

## 快速开始

### 1. 获取 CaptchaRun Token

1. 打开官网：https://captcha.run/
2. 注册并登录控制台
3. 复制 API Token（Bearer Token）
4. 确认余额充足，并支持 `PxCaptcha2`

### 2. 准备代理

单代理：

```text
http://username:password@host:port
```

代理文件 `proxies.txt`（每行一个，支持多种格式）：

```text
http://user:pass@1.2.3.4:8080
user:pass@1.2.3.4:8080
1.2.3.4:8080:user:pass
1.2.3.4:8080
```

### 3. 单线程注册

```bash
python outlook注册机.py \
  --cr-token YOUR_CAPTCHARUN_TOKEN \
  --proxy http://user:pass@host:port \
  --country US
```

### 4. 多线程批量注册

```bash
python outlook注册机.py \
  --cr-token YOUR_CAPTCHARUN_TOKEN \
  --proxy-file proxies.txt \
  --threads 5 \
  --country US \
  --domain outlook.com \
  --output accounts.json
```

---

## 命令行参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--cr-token` | 建议必填 | `填自己打令牌` | CaptchaRun API Token |
| `--proxy` | 建议 | 无 | 单个代理地址 |
| `--proxy-file` | 建议 | 无 | 代理列表文件 |
| `--threads` | ❌ | `1` | 并发线程数 |
| `--domain` | ❌ | `outlook.com` | `outlook.com` / `hotmail.com` |
| `--country` | ❌ | `US` | 国家 ISO 代码 |
| `--username` | ❌ | 随机 | 仅单线程模式有意义 |
| `--password` | ❌ | 随机 | 仅单线程模式有意义 |
| `--year` / `--month` / `--day` | ❌ | 随机 | 生日 |
| `--firstname` / `--lastname` | ❌ | 随机 | 姓名 |
| `--output` | ❌ | `accounts.json` | 输出文件路径 |
| `--fix-auth` | ❌ | 关闭 | 扫描输出文件，补全缺失 refresh_token |
| `--import-url` | ❌ | 占位字符串 | mail_manager 服务器地址 |
| `--import-password` | ❌ | `apple2024` | mail_manager 访问密码 |

> 实际使用时请把 `--cr-token`、代理、导入地址等占位默认值改成你自己的配置。

---

## 使用示例

### 完全随机单号注册

```bash
python outlook注册机.py \
  --cr-token YOUR_TOKEN \
  --proxy-file proxies.txt
```

### 指定资料注册

```bash
python outlook注册机.py \
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

### 5 线程批量注册

```bash
python outlook注册机.py \
  --cr-token YOUR_TOKEN \
  --proxy-file proxies.txt \
  --threads 5 \
  --output accounts.json
```

### 补授权（不注册，只补 refresh_token）

```bash
python outlook注册机.py \
  --fix-auth \
  --output accounts.json \
  --proxy-file proxies.txt
```

### 注册后自动导入 mail_manager

```bash
python outlook注册机.py \
  --cr-token YOUR_TOKEN \
  --proxy-file proxies.txt \
  --threads 3 \
  --import-url https://your-mail-manager.example.com \
  --import-password your_password
```

---

## 输出格式

默认写入 `--output`（默认 `accounts.json`，实际是按行文本）：

```text
xxx@outlook.com----Password123!----9e5f94bc-e8a4-4e73-b8be-63364c29d753----M.C5...refresh_token...
yyy@hotmail.com----Abcd4567!----9e5f94bc-e8a4-4e73-b8be-63364c29d753----
```

字段含义：

```text
email----password----client_id----refresh_token
```

- 第 1 段：邮箱
- 第 2 段：密码
- 第 3 段：OAuth client_id（Thunderbird 公共客户端）
- 第 4 段：refresh_token（OAuth 失败时可能为空）

---

## OAuth2 说明

注册成功后会自动调用 `oauth2_authorize()`：

1. 打开 Microsoft OAuth 授权页
2. 校验账号密码
3. 处理 passkey / KMSI / Consent 中断页
4. 获取 authorization `code`
5. 用 `code` 换取：
   - `access_token`
   - `refresh_token`

### 使用的客户端

```text
client_id  = 9e5f94bc-e8a4-4e73-b8be-63364c29d753
redirect   = https://login.microsoftonline.com/common/oauth2/nativeclient
```

### 主要 scope

- `offline_access`
- `openid profile`
- `https://graph.microsoft.com/Mail.Read`
- `https://graph.microsoft.com/Mail.Send`
- `https://graph.microsoft.com/IMAP.AccessAsUser.All`
- `https://graph.microsoft.com/POP.AccessAsUser.All`
- `https://graph.microsoft.com/SMTP.Send`

> 注意：本脚本会获取邮件相关 token，但**不会**在脚本内读取收件箱或提取邮件验证码。  
> 读信通常需要你另行使用 Graph / IMAP，或导入到 mail_manager 后处理。

---

## 核心模块

```text
outlook注册机.py
├── CaptchaRunSolver              # CaptchaRun PxCaptcha2 打码
├── MicrosoftSignupProtocol       # 微软注册协议
│   ├── step1_fetch_signup_page
│   ├── step4_check_username
│   ├── step3_risk_initialize
│   ├── step5_risk_verify
│   ├── step5b_risk_verify
│   ├── step7_create_account
│   └── register
├── oauth2_authorize()            # 注册后 OAuth2 登录拿 token
├── _register_one()               # 单线程任务：注册 + OAuth + 落盘 + 导入
├── _fix_auth()                   # 扫描账号文件补授权
├── _import_to_server()           # 导入 mail_manager
└── main()                        # CLI 入口 / 多线程调度 / 统计
```

---

## 运行统计

任务结束后会打印类似：

```text
══════════════════════════════════════════════════
  任务统计 (共 N 个)
══════════════════════════════════════════════════
  注册 + OAuth2 成功:  x
  注册成功, OAuth2 失败: y
  打码失败:            z
  注册失败 (其他):     w
  导入服务器成功:       a
  导入服务器失败:       b
══════════════════════════════════════════════════
```

---

## 与精简版的区别

| 能力 | 完整版（本项目） | 精简版 `outlook_register_only.py` |
|------|------------------|-----------------------------------|
| 协议注册 | ✅ | ✅ |
| CaptchaRun PX 打码 | ✅ | ✅ |
| OAuth2 拿 refresh_token | ✅ | ❌ |
| 多线程批量 | ✅ | ❌ |
| 导入 mail_manager | ✅ | ❌ |
| 补授权 `--fix-auth` | ✅ | ❌ |
| 输出含 client_id / token | ✅ | 仅 email----password |

如果你只需要“开号”，用精简版更清晰；  
如果你需要“可程序化使用的邮箱 token”，用本完整版。

---

## 常见问题

### 1. 必须要代理吗？

实际使用中建议必须。  
CaptchaRun 的 `PxCaptcha2` 任务会带上代理信息，注册与打码应尽量使用同一出口 IP。

### 2. CaptchaRun 失败怎么办？

检查：

- `--cr-token` 是否正确
- 账户余额是否足够
- 是否支持 `PxCaptcha2`
- 代理是否可用

### 3. 注册成功但 OAuth 失败？

账号仍会保存，但 `refresh_token` 为空。  
可以稍后用：

```bash
python outlook注册机.py --fix-auth --output accounts.json --proxy-file proxies.txt
```

补授权。

### 4. 为什么叫 `accounts.json`，内容却是文本行？

历史命名问题。实际输出是按行文本，不是标准 JSON 数组。

### 5. 能直接读邮件验证码吗？

不能。  
本脚本只负责：

- 注册
- OAuth 拿 token
- 保存 / 导入

如需读信，需要自行使用 `refresh_token` 调 Graph 或 IMAP。

### 6. 成功率不稳定？

常见影响因素：

- 代理质量与地区
- CaptchaRun 解题成功率 / 延迟
- Microsoft 风控策略变化
- 并发过高

---

## 安全建议

- 不要把真实 `--cr-token`、代理密码、import 密码提交到 GitHub
- 建议用环境变量或本地配置文件管理密钥
- 输出的 `accounts.json` 含账号凭证，注意权限与备份
- 公开仓库前先检查是否误传账号、token、代理

---

## 免责声明

本项目仅供协议研究、接口学习与个人测试。  
请遵守 Microsoft 服务条款及当地法律法规。  
因滥用自动化注册、批量开号、绕过风控等行为导致的任何损失或法律责任，由使用者自行承担。

---

## License

MIT

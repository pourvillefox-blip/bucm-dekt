# 北中医第二课堂 · 活动学分汇总

聚合北京中医药大学第二课堂学分活动的信息页。网页为纯静态单文件，数据每 3 天自动抓取，另有健康检查与邮件告警。

**线上地址**：https://pourvillefox-blip.github.io/bucm-dekt/
**仓库**：https://github.com/pourvillefox-blip/bucm-dekt （public）

## 当前状态（2026-11-08）

- 官网抓取：8 个栏目可用，最近一次入库 44 条。
- 公众号：搜狗微信线索 4 条 + WeRSS 微信读书通道 3 条（含当天活动）。
- 人工补充：3 条已核验的公众号活动。
- 当前共 56 条：A 级 2、B 级 7、C 级 47；默认“近 30 天”10 条，今日新增 2 条。
- 定时任务：本机每 3 天抓取并自动 push；每 2 小时健康检查。
- 邮件告警：已配置并测试通过（发件 `3026664502@qq.com` → 收件 `pourvillefox@qq.com`）。

## 目录结构

```
bucm-dekt/
├── config.json           # 数据源、关键词、邮件配置（含密码，已被 .gitignore 排除）
├── data/
│   ├── manual.json       # 人工核验补充的公众号活动（手工维护）
│   ├── official.json     # 官网抓取结果
│   ├── wechat.json       # 公众号抓取结果
│   ├── combined.json     # 合并去重后的最终数据
│   └── health.json       # 最近一次健康检查结果
├── docs/index.html       # 生成的网页（GitHub Pages 从这里发布）
├── site/template.html    # 页面模板
├── scripts/
│   ├── crawl_official.py # 抓校团委等官方栏目
│   ├── crawl_wechat.py   # 搜狗微信线索（尽力而为）
│   ├── build_site.py     # 合并数据并生成网页
│   ├── run_update.py     # 更新总入口（失败自动回滚）
│   ├── healthcheck.py    # 健康检查 + 邮件告警
│   ├── notify.py         # 邮件发送
│   ├── deploy.py         # git 提交并推送
│   └── setup_tasks.bat   # 注册 Windows 定时任务
└── logs/                 # 运行日志
```

## 快速开始

```bat
cd C:\Users\Fox\bucm-dekt
python scripts\run_update.py
python scripts\healthcheck.py
```

然后用浏览器打开 `docs\index.html`。

## 配置邮件告警

编辑 `config.json` 的 `email` 段（QQ 邮箱示例）：

```json
"email": {
  "enabled": true,
  "smtp_host": "smtp.qq.com",
  "smtp_port": 465,
  "use_ssl": true,
  "username": "你的QQ邮箱@qq.com",
  "password": "SMTP授权码（不是登录密码）",
  "to": "接收告警的邮箱@example.com",
  "cooldown_hours": 12
}
```

QQ 邮箱授权码在「设置 → 账户 → POP3/IMAP/SMTP 服务」里生成。163 邮箱同理（`smtp.163.com`）。

> 当前已配置完成并测试通过。QQ 授权码按账号绑定，换发件账号时必须同时更新授权码；健康时不会发信，可临时把 `stale_days` 改成 0 触发一次测试。

## 部署到 GitHub Pages

```bat
cd C:\Users\Fox\bucm-dekt
git init
git add .
git commit -m "init"
gh repo create bucm-dekt --public --source=. --remote=origin --push
```

然后到 GitHub 仓库 → Settings → Pages → Source 选 `Deploy from a branch`，分支 `main`，目录 `/docs`。

`config.json` 里 `deploy.enabled` 已设为 `true`，`run_update.py` 生成网页后会自动提交并推送，无需手动执行。手动推送仍可用：

```bat
python scripts\deploy.py
```

> 仓库是 public 的，网页内容任何人有链接都能访问。如果想让页面长期在线，这是最简单的方式；如果不想公开，可以改用私有服务器。

## 注册定时任务

右键以**普通用户**运行（不需要管理员）：

```bat
scripts\setup_tasks.bat
```

会创建两个任务：

| 任务 | 频率 | 作用 |
|---|---|---|
| `BUCM-DEKT-Update` | 每 3 天 03:00 | 官网 + 公众号 + 构建 + 部署 |
| `BUCM-DEKT-WeChat` | 每 12 小时 09:30/21:30 | 只刷新公众号 RSS + 构建 + 部署 |
| `BUCM-DEKT-Health` | 每 2 小时 | 检查页面、数据、WeRSS 登录态，异常发邮件 |

> ⚠️ 任务只在电脑开机、已登录且未休眠时执行；关机期间不会更新，也不会告警。要 7×24 更新，需要云服务器、GitHub Actions 或外部探针。

## 备份与日志

- 每次 3 天完整更新前自动备份 `config.json`、`data/manual.json` 和 WeRSS 的 `werss.db` 到 `backups/<时间戳>/`，保留最近 10 份。
- 日志按 2 MB 轮转，保留 3 个历史文件。
- Git 已固定使用 OpenSSL HTTPS 后端（`git config --global http.sslBackend openssl`），避免 schannel 偶发握手失败。
>
> 任务已设置为“允许电池供电、错过时间后补跑”，但仍是交互式登录模式。

## 微信公众号 RSS（已部署 WeRSS）

本机已部署 WeRSS：`C:\Users\Fox\we-mp-rss`，使用**微信读书通道**（`gather.model: weread_mp`）。

- 启动：`C:\Users\Fox\we-mp-rss\start_WeRSS_background.bat`
- 管理页：http://127.0.0.1:8001 （账号 `Fox`）
- 已订阅 8 个号：北京中医药大学、岐黄青年汇、bucm社联、中医学院青协、北京中医药大学学生会、活动周历（校学生会）、针道青年（针推学院）、岐黄志愿者之家
- 守护任务：`WeRSS-KeepAlive` 每 30 分钟检查一次，未运行则启动

`config.json` 的 `wechat_rss` 已填好四个 feed 地址，并开启 `refresh`：每次 `crawl_rss.py` 会先让 WeRSS 更新四个号的最新文章，再读取 feed。

RSS 解析已读取 `<content:encoded>` 全文，因此能提取摘要、学分数和报名截止时间；校内官方账号且正文明确写“第二课堂 X 学分”的条目会升到 A 级。

```json
"wechat_rss": {
  "enabled": true,
  "refresh": true,
  "admin_url": "http://127.0.0.1:8001",
  "feeds": [{"name": "岐黄青年汇", "url": "http://127.0.0.1:8001/feed/MP_WXS_xxx.xml"}]
}
```

> 限制：微信读书通道每次通常只返回每个号的最新一篇，所以历史文章不会一次性补齐；但最新活动不会漏。公众号后台 `app` 模式能翻页，但新账号会长期返回 `200013 frequency control`，暂不可用。
>
> 新增账号价值：`岐黄志愿者之家` 每周发志愿活动预告、`活动周历` 发每周沙龙/活动，价值最高；学生会、针道青年偏日常内容，活动密度较低，但偶尔有比赛和招募。

## 移动端

手机（≤760px）自动切换为：

- A/B/C 分段切换 + 单列卡片流，按 A→B→C、再按时间倒序；
- 顶部统计改为 3 列网格，全部可见；
- “学分速查”在手机端默认折叠，点击标题展开；
- 搜索框占满整行，筛选按钮横向滑动；
- 回到顶部按钮。

> GitHub Pages 的 Jekyll 构建**不接受 `<details>` 元素**，会导致 `Page build failed`。规则折叠改用普通 `section` + JS 类切换实现。

## 手动补充公众号活动

微信反爬严格，自动化只能抓到少量线索。你在微信里看到相关活动时，把信息加到 `data/manual.json` 的 `items` 数组：

```json
{
  "title": "活动标题",
  "account": "公众号名称",
  "publish_date": "2026-11-01",
  "url": "https://mp.weixin.qq.com/s/...",
  "summary": "一句话说明",
  "credit": "0.1",
  "credit_type": "综合素质",
  "deadline": "2026-11-20",
  "source_level": "B",
  "source_type": "manual",
  "evidence": "原文中关于学分的原句"
}
```

保存后跑一次 `python scripts\build_site.py` 即可出现在网页上。

## 核验等级

- **A**：官方来源，原文明确写出第二课堂学分数
- **B**：官方来源或公众号原文提到第二课堂/学分，但未给数值
- **C**：仅标题/摘要命中关键词，尚未核验

## 已知限制

1. **微信公众号不可稳定自动抓取**：`mp.weixin.qq.com` 正文直连被拦，搜狗微信索引滞后且限流。自动抓取只作为线索，主要靠 `manual.json` 补充。
2. **官网栏目以公示/新闻为主**：真正可报名的活动多在企业微信“微课堂”内，无法爬取。
3. **时间段**：默认只收录 2025-09-01 之后的内容，可在 `config.json` 的 `cutoff_date` 调整。

## 故障排查

| 现象 | 处理 |
|---|---|
| 收到“更新失败”邮件 | 看 `logs/run_update.log`，常见为官网改版或断网；数据已自动回滚 |
| 收到“页面异常”邮件 | 看 `logs/healthcheck.log`；若 `docs/index.html` 缺失，重跑 `build_site.py` |
| 邮件发不出 | 检查授权码、SMTP 端口（465 SSL / 587 STARTTLS）、是否被邮箱拦截 |
| 定时任务没跑 | `schtasks /Query /TN "BUCM-DEKT-Update" /V` 查看上次运行结果；确认电脑当时开机 |

# 北中医第二课堂 · 活动学分汇总

聚合北京中医药大学第二课堂学分活动的信息页。网页为纯静态单文件，数据每 3 天自动抓取，另有健康检查与邮件告警。

**线上地址**：https://pourvillefox-blip.github.io/bucm-dekt/
**仓库**：https://github.com/pourvillefox-blip/bucm-dekt （public）

## 当前状态（2026-11-08）

- 官网抓取：6 个栏目可用，最近一次入库 27 条。
- 公众号抓取：搜狗微信索引陈旧，只作为低精度线索，最近一次 4 条。
- 人工补充：3 条已核验的公众号活动。
- 定时任务：本机每 3 天抓取并自动 push；每 2 小时健康检查。
- 邮件告警：**尚未配置 SMTP 授权码，当前不会真正发信**。

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

> 当前 `password` 为空，邮件告警尚不可用；填好授权码后可用 `python scripts\healthcheck.py` 验证（健康时不会发信，可临时把 `stale_days` 改成 0 触发一次测试）。

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
| `BUCM-DEKT-Update` | 每 3 天 03:00 | 抓取 + 生成网页 |
| `BUCM-DEKT-Health` | 每 2 小时 | 检查页面/数据，异常发邮件 |

> ⚠️ 任务只在电脑开机、已登录且未休眠时执行；关机期间不会更新，也不会告警。要 7×24 更新，需要云服务器、GitHub Actions 或外部探针。
>
> 任务已设置为“允许电池供电、错过时间后补跑”，但仍是交互式登录模式。

## 接入微信公众号 RSS（可选）

如果后续部署了 Wechat2RSS 或 WeRSS，可在 `config.json` 里打开 RSS 通道：

```json
"wechat_rss": {
  "enabled": true,
  "feeds": [
    {"name": "岐黄青年汇", "url": "https://你的RSS服务/feed/xxxx"}
  ]
}
```

然后运行 `python scripts\crawl_rss.py`。只接受标题/摘要里明确提到“第二课堂”且与北中医相关的条目，结果写入 `data/rss.json`，构建时自动合并。

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

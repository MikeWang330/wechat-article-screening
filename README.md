# 微信公众号文章筛选 + MinerU 批量解析

这个项目在本地电脑运行，用来完成三件事：

1. 按关键词搜索微信公众号文章。
2. 按商业/行业报告标准筛选高价值内容。
3. 把可用的微信原文链接交给 MinerU，生成本地 Markdown 和 HTML 结果。

默认使用场景：饮料公司的商业分析部门。用户只需要输入研究主题、时间范围和目标篇数，不需要理解底层搜索、验证和转换流程。

完整筛选标准见 [SCREENING_STANDARD.md](SCREENING_STANDARD.md)。

## 准备环境

安装 Python 后，在项目目录运行：

```powershell
pip install -r requirements.txt
```

准备 MinerU Token：

```text
https://mineru.net/apiManage/token
```

推荐用环境变量保存：

```powershell
$env:MINERU_TOKEN="你的 MinerU Token"
```

也可以创建 `mineru_token.txt`，把 Token 单独放进去。这个文件不会上传到 GitHub。

## 启动网页

在项目目录运行：

```powershell
python web_app.py
```

然后打开：

```text
http://127.0.0.1:8787
```

网页里只需要做几件事：

- 输入搜索关键词。
- 选择时间范围，例如过去一年、过去三个月。
- 填目标篇数。
- 在设置页填 LLM API 和 MinerU Token。
- 点击“开始任务”。

LLM 只用于扩充关键词。后续搜索、筛选、微信链接验证、本地 HTML 准备和 MinerU 转换，都由本地程序执行。

## 局域网试用

如果你的电脑开着，同一个网络里的同事也可以访问你的网页。

启动后，终端会显示类似：

```text
Open on the same network: http://10.x.x.x:8787
```

把这个地址发给同事即可。

注意：

- 所有任务实际都跑在你的电脑上。
- 如果搜狗要求验证，浏览器窗口会弹在你的电脑上，需要你完成验证。
- 一次建议只让一个人运行任务，避免排队和触发风控。
- 如果同事打不开，通常是 Windows 防火墙拦截了 Python，需要允许专用网络访问。

## 搜狗验证

项目不会绕过验证码。

如果搜狗微信搜索要求验证，程序会打开 Chrome 或 Edge 窗口。请在窗口里完成验证，验证后不要立刻关闭窗口，程序会继续采集结果。

如果已经筛出候选文章，但没有拿到微信原文链接，可以在网页里点“重试验证”。这会复用候选表，只重新尝试把候选链接转成 `mp.weixin.qq.com` 原文链接。

## 自动模式命令

不使用网页时，也可以直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "百岁山 降价" -Count 20
```

指定时间范围：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "电解质水 世界杯 营销" -Count 20 -StartDate "2025-07-01" -EndDate "2026-07-03"
```

只生成 `urls.txt`，暂时不跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "饮料 行业分析" -Count 20 -OnlyUrls
```

## 手动 URL 模式

如果你已经有微信公众号文章链接，创建 `urls.txt`：

```text
https://mp.weixin.qq.com/s/xxxx
https://mp.weixin.qq.com/s/yyyy
```

然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

## 输出位置

搜索候选：

```text
candidates/
```

最终解析结果：

```text
runs/
  20260703-120000-urls/
    markdown/
    html/
    summary.md
    result.json
    successful_urls.txt
    failed_urls.txt
```

最新一次运行目录会写入：

```text
latest_run.txt
```

长期索引会保存到：

```text
library/articles_index.csv
```

## 筛选逻辑

程序默认按商业分析用途筛选，不会为了凑数量强行加入弱相关文章。

优先保留：

- 案例复盘
- 行业分析
- 数据报告
- 深度访谈
- 策略拆解
- 有市场、渠道、价格带、竞品、消费者、终端、供应链信息的文章

默认排除：

- 招聘、课程、资料包下载
- 纯新闻快讯、活动预告、会议通知
- 浅层榜单、低价值转载
- 没有正文或内容过短的文章

如果目标是 20 篇，但只找到 12 篇高质量文章，程序会返回 12 篇，而不是补弱相关内容。

## 常见问题

### 为什么数量经常不够？

因为最终只保留同时满足三件事的文章：

1. 搜索阶段能找到。
2. 筛选阶段足够相关。
3. 验证阶段能转成可访问的微信原文链接。

任意一步失败，都会被排除。

### 为什么会卡在验证微信链接？

这一步需要本机浏览器打开搜狗跳转链接。如果浏览器启动失败、搜狗要求验证、或链接已失效，就可能拿不到微信原文链接。

可以稍后重试，或在网页里点“重试验证”。

### MinerU 提示额度用完怎么办？

如果看到：

```text
daily web crawl limit reached max: 100 tasks, submit tomorrow
```

说明 MinerU 当天额度用完。第二天额度恢复后，可以继续运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

### 哪些文件不会上传？

这些属于本地运行数据，已被 `.gitignore` 忽略：

- `mineru_token.txt`
- `research_memory.json`
- `urls.txt`
- `runs/`
- `candidates/`
- `outputs/`
- `work/`
- `library/articles_index.csv`

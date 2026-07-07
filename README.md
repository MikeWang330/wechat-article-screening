# 微信公众号文章筛选 + MinerU 本地解析

这个项目在本地电脑运行，用来搜索、筛选并解析微信公众号文章。默认面向饮料公司的商业分析部门，使用者不需要理解终端、脚本或浏览器验证细节。

程序会完成：

1. 根据研究主题扩展搜索词。
2. 搜索微信公众号文章候选。
3. 按商业分析标准筛选高价值内容。
4. 验证微信原文链接是否可访问。
5. 生成本地 HTML / Markdown 结果，必要时交给 MinerU 解析。

筛选标准见 [SCREENING_STANDARD.md](SCREENING_STANDARD.md)。

## 安装

安装 Python 后，在项目目录运行：

```powershell
pip install -r requirements.txt
```

如果要使用 MinerU，准备 Token：

```text
https://mineru.net/apiManage/token
```

推荐把 Token 存成环境变量：

```powershell
$env:MINERU_TOKEN="你的 MinerU Token"
```

也可以新建 `mineru_token.txt`，把 Token 单独放进去。这个文件不会上传到 GitHub。

## 启动网页

在项目目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_web.ps1
```

然后打开：

```text
http://127.0.0.1:8787
```

请保持启动窗口打开。Windows 下不要用隐藏窗口启动网页服务，否则 Chrome 验证窗口可能启动失败。

## 网页怎么用

1. 输入研究主题。
2. 选择时间范围。
3. 选择筛选强度。
4. 在设置页填写 LLM API Key 或 MinerU Token。
5. 点击“开始任务”。

筛选强度决定“质量门槛”和“最多保留数量”：

| 强度 | 含义 | 最多保留 |
|---:|---|---:|
| 1.0 | 极严格，只保留高度精准内容 | 10 |
| 0.8 | 严格，偏质量，少量扩展 | 15 |
| 0.6 | 推荐，质量和覆盖平衡 | 20 |
| 0.4 | 宽松，扩大相关背景 | 30 |
| 0.2 | 很宽，接受外围材料 | 40 |
| 0 | 最大召回，但仍过滤垃圾和坏链接 | 50 |

默认强度是 `0.6`。这些数字是上限，不是承诺数量。程序不会为了凑数加入弱相关或不可访问文章。

## 搜狗验证

项目不会绕过验证码。

如果搜狗微信搜索要求验证，程序会打开 Chrome 窗口。请在窗口里完成验证，验证后不要立刻关闭窗口，程序会继续采集。

如果已经筛出候选文章，但没有拿到微信原文链接，可以在网页里点“重试验证”。它会复用候选表，只重新尝试把候选链接转成 `mp.weixin.qq.com` 原文链接。

## 输出位置

候选表：

```text
candidates/
```

最终结果：

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

程序优先保留：

- 案例复盘
- 行业分析
- 数据报告
- 深度访谈
- 策略拆解
- 包含市场、渠道、价格带、竞品、消费者、终端、供应链信息的文章

默认排除：

- 招聘、课程、资料包下载
- 纯新闻快讯、活动预告、会议通知
- 浅层榜单、低价值转载
- 没有正文、正文过短、链接过期、作者删除、不可访问的文章

如果某个主题在当前时间范围内只找到 11 篇高质量可访问文章，程序会返回 11 篇，而不是硬凑到上限。

## 命令行用法

网页是推荐方式。需要直接运行脚本时，可以用：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "百岁山 降价"
```

指定时间范围：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "电解质水 世界杯 营销" -StartDate "2025-07-01" -EndDate "2026-07-03"
```

只生成 `urls.txt`，暂时不跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "饮料 行业分析" -OnlyUrls
```

命令行仍保留 `-Count`、`-Mode` 等兼容参数，但网页端已经改为使用筛选强度。

## 手动 URL 模式

如果已经有微信公众号文章链接，创建 `urls.txt`：

```text
https://mp.weixin.qq.com/s/xxxx
https://mp.weixin.qq.com/s/yyyy
```

然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

## 常见问题

### 为什么数量经常不满？

因为最终只保留同时满足这些条件的文章：

1. 搜索阶段能找到。
2. 时间范围符合。
3. 主题相关。
4. 内容有商业分析价值。
5. 微信原文链接可访问。

任意一步失败，都会被排除。

### 为什么会卡在验证微信链接？

这一步需要本机 Chrome 打开搜狗跳转链接。如果 Chrome 启动失败、搜狗要求验证、链接已过期或文章被删除，就可能拿不到微信原文链接。

可以稍后重试，或在网页里点“重试验证”。

### MinerU 提示额度用完怎么办？

如果看到：

```text
daily web crawl limit reached max: 100 tasks, submit tomorrow
```

说明 MinerU 当天额度用完。第二天额度恢复后运行：

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

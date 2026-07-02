# 微信公众号文章搜索筛选 + MinerU 批量解析

这个项目在你的电脑本地运行，用来做两件事：

1. 自动搜索、筛选微信公众号文章，并转换成真实 `mp.weixin.qq.com` 链接。
2. 把公众号文章交给 MinerU 解析，生成 Markdown 文件。

搜狗跳转链接依赖本机浏览器复核，所以不建议放到 GitHub Actions 云端运行。每个人跑出来的数据只保存在自己的本地，不会上传到 GitHub。

## 先准备

1. 安装 Python。
2. 安装依赖：

```powershell
pip install -r requirements.txt
```

3. 去 MinerU 获取 Token：

```text
https://mineru.net/apiManage/token
```

4. 设置 Token，推荐用环境变量：

```powershell
$env:MINERU_TOKEN="你的 MinerU Token"
```

也可以在项目目录下创建 `mineru_token.txt`，把 Token 单独放进去。这个文件不会上传到 GitHub。

## AI 用户

适合你把这个仓库链接发给 Codex、Claude、ChatGPT、DeepSeek 等 AI，让 AI 在你的电脑上帮你跑。

### AI 用户：本地研究记忆

第一次用时，让 AI 先帮你建立本地 `research_memory.json`。它会记录你的长期筛选偏好，比如喜欢什么文章、排除什么内容、找不满时怎么处理。

可以这样说：

```text
请先根据我的回答，帮我建立本地 research_memory.json。
以后类似任务默认用于商业分析；优先要案例复盘、行业分析、数据报告；
过滤招聘、课程、资料包和普通新闻快讯；找不满时宁可少给，不要硬凑。
```

这份记忆只保存在你的电脑，不会上传 GitHub。不要把 MinerU Token、一次性研究主题或敏感信息写进去。

### AI 用户：自动模式

你只需要把需求告诉 AI。第一次用时，不需要一次说得很完美，AI 应该先帮你问清楚。

可以这样说：

```text
请使用这个仓库的 SKILL.md，帮我在本地运行自动模式。
我的需求是：2025年至今，找 20 篇 AI 硬件品牌营销案例相关的微信公众号文章。
我已经准备好了 MinerU Token。
```

第一次使用时，AI 通常会先问这些问题里的几项：

- 这次研究最后是用来写报告、做案例库，还是只想快速找资料？
- 你更想要案例复盘、行业分析、数据报告、采访、官方信息，还是都可以？
- 时间范围是否严格？如果符合主题但稍早一点，要不要保留？
- 哪些内容不要？比如招聘、课程、资料包、新闻快讯、低质量转载。
- 找不满数量时，是宁可少给高质量结果，还是允许放宽到背景文章？

之后再用时，你只要说新的主题和数量即可。除非你主动改要求，AI 和程序都会沿用这份本地筛选习惯。

自动模式默认规则：

- 按你的 `research_memory.json` 和本次需求来筛选。
- 如果没有写时间范围，默认看最近一年。
- 如果主题不是明确营销问题，默认用通用筛选，不强行套营销逻辑。
- 如果符合要求的文章不够，宁可少给，也不要拼凑弱相关内容。
- 如果文章已删除、不可查看或没有正文，会自动跳过，不生成无效 Markdown。

### AI 用户：手动模式

如果你已经自己找好了公众号链接，直接把链接发给 AI，并说：

```text
请把这些微信公众号链接写入 urls.txt，然后运行手动模式解析。
```

AI 应该把链接放进 `urls.txt`，每行一个，然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

## 本地用户

适合你自己打开 PowerShell，在项目目录里运行。

### 本地用户：自动模式

最简单命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销 品牌案例 赞助商" -Count 20
```

快速模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销 品牌案例 赞助商" -Count 20 -Mode fast
```

指定时间范围：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销 品牌案例 赞助商" -Count 20 -StartDate "2025-01-01" -EndDate "2026-07-02"
```

只生成 `urls.txt`，先不跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销 品牌案例 赞助商" -Count 20 -OnlyUrls
```

### 本地用户：手动模式

先创建 `urls.txt`，每行放一个微信公众号文章链接：

```text
https://mp.weixin.qq.com/s/xxxx
https://mp.weixin.qq.com/s/yyyy
```

然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

## 输出在哪里

每次 MinerU 解析都会保存到新的运行目录：

```text
runs/
  20260702-120000-urls/
    markdown/
    result.json
    failed_urls.txt
    successful_urls.txt
    summary.md
```

你真正要看的 Markdown 文件在：

```text
runs/某次运行的目录/markdown/
```

如果不知道最新一次是哪一个，看项目根目录里的：

```text
latest_run.txt
```

自动搜索阶段会生成候选清单：

```text
candidates/
```

长期索引保存在：

```text
library/articles_index.csv
```

## 常见问题

如果看到：

```text
daily web crawl limit reached max: 100 tasks, submit tomorrow
```

意思是 MinerU 当天网页抓取额度已经用完了，不是程序坏了。第二天额度恢复后，可以直接跑手动模式继续解析已有的 `urls.txt`：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

如果上一次 MinerU 有失败链接，可以重试失败项：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_retry_failed.ps1
```

如果某篇微信公众号文章已经删除、违规不可查看、没有正文，程序会写进 `failed_urls.txt`，不会放进最终 Markdown。

## 给 AI 的 Skill 文件

这个仓库可以直接作为微信公众号文章筛选 Skill 使用：

```text
SKILL.md
agents/openai.yaml
references/universal-prompt.md
```

- `SKILL.md`：给 Codex 这类 Skill 系统使用。
- `references/universal-prompt.md`：可以复制给 Claude、ChatGPT、DeepSeek 等 AI 使用。

## 本地数据不会上传

这些文件和目录属于个人运行数据，已经被 `.gitignore` 忽略：

- `mineru_token.txt`
- `research_memory.json`
- `urls.txt`
- `runs/`
- `candidates/`
- `outputs/`
- `work/`
- `library/articles_index.csv`

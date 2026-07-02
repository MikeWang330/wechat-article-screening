# 微信公众号文章搜索筛选 + MinerU 批量解析

这个项目只推荐两个入口：

- **自动模式**：输入主题和数量，程序自动找文章、筛选、转换真实公众号链接，并继续跑 MinerU。
- **手动模式**：你已经有公众号链接，放进 `urls.txt`，程序只跑 MinerU。

搜狗跳转链接依赖本机浏览器复核，所以不建议放到 GitHub Actions 云端运行。请克隆到自己的电脑本地使用。每个人跑出来的数据只保存在自己的本地。

## 新手怎么用

最简单的理解方式：

1. 去 MinerU 创建 Token。
2. 把 Token 放到本地电脑。
3. 把你的需求告诉 AI，让 AI 帮你运行自动模式。

## 安装

```powershell
pip install -r requirements.txt
```

## 设置 MinerU Token

先进入 MinerU 的 Token 页面：

```text
https://mineru.net/apiManage/token
```

创建或复制你的 API Token。

推荐用环境变量：

```powershell
$env:MINERU_TOKEN="你的 MinerU Token"
```

也可以在项目目录下创建 `mineru_token.txt`，把 Token 单独放进去。这个文件不会上传到 GitHub。

## 自动模式

如果你准备用 AI 帮你操作这个项目，推荐直接把这个仓库链接给 AI，然后这样说：

```text
请使用这个仓库的 SKILL.md，帮我在本地运行自动模式。
我的需求是：2025年至今，找 20 篇 AI 硬件品牌营销案例相关的微信公众号文章。
我已经准备好了 MinerU Token。
```

AI 会先判断你的需求是否清楚；如果不清楚，会问少量关键问题。确认后，它应该优先给出或直接运行下面这种自动模式命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "AI 硬件 品牌营销案例 2025年至今" -Count 20
```

最简单用法：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销 品牌案例 赞助商" -Count 20
```

自动模式会自己处理默认策略：

- 如果没写时间范围，默认看最近一年。
- 默认使用通用筛选模式，不强行套营销逻辑。
- 默认只保留质量达到 `maybe` 或 `strong` 的文章。
- 默认使用分级相关：优先精确命中；如果主题内容较少，会补充核心实体相关、能帮助理解主题的背景文章。

如果只想先生成 `urls.txt`，不跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销 品牌案例 赞助商" -Count 20 -OnlyUrls
```

如果上一次 MinerU 有失败链接，可以直接重试失败项：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_retry_failed.ps1
```

## 常见提示

如果看到：

```text
daily web crawl limit reached max: 100 tasks, submit tomorrow
```

意思是 MinerU 当天网页抓取额度已经用完了，不是程序坏了。第二天额度恢复后，重新运行即可：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

如果只想继续某一步，也可以用自动模式的阶段参数：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Stage mineru
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Stage retry
```

## 手动模式

先创建 `urls.txt`，每行放一个微信公众号文章链接：

```text
https://mp.weixin.qq.com/s/xxxx
https://mp.weixin.qq.com/s/yyyy
```

然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_manual.ps1
```

## 输出位置

每次 MinerU 解析都会保存到新的运行目录：

```text
runs/
  20260702-120000-urls/
    html/
    markdown/
    zip/
    extract/
    html_manifest.json
    result.json
    failed_urls.txt
    successful_urls.txt
    summary.md
    run_state.json
```

你真正要看的 Markdown 文件在：

```text
runs/某次运行的目录/markdown/
```

例如：

```text
runs/20260702-120000-urls/markdown/
```

如果不知道最新一次是哪一个，看项目根目录里的：

```text
latest_run.txt
```

自动搜索阶段会生成：

```text
candidates/
  *.csv
  *.md
  *-screened-pool.csv
```

长期索引保存在：

```text
library/articles_index.csv
```

这些都是本地运行数据，不会上传到 GitHub。

## 筛选 Skill

这个仓库本身也可以作为一个可复用的微信公众号文章筛选 Skill。

Skill 文件在仓库根目录：

```text
SKILL.md
agents/openai.yaml
references/universal-prompt.md
```

其中：

- `SKILL.md`：给 Codex 这类 Skill 系统使用
- `references/universal-prompt.md`：可以复制给 Claude、ChatGPT、DeepSeek 等 AI 使用

## 本地数据不会上传

这些文件和目录属于个人运行数据，已经被 `.gitignore` 忽略：

- `mineru_token.txt`
- `urls.txt`
- `runs/`
- `candidates/`
- `outputs/`
- `work/`
- `library/articles_index.csv`

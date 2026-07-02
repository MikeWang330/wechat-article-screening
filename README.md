# 微信公众号文章搜索筛选 + MinerU 批量解析

这个项目只有两个推荐入口：

- **自动模式**：你给主题和数量，程序自动找公众号文章、筛选、转换真实链接，然后跑 MinerU。
- **手动模式**：你自己准备 `urls.txt`，程序只负责跑 MinerU。

因为搜狗跳转链接依赖本机浏览器复核，不建议放到 GitHub Actions 云端跑。别人使用这个项目时，应该克隆到自己的电脑本地运行。运行出来的数据也只保存在本地。

## 安装

```powershell
pip install -r requirements.txt
```

## 设置 MinerU Token

推荐用环境变量：

```powershell
$env:MINERU_TOKEN="你的 MinerU Token"
```

也可以在项目目录下创建 `mineru_token.txt`，把 Token 单独放进去。这个文件已被 `.gitignore` 忽略，不会上传。

## 自动模式

适合：用户只知道主题、关键词和想要多少篇文章。

程序会自动完成：

1. 搜索 Sogou WeChat。
2. 筛选候选文章。
3. 用后台浏览器把搜狗跳转链接转换成真实 `mp.weixin.qq.com` 链接。
4. 写入 `urls.txt`。
5. 保存微信公众号文章为本地 HTML。
6. 上传给 MinerU 解析。
7. 下载结果并收集 Markdown。

运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销" -Count 20
```

限定时间范围：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销" -Count 20 -StartDate "2025-01-01" -EndDate "2026-07-02"
```

非营销主题建议使用通用筛选模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "AI 硬件产业链" -Count 20 -Focus general
```

如果只想自动生成 `urls.txt`，暂时不跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "世界杯营销" -Count 20 -OnlyUrls
```

## 手动模式

适合：用户已经自己挑好了公众号文章链接。

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
    html/
    markdown/
    zip/
    extract/
    html_manifest.json
    result.json
    failed_urls.txt
    successful_urls.txt
    summary.md
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

## 不要上传的本地文件

这些文件和目录属于个人运行数据，已经被 `.gitignore` 忽略：

- `mineru_token.txt`
- `urls.txt`
- `runs/`
- `candidates/`
- `outputs/`
- `work/`
- `library/articles_index.csv`

别人克隆这个项目后，运行出来的数据会保存在他们自己的本地目录里。

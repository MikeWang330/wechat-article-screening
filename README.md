# 微信公众号文章搜索筛选 + MinerU 批量解析

这个项目用于把一个研究主题变成可解析的微信公众号文章 Markdown。

完整流程是：

1. 根据主题搜索 Sogou WeChat。
2. 自动筛选候选公众号文章。
3. 在后台浏览器里把搜狗跳转链接转换成真实 `mp.weixin.qq.com` 链接。
4. 把最终链接写入 `urls.txt`。
5. 把微信公众号文章保存成本地 HTML。
6. 使用 MinerU `MinerU-HTML` 模型解析本地 HTML。
7. 下载解析结果，并把 Markdown 文件保存到本地运行目录。

所有运行数据默认只保存在本地。`runs/`、`candidates/`、`outputs/`、`work/`、`urls.txt`、`mineru_token.txt` 等都不会上传到 GitHub。

## 安装依赖

```powershell
pip install -r requirements.txt
```

## 设置 MinerU Token

推荐用环境变量：

```powershell
$env:MINERU_TOKEN="你的 MinerU Token"
```

也可以在项目目录下创建 `mineru_token.txt`，把 Token 单独放进去。这个文件已被 `.gitignore` 忽略，不会上传。

## 一步跑完整流程

搜索、筛选、转换真实公众号链接、写入 `urls.txt`，然后继续跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI 硬件产业链" -Count 20
```

只搜索并准备 `urls.txt`，不跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI 硬件产业链" -Count 20 -SkipMinerU
```

限定时间范围：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "世界杯营销" -Count 20 -StartDate "2025-01-01" -EndDate "2026-07-02"
```

非营销主题建议强制使用通用筛选模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI 硬件产业链" -Count 20 -Focus general
```

## 只做文章搜索和链接转换

生成候选清单和真实公众号链接，但不运行 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "世界杯营销" -Count 20
```

如果只想看候选结果，不想覆盖 `urls.txt`：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "世界杯营销" -Count 20 -NoWriteUrls
```

搜索阶段输出：

- `candidates/*.csv`：最终选中的候选文章列表
- `candidates/*.md`：适合直接阅读的候选表
- `candidates/*-screened-pool.csv`：进入链接转换环节的候选池
- `urls.txt`：最终确认的真实公众号文章链接

## 只跑 MinerU

如果你已经准备好了 `urls.txt`，可以直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_mineru_html_file.ps1
```

或者手动运行：

```powershell
python mineru_batch_wechat.py --urls urls.txt --submit-source html-file
```

Linux/macOS：

```bash
./run.sh
```

## 本地输出结构

每次 MinerU 解析都会保存到一个新的运行目录：

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

长期索引保存在：

```text
library/articles_index.csv
```

这个 CSV 是本地生成的，也不会上传到 GitHub。

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

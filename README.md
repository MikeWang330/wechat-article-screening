# WeChat Article Research + MinerU Parser

This project helps you build a reusable WeChat public-account article workflow:

1. Search Sogou WeChat by topic.
2. Screen candidate articles with a question-led research rubric.
3. Resolve Sogou redirect links into real `mp.weixin.qq.com` URLs.
4. Save final URLs to `urls.txt`.
5. Convert WeChat URLs to local HTML.
6. Upload local HTML files to MinerU `MinerU-HTML`.
7. Download MinerU results and collect Markdown files.

All run data is local by default. Generated folders such as `runs/`, `candidates/`, `outputs/`, `work/`, `urls.txt`, and `mineru_token.txt` are ignored by Git.

## Install

```powershell
pip install -r requirements.txt
```

## MinerU Token

Recommended:

```powershell
$env:MINERU_TOKEN="your MinerU token"
```

Alternative: create a local `mineru_token.txt` file in this project folder. This file is ignored by Git.

## One-Step Workflow

Search, screen, resolve URLs, write `urls.txt`, then run MinerU:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI hardware industry" -Count 20
```

Only search and prepare `urls.txt`, without running MinerU:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI hardware industry" -Count 20 -SkipMinerU
```

With a time range:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "World Cup marketing" -Count 20 -StartDate "2025-01-01" -EndDate "2026-07-02"
```

For non-marketing topics, force general screening:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI hardware supply chain" -Count 20 -Focus general
```

## Research Only

Generate candidates and real WeChat URLs, but do not run MinerU:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "World Cup marketing" -Count 20
```

Do not overwrite `urls.txt`:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "World Cup marketing" -Count 20 -NoWriteUrls
```

Outputs:

- `candidates/*.csv`: final selected candidate list
- `candidates/*.md`: readable candidate table
- `candidates/*-screened-pool.csv`: screened pool before final selection
- `urls.txt`: final verified WeChat article URLs, generated unless `-NoWriteUrls` is used

## MinerU Only

If you already have `urls.txt`, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_mineru_html_file.ps1
```

Or:

```powershell
python mineru_batch_wechat.py --urls urls.txt --submit-source html-file
```

Linux/macOS:

```bash
./run.sh
```

## Local Output Structure

Each MinerU run is saved under `runs/<timestamp>-urls/`:

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

The long-term local index is saved to:

```text
library/articles_index.csv
```

This CSV is generated locally and ignored by Git.

## Included Skill

This repository also works as a reusable screening Skill. The Skill files are at the repository root:

```text
SKILL.md
agents/openai.yaml
references/universal-prompt.md
```

It contains:

- `SKILL.md`: for Codex-style skill systems
- `references/universal-prompt.md`: a portable prompt for Claude, ChatGPT, DeepSeek, and other AI assistants

## Notes

- Keep `mineru_token.txt` local.
- Keep `urls.txt` local because it is user/project data.
- Do not commit generated data from `runs/`, `candidates/`, `outputs/`, or `work/`.

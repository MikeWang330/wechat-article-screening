# Article Library

This folder is the long-term article index for all MinerU runs.

## Files

- `articles_index.csv`: one row per article per run.

## Main Columns

- `run_id`: run folder name under `runs/`
- `data_id`: item id in that run
- `title`: article title extracted from Markdown or local HTML
- `status`: final task status
- `source_url`: original URL from `urls.txt`
- `submitted_url`: URL or local HTML path submitted to MinerU
- `run_dir`: run output directory
- `html_path`: locally saved HTML file
- `markdown_files`: collected Markdown files
- `error`: failure reason, if any


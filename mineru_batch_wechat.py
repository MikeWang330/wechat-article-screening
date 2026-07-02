import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests


SUBMIT_URL = "https://mineru.net/api/v4/extract/task/batch"
FILE_URLS_URL = "https://mineru.net/api/v4/file-urls/batch"
RESULT_URL_TEMPLATE = "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
MODEL_VERSION = "MinerU-HTML"
TOKEN_FILE = "mineru_token.txt"
LIBRARY_DIR = Path("library")
ARTICLE_INDEX_FILE = LIBRARY_DIR / "articles_index.csv"

SUCCESS_STATUSES = {"success", "succeeded", "done", "completed", "complete", "finished", "finish"}
FAILED_STATUSES = {
    "fail",
    "failed",
    "error",
    "errored",
    "exception",
    "timeout",
    "canceled",
    "cancelled",
    "html_failed",
    "html_publish_failed",
    "html_upload_failed",
}
RUNNING_STATUSES = {"pending", "processing", "running", "waiting", "queued", "created", "submitted", "converting"}


@dataclass
class ArticleTask:
    data_id: str
    url: str
    submit_url: str = ""
    status: str = "pending"
    zip_url: str = ""
    error: str = ""
    html_path: str = ""
    html_url: str = ""
    html_status: str = "pending"
    html_error: str = ""
    upload_url: str = ""
    markdown_files: List[str] = field(default_factory=list)

    def mineru_url(self) -> str:
        return self.submit_url or self.url

    def to_json(self) -> Dict[str, Any]:
        return {
            "data_id": self.data_id,
            "source_url": self.url,
            "submitted_url": self.mineru_url(),
            "status": self.status,
            "html_path": self.html_path,
            "html_url": self.html_url,
            "html_status": self.html_status,
            "html_error": self.html_error,
            "upload_url": self.upload_url,
            "full_zip_url": self.zip_url,
            "error": self.error,
            "markdown_files": self.markdown_files,
        }


class MinerUClient:
    def __init__(self, token: str, timeout: int = 60) -> None:
        auth_scheme = os.getenv("MINERU_AUTH_SCHEME", "Bearer").strip()
        auth_value = f"{auth_scheme} {token}" if auth_scheme else token
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "Authorization": auth_value,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "mineru-wechat-batch/1.1",
            }
        )
        self.timeout = timeout

    def submit_batch(self, tasks: List[ArticleTask]) -> str:
        payload = build_submit_payload(tasks)
        response = self.session.post(SUBMIT_URL, json=payload, timeout=self.timeout)
        body = parse_json_response(response)
        batch_id = find_first_key(body, "batch_id")

        if response.ok and batch_id:
            return str(batch_id)

        message = extract_error_message(body) or response.text[:500]
        raise RuntimeError(f"Batch submit failed: HTTP {response.status_code}, message={message}")

    def create_file_upload_batch(self, tasks: List[ArticleTask]) -> str:
        payload = build_file_upload_payload(tasks)
        response = self.session.post(FILE_URLS_URL, json=payload, timeout=self.timeout)
        body = parse_json_response(response)
        batch_id = find_first_key(body, "batch_id")
        file_urls = find_first_key(body, "file_urls")

        if not response.ok or not batch_id:
            message = extract_error_message(body) or response.text[:500]
            raise RuntimeError(f"File URL request failed: HTTP {response.status_code}, message={message}")
        if not isinstance(file_urls, list) or len(file_urls) != len(tasks):
            raise RuntimeError("File URL request did not return one upload URL per task")

        for task, upload_url in zip(tasks, file_urls):
            task.upload_url = str(upload_url)

        return str(batch_id)

    def upload_local_files(self, tasks: List[ArticleTask]) -> None:
        upload_session = requests.Session()
        upload_session.trust_env = False

        for task in tasks:
            if normalize_status(task.status) in FAILED_STATUSES:
                continue
            try:
                html_path = Path(task.html_path)
                if not html_path.exists():
                    raise FileNotFoundError(f"HTML file not found: {html_path}")
                if not task.upload_url:
                    raise RuntimeError("Missing MinerU upload URL")

                with html_path.open("rb") as file_obj:
                    response = upload_session.put(
                        task.upload_url,
                        data=file_obj,
                        timeout=self.timeout,
                    )
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}, {response.text[:300]}")

                task.status = "submitted"
                task.submit_url = str(html_path)
                task.html_status = "uploaded"
            except Exception as exc:
                task.status = "html_upload_failed"
                task.html_status = "upload_failed"
                task.html_error = f"{type(exc).__name__}: {exc}"
                task.error = task.error or f"HTML upload failed: {task.html_error}"

    def fetch_batch_result(self, batch_id: str) -> Dict[str, Any]:
        url = RESULT_URL_TEMPLATE.format(batch_id=batch_id)
        response = self.session.get(url, timeout=self.timeout)
        body = parse_json_response(response)
        if not response.ok:
            raise RuntimeError(f"Batch result query failed: HTTP {response.status_code}, {extract_error_message(body)}")
        return body

    def download(self, url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.session.get(url, stream=True, timeout=self.timeout) as response:
            response.raise_for_status()
            with target.open("wb") as file_obj:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_obj.write(chunk)


def build_submit_payload(tasks: List[ArticleTask]) -> Dict[str, Any]:
    return {
        "model_version": MODEL_VERSION,
        "files": [{"data_id": task.data_id, "url": task.mineru_url()} for task in tasks],
    }


def build_file_upload_payload(tasks: List[ArticleTask]) -> Dict[str, Any]:
    return {
        "model_version": MODEL_VERSION,
        "files": [
            {
                "name": f"{safe_filename(task.data_id)}.html",
                "data_id": task.data_id,
            }
            for task in tasks
        ],
    }


def parse_json_response(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"API did not return JSON: HTTP {response.status_code}, {response.text[:500]}") from exc

    if isinstance(data, dict):
        return data
    return {"data": data}


def find_first_key(value: Any, key: str) -> Optional[Any]:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_first_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first_key(child, key)
            if found is not None:
                return found
    return None


def extract_error_message(value: Any) -> str:
    for key in ("error", "err_msg", "error_msg", "message", "msg", "detail"):
        found = find_first_key(value, key)
        if found:
            return stringify(found)
    return ""


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def read_urls(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"URL file not found: {path}")

    urls = []
    seen = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if line in seen:
            continue
        seen.add(line)
        urls.append(line)
    return urls


def make_tasks(urls: Iterable[str], data_id_prefix: str) -> List[ArticleTask]:
    return [
        ArticleTask(data_id=f"{safe_filename(data_id_prefix)}_{index:03d}", url=url)
        for index, url in enumerate(urls, start=1)
    ]


def prepare_html_files(
    tasks: List[ArticleTask],
    html_dir: Path,
    timeout: int,
    force: bool = False,
) -> None:
    html_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )

    for task in tasks:
        html_path = html_dir / f"{safe_filename(task.data_id)}.html"
        task.html_path = str(html_path)

        if html_path.exists() and html_path.stat().st_size > 0 and not force:
            task.html_status = "cached"
            continue

        print(f"Saving HTML: {task.data_id}", flush=True)
        try:
            response = session.get(task.url, timeout=timeout)
            response.raise_for_status()
            html = response.text
            if not looks_like_html(html):
                raise RuntimeError("Response does not look like HTML")
            html = make_html_local_readable(html)
            html_path.write_text(html, encoding="utf-8")
            task.html_status = "saved"
            task.html_error = ""
        except Exception as exc:
            task.status = "html_failed"
            task.html_status = "failed"
            task.html_error = f"{type(exc).__name__}: {exc}"
            task.error = task.error or f"HTML save failed: {task.html_error}"


def looks_like_html(value: str) -> bool:
    sample = value[:4096].lower()
    return "<html" in sample or "<!doctype html" in sample or "js_content" in sample


def make_html_local_readable(html: str) -> str:
    html = html.replace('href="//', 'href="https://')
    html = html.replace('src="//', 'src="https://')
    html = html.replace("href='//", "href='https://")
    html = html.replace("src='//", "src='https://")
    simplified = simplify_wechat_html(html)
    if simplified:
        return simplified

    style = """
<style id="local-readable-html">
  #js_content {
    visibility: visible !important;
    opacity: 1 !important;
  }
</style>
"""
    if "local-readable-html" in html:
        return html
    if "</head>" in html:
        return html.replace("</head>", f"{style}</head>", 1)
    return style + html


def simplify_wechat_html(html: str) -> str:
    content = extract_element_by_id(html, "js_content")
    if not content:
        return ""

    title = extract_html_title(html)
    content = content.replace("data-src=", "src=")
    content = content.replace("data-original=", "src=")
    content = re.sub(r'\sstyle="[^"]*visibility:\s*hidden;?\s*opacity:\s*0;?[^"]*"', "", content, flags=re.I)
    content = re.sub(r"\sstyle='[^']*visibility:\s*hidden;?\s*opacity:\s*0;?[^']*'", "", content, flags=re.I)

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape_html(title)}</title>
  <style>
    body {{ max-width: 760px; margin: 0 auto; padding: 24px; font-family: Arial, "Microsoft YaHei", sans-serif; line-height: 1.75; }}
    img {{ max-width: 100%; height: auto; }}
    #js_content {{ visibility: visible !important; opacity: 1 !important; }}
  </style>
</head>
<body>
  <h1>{escape_html(title)}</h1>
  {content}
</body>
</html>
"""


def extract_html_title(html: str) -> str:
    patterns = [
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        r'<h1[^>]+id=["\']activity-name["\'][^>]*>(.*?)</h1>',
        r"<title[^>]*>(.*?)</title>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            title = re.sub(r"<[^>]+>", "", match.group(1))
            title = title.replace("&nbsp;", " ")
            return re.sub(r"\s+", " ", title).strip()
    return "WeChat Article"


def extract_element_by_id(html: str, element_id: str) -> str:
    start_match = re.search(
        rf"<(?P<tag>[a-zA-Z][\w:-]*)\b(?=[^>]*\bid=[\"']{re.escape(element_id)}[\"'])[^>]*>",
        html,
        re.I | re.S,
    )
    if not start_match:
        return ""

    tag = start_match.group("tag").lower()
    position = start_match.end()
    depth = 1
    tag_pattern = re.compile(rf"<(?P<close>/)?{re.escape(tag)}\b[^>]*>", re.I | re.S)

    for match in tag_pattern.finditer(html, position):
        if match.group("close"):
            depth -= 1
            if depth == 0:
                return html[start_match.start() : match.end()]
        else:
            depth += 1

    return html[start_match.start() :]


def escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def publish_html_files(
    tasks: List[ArticleTask],
    upload_dir: Path,
    public_base_url: str,
    upload_command: str,
) -> None:
    if upload_command:
        publish_html_with_command(tasks, upload_command)
        return

    if not upload_dir or not public_base_url:
        raise RuntimeError(
            "--submit-source html-url requires either "
            "--html-upload-dir plus --html-public-base-url, or --html-upload-command"
        )

    upload_dir.mkdir(parents=True, exist_ok=True)
    base_url = public_base_url.rstrip("/")

    for task in tasks:
        if normalize_status(task.status) in FAILED_STATUSES:
            continue
        try:
            source_path = Path(task.html_path)
            if not source_path.exists():
                raise FileNotFoundError(f"HTML file not found: {source_path}")
            remote_name = f"{safe_filename(task.data_id)}.html"
            target_path = upload_dir / remote_name
            shutil.copy2(source_path, target_path)
            task.html_url = f"{base_url}/{quote(remote_name)}"
            task.submit_url = task.html_url
            task.html_status = "published"
        except Exception as exc:
            task.status = "html_publish_failed"
            task.html_status = "publish_failed"
            task.html_error = f"{type(exc).__name__}: {exc}"
            task.error = task.error or f"HTML publish failed: {task.html_error}"


def publish_html_with_command(tasks: List[ArticleTask], upload_command: str) -> None:
    for task in tasks:
        if normalize_status(task.status) in FAILED_STATUSES:
            continue
        try:
            html_path = Path(task.html_path)
            if not html_path.exists():
                raise FileNotFoundError(f"HTML file not found: {html_path}")

            remote_name = f"{safe_filename(task.data_id)}.html"
            command = upload_command.format(
                data_id=task.data_id,
                html_path=str(html_path),
                html_path_posix=html_path.as_posix(),
                remote_name=remote_name,
            )
            completed = subprocess.run(
                command,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
            )
            html_url = extract_first_url(completed.stdout)
            if not html_url:
                raise RuntimeError("Upload command did not print a public URL")

            task.html_url = html_url
            task.submit_url = html_url
            task.html_status = "published"
        except Exception as exc:
            task.status = "html_publish_failed"
            task.html_status = "publish_failed"
            task.html_error = f"{type(exc).__name__}: {exc}"
            task.error = task.error or f"HTML publish failed: {task.html_error}"


def extract_first_url(value: str) -> str:
    for line in value.splitlines():
        text = line.strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
    return ""


def poll_until_finished(
    client: MinerUClient,
    batch_id: str,
    tasks: List[ArticleTask],
    interval: int,
    max_wait: int,
) -> Dict[str, Any]:
    started_at = time.monotonic()
    raw_result: Dict[str, Any] = {}

    while True:
        raw_result = client.fetch_batch_result(batch_id)
        merge_result(tasks, raw_result)

        print(f"Progress: {summarize_statuses(tasks)}", flush=True)

        if all(is_terminal(task.status) for task in tasks):
            return raw_result

        batch_status = get_batch_status(raw_result)
        if batch_status in SUCCESS_STATUSES:
            mark_unfinished_as_failed(tasks, "Batch finished but this URL did not return a result")
            return raw_result
        if batch_status in FAILED_STATUSES:
            mark_unfinished_as_failed(tasks, f"Batch state is {batch_status}")
            return raw_result

        elapsed = time.monotonic() - started_at
        if elapsed >= max_wait:
            mark_unfinished_as_failed(tasks, f"Polling timed out after {int(elapsed)} seconds")
            return raw_result

        time.sleep(interval)


def merge_result(tasks: List[ArticleTask], raw_result: Dict[str, Any]) -> None:
    task_by_id = {task.data_id: task for task in tasks}
    task_by_url = {task.url: task for task in tasks}
    task_by_submit_url = {task.mineru_url(): task for task in tasks}

    for item in iter_result_items(raw_result):
        if not isinstance(item, dict):
            continue

        data_id = first_value(item, "data_id", "id", "task_id")
        url = first_value(item, "url", "source_url", "file_url")
        task = task_by_id.get(str(data_id)) if data_id else None
        if task is None and url:
            task = task_by_url.get(str(url))
        if task is None and url:
            task = task_by_submit_url.get(str(url))
        if task is None:
            continue

        status = normalize_status(first_value(item, "status", "state", "task_status"))
        if status:
            task.status = status

        zip_url = first_value(item, "full_zip_url", "zip_url", "result_zip_url", "download_url")
        if zip_url:
            task.zip_url = str(zip_url)

        error = extract_error_message(item)
        if error:
            task.error = error

        if task.zip_url and task.status in RUNNING_STATUSES:
            task.status = "success"


def get_batch_status(raw_result: Dict[str, Any]) -> str:
    status = first_value(raw_result, "status", "state", "batch_status")
    data = raw_result.get("data")
    if not status and isinstance(data, dict):
        status = first_value(data, "status", "state", "batch_status")
    return normalize_status(status)


def iter_result_items(raw_result: Any) -> Iterable[Any]:
    if isinstance(raw_result, list):
        yield from raw_result
        return

    if not isinstance(raw_result, dict):
        return

    for key in ("results", "extract_result", "extract_results", "task_results", "items", "list", "data"):
        value = raw_result.get(key)
        if isinstance(value, list):
            yield from value
        elif isinstance(value, dict):
            yield from iter_result_items(value)


def first_value(mapping: Dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def normalize_status(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    status_aliases = {"1": "success", "2": "failed", "3": "processing", "true": "success", "false": "failed"}
    return status_aliases.get(text, text)


def is_terminal(status: str) -> bool:
    normalized = normalize_status(status)
    return normalized in SUCCESS_STATUSES or normalized in FAILED_STATUSES


def mark_unfinished_as_failed(tasks: List[ArticleTask], message: str) -> None:
    for task in tasks:
        if not is_terminal(task.status):
            task.status = "failed"
            task.error = task.error or message


def summarize_statuses(tasks: List[ArticleTask]) -> str:
    counts: Dict[str, int] = {}
    for task in tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


def download_and_collect_markdown(
    client: MinerUClient,
    tasks: List[ArticleTask],
    zip_dir: Path,
    extract_dir: Path,
    run_markdown_dir: Path,
) -> None:
    zip_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    run_markdown_dir.mkdir(parents=True, exist_ok=True)

    for task in tasks:
        if normalize_status(task.status) not in SUCCESS_STATUSES:
            continue
        if not task.zip_url:
            task.status = "failed"
            task.error = task.error or "Task succeeded but full_zip_url is missing"
            continue

        try:
            zip_path = zip_dir / f"{safe_filename(task.data_id)}.zip"
            task_extract_dir = extract_dir / safe_filename(task.data_id)
            task_extract_dir.mkdir(parents=True, exist_ok=True)

            print(f"Downloading: {task.data_id}", flush=True)
            client.download(task.zip_url, zip_path)
            extract_zip_safely(zip_path, task_extract_dir)

            copied = copy_markdown_files(task_extract_dir, run_markdown_dir, task.data_id)
            task.markdown_files = [str(path) for path in copied]

            if not copied:
                task.status = "failed"
                task.error = task.error or "No Markdown file found in zip"
        except Exception as exc:
            task.status = "failed"
            task.error = f"Download or extract failed: {type(exc).__name__}: {exc}"


def extract_zip_safely(zip_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            destination = (target_root / member.filename).resolve()
            try:
                destination.relative_to(target_root)
            except ValueError as exc:
                raise RuntimeError(f"Zip contains unsafe path: {member.filename}") from exc
            archive.extract(member, target_root)


def copy_markdown_files(source_dir: Path, markdown_dir: Path, data_id: str) -> List[Path]:
    copied = []
    for markdown_file in source_dir.rglob("*"):
        if not markdown_file.is_file() or markdown_file.suffix.lower() not in {".md", ".markdown"}:
            continue

        relative_name = "__".join(markdown_file.relative_to(source_dir).parts)
        title = extract_markdown_title(markdown_file)
        name_part = safe_filename(title) if title else safe_filename(relative_name)
        target_name = f"{safe_filename(data_id)}__{truncate_filename(name_part, 90)}.md"
        target_path = unique_path(markdown_dir / target_name)
        shutil.copy2(markdown_file, target_path)
        copied.append(target_path)
    return copied


def extract_markdown_title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:120]:
            text = line.strip()
            if text.startswith("# "):
                return text[2:].strip()
    except OSError:
        return ""
    return ""


def truncate_filename(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[:max_length].rstrip("._- ") or "file"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def safe_filename(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("_")
    name = "".join(safe).strip("._")
    return name or "file"


def default_run_dir(urls_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = safe_filename(urls_path.stem)
    return Path("runs") / f"{timestamp}-{name}"


def write_outputs(
    tasks: List[ArticleTask],
    batch_results: List[Dict[str, Any]],
    run_dir: Path,
    urls_path: Path,
    submit_source: str,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)

    result_payload = {
        "model_version": MODEL_VERSION,
        "source_urls_file": str(urls_path),
        "submit_source": submit_source,
        "batch_results": batch_results,
        "items": [task.to_json() for task in tasks],
    }
    (run_dir / "result.json").write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "html_manifest.json").write_text(
        json.dumps([task.to_json() for task in tasks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failed_urls = [task.url for task in tasks if normalize_status(task.status) in FAILED_STATUSES]
    (run_dir / "failed_urls.txt").write_text("\n".join(failed_urls) + ("\n" if failed_urls else ""), encoding="utf-8")

    if submit_source == "html-only":
        successful_urls = [task.url for task in tasks if normalize_status(task.status) not in FAILED_STATUSES]
    else:
        successful_urls = [task.url for task in tasks if normalize_status(task.status) in SUCCESS_STATUSES]
    (run_dir / "successful_urls.txt").write_text(
        "\n".join(successful_urls) + ("\n" if successful_urls else ""),
        encoding="utf-8",
    )
    write_run_summary(tasks, batch_results, run_dir, urls_path, submit_source)
    write_run_state(tasks, batch_results, run_dir, urls_path, submit_source)
    update_article_index(tasks, run_dir, urls_path, submit_source)


def write_run_state(
    tasks: List[ArticleTask],
    batch_results: List[Dict[str, Any]],
    run_dir: Path,
    urls_path: Path,
    submit_source: str,
) -> None:
    total = len(tasks)
    success_count = sum(1 for task in tasks if normalize_status(task.status) in SUCCESS_STATUSES)
    failed_count = sum(1 for task in tasks if normalize_status(task.status) in FAILED_STATUSES)
    pending_count = total - success_count - failed_count
    markdown_count = sum(len(task.markdown_files) for task in tasks)
    failed_urls_path = run_dir / "failed_urls.txt"

    if failed_count:
        next_action = "retry_failed"
    elif pending_count:
        next_action = "inspect_pending"
    else:
        next_action = "done"

    payload = {
        "run_id": run_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_urls_file": str(urls_path),
        "submit_source": submit_source,
        "model_version": MODEL_VERSION,
        "total_urls": total,
        "mineru_success_count": success_count,
        "mineru_failed_count": failed_count,
        "pending_count": pending_count,
        "markdown_file_count": markdown_count,
        "batch_count": len(batch_results),
        "batch_ids": [batch.get("batch_id", "") for batch in batch_results if batch.get("batch_id")],
        "run_dir": str(run_dir),
        "markdown_dir": str(run_dir / "markdown"),
        "result_json": str(run_dir / "result.json"),
        "failed_urls_file": str(failed_urls_path),
        "next_action": next_action,
    }
    (run_dir / "run_state.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_run_summary(
    tasks: List[ArticleTask],
    batch_results: List[Dict[str, Any]],
    run_dir: Path,
    urls_path: Path,
    submit_source: str,
) -> None:
    run_id = run_dir.name
    total = len(tasks)
    success = [task for task in tasks if normalize_status(task.status) in SUCCESS_STATUSES]
    failed = [task for task in tasks if normalize_status(task.status) in FAILED_STATUSES]
    pending = [task for task in tasks if normalize_status(task.status) not in SUCCESS_STATUSES | FAILED_STATUSES]
    markdown_files = [path for task in tasks for path in task.markdown_files]

    lines = [
        f"# Run Summary: {run_id}",
        "",
        f"- Created at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Source URL file: `{urls_path}`",
        f"- Submit source: `{submit_source}`",
        f"- Total URLs: {total}",
        f"- Success: {len(success)}",
        f"- Failed: {len(failed)}",
        f"- Pending/unfinished: {len(pending)}",
        f"- Markdown files: {len(markdown_files)}",
        "",
        "## Output Paths",
        "",
        f"- Markdown: `{run_dir / 'markdown'}`",
        f"- HTML: `{run_dir / 'html'}`",
        f"- Result JSON: `{run_dir / 'result.json'}`",
        f"- Run State: `{run_dir / 'run_state.json'}`",
        f"- Failed URLs: `{run_dir / 'failed_urls.txt'}`",
        f"- Successful URLs: `{run_dir / 'successful_urls.txt'}`",
        "",
        "## Batch Results",
        "",
    ]

    if batch_results:
        lines.append("| Batch | Batch ID | Tasks | Error |")
        lines.append("|---|---|---:|---|")
        for batch in batch_results:
            error = str(batch.get("error", "")).replace("|", "/")
            lines.append(
                f"| {batch.get('batch_name', '')} | {batch.get('batch_id', '')} | "
                f"{batch.get('task_count', 0)} | {error} |"
            )
    else:
        lines.append("No MinerU batch was submitted.")

    lines.extend(["", "## Markdown Files", ""])
    if markdown_files:
        lines.append("| Data ID | Title | File |")
        lines.append("|---|---|---|")
        for task in tasks:
            for markdown_file in task.markdown_files:
                title = extract_markdown_title(Path(markdown_file)) or task.data_id
                lines.append(
                    f"| {task.data_id} | {title.replace('|', '/')} | `{markdown_file}` |"
                )
    else:
        lines.append("No Markdown files have been collected yet.")

    lines.extend(["", "## Failed Items", ""])
    if failed:
        lines.append("| Data ID | Status | Error | URL |")
        lines.append("|---|---|---|---|")
        for task in failed:
            error = (task.error or task.html_error).replace("|", "/")
            lines.append(f"| {task.data_id} | {task.status} | {error} | {task.url} |")
    else:
        lines.append("No failed items.")

    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def update_article_index(
    tasks: List[ArticleTask],
    run_dir: Path,
    urls_path: Path,
    submit_source: str,
) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_id",
        "data_id",
        "title",
        "status",
        "source_url",
        "submitted_url",
        "submit_source",
        "source_urls_file",
        "run_dir",
        "html_path",
        "markdown_files",
        "full_zip_url",
        "error",
        "updated_at",
    ]

    rows_by_key: Dict[str, Dict[str, str]] = {}
    if ARTICLE_INDEX_FILE.exists():
        with ARTICLE_INDEX_FILE.open("r", encoding="utf-8-sig", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                key = make_index_key(row.get("run_id", ""), row.get("data_id", ""))
                if key:
                    rows_by_key[key] = {name: row.get(name, "") for name in fieldnames}

    updated_at = datetime.now().isoformat(timespec="seconds")
    for task in tasks:
        key = make_index_key(run_dir.name, task.data_id)
        rows_by_key[key] = {
            "run_id": run_dir.name,
            "data_id": task.data_id,
            "title": task_title(task),
            "status": task.status,
            "source_url": task.url,
            "submitted_url": task.mineru_url(),
            "submit_source": submit_source,
            "source_urls_file": str(urls_path),
            "run_dir": str(run_dir),
            "html_path": task.html_path,
            "markdown_files": ";".join(task.markdown_files),
            "full_zip_url": task.zip_url,
            "error": task.error or task.html_error,
            "updated_at": updated_at,
        }

    rows = sorted(rows_by_key.values(), key=lambda row: (row["run_id"], row["data_id"]))
    with ARTICLE_INDEX_FILE.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_index_key(run_id: str, data_id: str) -> str:
    if not run_id or not data_id:
        return ""
    return f"{run_id}::{data_id}"


def task_title(task: ArticleTask) -> str:
    for markdown_file in task.markdown_files:
        title = extract_markdown_title(Path(markdown_file))
        if title:
            return title
    html_title = extract_title_from_html_path(task.html_path)
    return html_title or task.data_id


def extract_title_from_html_path(html_path: str) -> str:
    if not html_path:
        return ""
    path = Path(html_path)
    if not path.exists():
        return ""
    try:
        return extract_html_title(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def write_latest_pointer(run_dir: Path) -> None:
    Path("latest_run.txt").write_text(str(run_dir), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch parse WeChat article URLs with MinerU.")
    parser.add_argument("--urls", default="urls.txt", help="URL list file. Default: urls.txt")
    parser.add_argument("--output-dir", default="", help="Run output directory. Default: runs/<timestamp>-<urls-file>")
    parser.add_argument("--data-id-prefix", default="", help="Prefix for MinerU data_id. Default: URL file name.")
    parser.add_argument("--poll-interval", type=int, default=15, help="Polling interval in seconds. Default: 15")
    parser.add_argument("--max-wait", type=int, default=3600, help="Max polling wait in seconds. Default: 3600")
    parser.add_argument("--timeout", type=int, default=60, help="Single request timeout in seconds. Default: 60")
    parser.add_argument(
        "--prepare-html",
        action="store_true",
        help="Save each WeChat article as local HTML before submitting to MinerU.",
    )
    parser.add_argument(
        "--force-html",
        action="store_true",
        help="Re-download HTML even when a cached HTML file already exists.",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only save local HTML files and write manifests; do not submit to MinerU.",
    )
    parser.add_argument(
        "--submit-source",
        choices=("wechat-url", "html-url", "html-file"),
        default="wechat-url",
        help=(
            "Submit original WeChat URLs, published HTML URLs, or local HTML files "
            "uploaded through MinerU file URLs. Default: wechat-url"
        ),
    )
    parser.add_argument(
        "--html-upload-dir",
        default="",
        help="Directory mapped to a public static URL. Used with --html-public-base-url.",
    )
    parser.add_argument(
        "--html-public-base-url",
        default="",
        help="Public base URL for files copied to --html-upload-dir.",
    )
    parser.add_argument(
        "--html-upload-command",
        default="",
        help=(
            "Custom upload command template. It may use {html_path}, {html_path_posix}, "
            "{remote_name}, {data_id}; stdout must print the public URL."
        ),
    )
    return parser.parse_args()


def load_token() -> str:
    env_token = os.getenv("MINERU_TOKEN", "").strip()
    if env_token:
        return env_token

    token_path = Path(TOKEN_FILE)
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()

    return ""


def main() -> int:
    args = parse_args()
    urls_path = Path(args.urls)
    run_dir = Path(args.output_dir) if args.output_dir else default_run_dir(urls_path)
    data_id_prefix = args.data_id_prefix or urls_path.stem

    try:
        urls = read_urls(urls_path)
        if not urls:
            raise RuntimeError(f"No usable URLs found in {urls_path}")

        tasks = make_tasks(urls, data_id_prefix=data_id_prefix)

        if args.submit_source == "html-url" and not args.html_upload_command:
            if not args.html_upload_dir or not args.html_public_base_url:
                raise RuntimeError(
                    "--submit-source html-url requires --html-upload-dir plus "
                    "--html-public-base-url, or --html-upload-command"
                )

        if args.prepare_html or args.html_only or args.submit_source in {"html-url", "html-file"}:
            print("Preparing local HTML files...", flush=True)
            prepare_html_files(
                tasks=tasks,
                html_dir=run_dir / "html",
                timeout=args.timeout,
                force=args.force_html,
            )

        if args.html_only:
            write_outputs(tasks, [], run_dir, urls_path, "html-only")
            write_latest_pointer(run_dir)
            failed_count = sum(1 for task in tasks if normalize_status(task.status) in FAILED_STATUSES)
            print(f"Done. HTML saved={len(tasks) - failed_count}, Failed={failed_count}", flush=True)
            print(f"Run HTML: {run_dir / 'html'}", flush=True)
            print(f"HTML manifest: {run_dir / 'html_manifest.json'}", flush=True)
            return 0

        if args.submit_source == "html-url":
            print("Publishing HTML files...", flush=True)
            publish_html_files(
                tasks=tasks,
                upload_dir=Path(args.html_upload_dir) if args.html_upload_dir else Path(),
                public_base_url=args.html_public_base_url,
                upload_command=args.html_upload_command,
            )

        mineru_tasks = [task for task in tasks if normalize_status(task.status) not in FAILED_STATUSES]
        if not mineru_tasks:
            write_outputs(tasks, [], run_dir, urls_path, args.submit_source)
            write_latest_pointer(run_dir)
            raise RuntimeError("No tasks can be submitted to MinerU")

        token = load_token()
        if not token:
            print(f"Error: please set MINERU_TOKEN or create {TOKEN_FILE}.", file=sys.stderr)
            return 2

        client = MinerUClient(token=token, timeout=args.timeout)

        print(f"URLs: {len(tasks)}", flush=True)
        print(f"Run directory: {run_dir}", flush=True)
        print(f"Submit source: {args.submit_source}", flush=True)

        batch_results: List[Dict[str, Any]] = []
        batch_name = "batch_001"
        batch_tasks = mineru_tasks
        print(f"{batch_name}: submitting {len(batch_tasks)} tasks", flush=True)

        try:
            if args.submit_source == "html-file":
                batch_id = client.create_file_upload_batch(batch_tasks)
                print(f"{batch_name}: upload URLs ready. batch_id={batch_id}", flush=True)
                client.upload_local_files(batch_tasks)
                upload_failed = [
                    task for task in batch_tasks if normalize_status(task.status) in FAILED_STATUSES
                ]
                if len(upload_failed) == len(batch_tasks):
                    raise RuntimeError("All local HTML uploads failed")
                print(f"{batch_name}: uploaded local HTML files", flush=True)
            else:
                batch_id = client.submit_batch(batch_tasks)
                print(f"{batch_name}: submitted. batch_id={batch_id}", flush=True)

            raw_result = poll_until_finished(
                client=client,
                batch_id=batch_id,
                tasks=batch_tasks,
                interval=args.poll_interval,
                max_wait=args.max_wait,
            )

            download_and_collect_markdown(
                client=client,
                tasks=batch_tasks,
                zip_dir=run_dir / "zip" / batch_name,
                extract_dir=run_dir / "extract" / batch_name,
                run_markdown_dir=run_dir / "markdown",
            )

            batch_results.append(
                {
                    "batch_name": batch_name,
                    "batch_id": batch_id,
                    "task_count": len(batch_tasks),
                    "data_ids": [task.data_id for task in batch_tasks],
                    "raw_result": raw_result,
                }
            )
        except Exception as exc:
            message = f"{batch_name} failed: {type(exc).__name__}: {exc}"
            print(message, file=sys.stderr, flush=True)
            mark_unfinished_as_failed(batch_tasks, message)
            batch_results.append(
                {
                    "batch_name": batch_name,
                    "batch_id": "",
                    "task_count": len(batch_tasks),
                    "data_ids": [task.data_id for task in batch_tasks],
                    "error": message,
                    "raw_result": {},
                }
            )

        write_outputs(tasks, batch_results, run_dir, urls_path, args.submit_source)
        write_latest_pointer(run_dir)

        failed_count = sum(1 for task in tasks if normalize_status(task.status) in FAILED_STATUSES)
        print(f"Done. Success={len(tasks) - failed_count}, Failed={failed_count}", flush=True)
        print(f"Run Markdown: {run_dir / 'markdown'}", flush=True)
        print(f"Result JSON: {run_dir / 'result.json'}", flush=True)
        print(f"Failed URLs: {run_dir / 'failed_urls.txt'}", flush=True)
        return 0
    except Exception as exc:
        print(f"Run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

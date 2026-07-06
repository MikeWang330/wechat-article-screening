#!/usr/bin/env python3
"""Local web console for WeChat article screening."""

from __future__ import annotations

import json
import os
import re
import csv
import queue
import datetime as dt
import subprocess
import threading
import time
import uuid
import urllib.parse
import urllib.error
import urllib.request
import socket
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WORK_DIR = ROOT / "work"
JOBS: dict[str, "Job"] = {}
JOBS_LOCK = threading.Lock()
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))
JOB_SEMAPHORE = threading.Semaphore(max(1, MAX_CONCURRENT_JOBS))
PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
)
DEAD_PROXY_VALUES = {
    "http://127.0.0.1:9",
    "https://127.0.0.1:9",
    "127.0.0.1:9",
}


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>微信研究工作台</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f5;
      --panel: #ffffff;
      --panel-soft: #f1f5f2;
      --text: #17211f;
      --muted: #69746f;
      --line: #dbe2dd;
      --line-strong: #c9d4ce;
      --accent: #0d7568;
      --accent-dark: #07584f;
      --accent-soft: #e8f5f1;
      --ok: #08714f;
      --warn: #9b6200;
      --bad: #aa2f35;
      --shadow: 0 14px 38px rgba(22, 36, 32, 0.08);
      --shadow-soft: 0 8px 22px rgba(22, 36, 32, 0.06);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-width: 0;
      background:
        linear-gradient(180deg, #eef4f1 0, #f6f7f5 340px),
        var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }
    button, input, select, textarea { font: inherit; }
    .shell {
      min-height: 100vh;
    }
    nav {
      position: sticky;
      top: 0;
      z-index: 20;
      height: 68px;
      display: grid;
      grid-template-columns: minmax(220px, auto) 1fr auto;
      align-items: center;
      gap: 22px;
      padding: 0 32px;
      background: rgba(255, 255, 255, 0.88);
      border-bottom: 1px solid rgba(201, 212, 206, 0.8);
      backdrop-filter: blur(18px);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .mark {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: #10221f;
      color: #dff5ed;
      font-weight: 800;
      box-shadow: inset 0 -1px 0 rgba(255,255,255,0.14);
    }
    h1, h2 {
      margin: 0;
      font-weight: 760;
      letter-spacing: 0;
    }
    h1 { font-size: 16px; }
    h2 { font-size: 28px; line-height: 1.15; }
    .nav-buttons {
      display: flex;
      justify-content: center;
      gap: 8px;
    }
    .nav-button {
      min-height: 36px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--muted);
      border-radius: 8px;
      padding: 0 13px;
      font-weight: 700;
    }
    .nav-button.active {
      color: var(--accent-dark);
      background: var(--accent-soft);
      border-color: #c3ded7;
    }
    .footer-note {
      color: var(--muted);
      line-height: 1.5;
      font-size: 12px;
      white-space: nowrap;
    }
    .main {
      min-width: 0;
      width: 100%;
      max-width: 1480px;
      margin: 0 auto;
      padding: 26px 32px 42px;
    }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: start;
      margin-bottom: 20px;
    }
    .subtitle {
      margin-top: 7px;
      color: var(--muted);
      line-height: 1.6;
    }
    .page { display: none; }
    .page.active { display: block; }
    .layout {
      display: grid;
      grid-template-columns: minmax(360px, 430px) minmax(560px, 1fr);
      gap: 18px;
      align-items: start;
    }
    .history-toggle {
      position: fixed;
      left: 0;
      top: 112px;
      z-index: 45;
      min-height: 96px;
      width: 40px;
      border-radius: 0 8px 8px 0;
      padding: 0;
      writing-mode: vertical-rl;
      letter-spacing: 0;
      box-shadow: var(--shadow-soft);
    }
    .panel,
    .history-panel,
    .statusbar,
    .summary,
    .progress-panel {
      background: rgba(255,255,255,0.94);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow-soft);
    }
    .history-panel {
      position: fixed;
      left: 0;
      top: 86px;
      bottom: 22px;
      z-index: 44;
      width: min(330px, calc(100vw - 56px));
      display: grid;
      grid-template-rows: auto 1fr;
      gap: 12px;
      min-width: 0;
      padding: 16px;
      transform: translateX(calc(-100% - 10px));
      transition: transform 0.22s ease, box-shadow 0.22s ease;
    }
    .history-panel.open {
      transform: translateX(52px);
      box-shadow: var(--shadow);
    }
    .history-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }
    .history-title {
      color: var(--text);
      font-size: 15px;
      font-weight: 780;
      line-height: 1.3;
    }
    .history-subtitle {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .history-list {
      display: grid;
      align-content: start;
      gap: 8px;
      min-height: 0;
      overflow: auto;
      padding: 1px 2px 1px 1px;
    }
    .history-item {
      width: 100%;
      min-height: 122px;
      display: grid;
      align-content: start;
      gap: 9px;
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 16px 14px 14px;
      background: #f8faf8;
      color: var(--text);
      text-align: left;
      transition: transform 0.16s ease, background 0.16s ease, border-color 0.16s ease;
    }
    .history-item:hover {
      transform: translateY(-1px);
      background: #f0f7f4;
      border-color: #c7ded7;
    }
    .history-item.active {
      border-color: #86c5b6;
      background: #e9f6f2;
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .history-name {
      font-size: 15px;
      font-weight: 760;
      line-height: 24px;
      min-height: 26px;
      padding-top: 2px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .history-meta {
      width: fit-content;
      max-width: 100%;
      padding: 3px 8px;
      border-radius: 999px;
      background: #eef3ef;
      color: #65736d;
      font-size: 11px;
      line-height: 1.35;
      font-weight: 650;
    }
    .history-summary {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 1px;
    }
    .history-stat {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 6px;
      background: #fff;
      border: 1px solid #dbe5df;
      color: #3d4e47;
      font-size: 12px;
      font-weight: 720;
    }
    .history-empty {
      padding: 12px;
      border: 1px dashed var(--line-strong);
      border-radius: 8px;
      color: var(--muted);
      background: #fbfcfb;
      line-height: 1.6;
    }
    .panel {
      padding: 20px;
    }
    .panel-title {
      display: flex;
      align-items: center;
      min-height: 26px;
      font-size: 15px;
      font-weight: 780;
      margin-bottom: 14px;
    }
    label {
      display: block;
      margin: 15px 0 6px;
      font-weight: 700;
      color: #263430;
      font-size: 13px;
    }
    input, select, textarea {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 9px 11px;
      color: var(--text);
      background: #fff;
      outline: none;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    input:focus, select:focus, textarea:focus {
      border-color: #78b9ac;
      box-shadow: 0 0 0 4px rgba(13,117,104,0.1);
    }
    textarea { min-height: 126px; resize: vertical; }
    .custom-date { display: none; }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .intensity-control {
      display: grid;
      gap: 12px;
      margin-top: 8px;
      padding: 15px 16px 14px;
      border: 1px solid rgba(169, 190, 184, 0.56);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(247,250,248,0.94));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.75), 0 10px 24px rgba(28, 45, 41, 0.06);
    }
    .intensity-readout {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
    }
    .intensity-current {
      color: var(--text);
      font-size: 17px;
      font-weight: 800;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .intensity-limit {
      display: inline-flex;
      align-items: center;
      min-height: 25px;
      padding: 0 10px;
      border-radius: 999px;
      background: rgba(13,117,104,0.08);
      color: #0c6f63;
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
    }
    .intensity-slider-shell {
      position: relative;
      padding: 3px 0 1px;
    }
    .intensity-range {
      width: 100%;
      min-height: 28px;
      padding: 0;
      border: 0;
      background: transparent;
      accent-color: var(--accent);
      cursor: pointer;
      -webkit-appearance: none;
      appearance: none;
    }
    .intensity-range:focus {
      box-shadow: none;
    }
    .intensity-range::-webkit-slider-runnable-track {
      height: 6px;
      border-radius: 999px;
      background: linear-gradient(
        90deg,
        #0e7a6c 0%,
        #0e7a6c var(--intensity-position, 60%),
        #e2e9e6 var(--intensity-position, 60%),
        #e2e9e6 100%
      );
    }
    .intensity-range::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 21px;
      height: 21px;
      margin-top: -7.5px;
      border: 1px solid rgba(40, 64, 59, 0.12);
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 2px 6px rgba(17, 34, 31, 0.18), 0 5px 14px rgba(17, 34, 31, 0.12);
    }
    .intensity-range::-moz-range-track {
      height: 6px;
      border-radius: 999px;
      background: #e2e9e6;
    }
    .intensity-range::-moz-range-progress {
      height: 6px;
      border-radius: 999px;
      background: #0e7a6c;
    }
    .intensity-range::-moz-range-thumb {
      width: 19px;
      height: 19px;
      border: 1px solid rgba(40, 64, 59, 0.12);
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 2px 6px rgba(17, 34, 31, 0.18), 0 5px 14px rgba(17, 34, 31, 0.12);
    }
    .intensity-scale {
      position: relative;
      height: 18px;
      margin-top: -2px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.2;
      font-variant-numeric: tabular-nums;
      font-feature-settings: "tnum";
    }
    .intensity-scale span {
      position: absolute;
      top: 0;
      left: var(--tick-left);
      width: 34px;
      margin-left: -17px;
      text-align: center;
    }
    .intensity-scale .active {
      color: #0b6f63;
      font-weight: 800;
    }
    .intensity-desc {
      color: #687771;
      font-size: 12px;
      line-height: 1.6;
    }
    .check {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 14px;
      color: var(--text);
      font-weight: 600;
    }
    .check input {
      width: 16px;
      min-height: 16px;
    }
    .setting-intro {
      display: grid;
      gap: 10px;
      margin: 4px 0 16px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfb;
    }
    .setting-intro .hint {
      margin-top: 0;
      line-height: 1.7;
    }
    .setting-intro button {
      width: fit-content;
    }
    button {
      min-height: 40px;
      border: 1px solid var(--accent);
      border-radius: 8px;
      padding: 0 14px;
      background: var(--accent);
      color: #fff;
      font-weight: 720;
      cursor: pointer;
      transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease;
    }
    button:hover { background: var(--accent-dark); transform: translateY(-1px); }
    button.secondary {
      background: #fff;
      color: var(--accent-dark);
      border-color: #a9cec5;
    }
    button.secondary:hover {
      background: #f1f8f5;
    }
    button.danger {
      border-color: #d7a0a4;
      background: #fff;
      color: #a72f36;
    }
    button.danger:hover {
      background: #fff2f2;
      border-color: #bd6970;
    }
    .actions {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 22px;
    }
    .actions button {
      width: 100%;
      padding: 0 10px;
    }
    .run-column {
      min-width: 0;
      display: grid;
      gap: 12px;
    }
    .statusbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 64px;
      padding: 14px 16px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 8px;
      padding: 0 10px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .pill.running { color: var(--warn); border-color: #dfc17b; background: #fff9e8; }
    .pill.done { color: var(--ok); border-color: #99d6bf; background: #effaf5; }
    .pill.failed { color: var(--bad); border-color: #e0a4a4; background: #fff1f1; }
    .pill.canceled { color: var(--bad); border-color: #e0a4a4; background: #fff1f1; }
    .summary {
      padding: 13px 16px;
      color: var(--muted);
      line-height: 1.6;
    }
    .progress-panel {
      position: relative;
      min-height: 540px;
      padding: 20px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }
    .progress-panel.is-complete,
    .progress-panel.is-idle {
      min-height: 0;
    }
    .progress-panel::before {
      content: "";
      position: absolute;
      inset: 0;
      height: 116px;
      background:
        repeating-linear-gradient(90deg, rgba(13,117,104,0.08) 0 1px, transparent 1px 34px),
        linear-gradient(180deg, rgba(13,117,104,0.08), transparent);
      opacity: 0.75;
      pointer-events: none;
    }
    .activity {
      position: relative;
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 18px;
    }
    .spinner {
      width: 42px;
      height: 42px;
      border-radius: 50%;
      border: 3px solid #d7e2dd;
      border-top-color: var(--accent);
      animation: spin 0.9s linear infinite;
      flex: 0 0 auto;
      background: #fff;
    }
    .spinner.idle {
      animation: none;
      border-color: #b7c4cf;
      background: #fff;
    }
    .spinner.done {
      animation: none;
      border-color: #96cfb6;
      background: #effaf5;
      position: relative;
    }
    .spinner.done::before {
      content: "";
      position: absolute;
      width: 15px;
      height: 8px;
      border-left: 3px solid var(--ok);
      border-bottom: 3px solid var(--ok);
      left: 50%;
      top: 48%;
      transform: translate(-50%, -50%) rotate(-45deg);
      transform-origin: center;
    }
    .spinner.failed {
      animation: none;
      border-color: #e0a4a4;
      background: #fff1f1;
      position: relative;
    }
    .spinner.failed::before,
    .spinner.failed::after {
      content: "";
      position: absolute;
      width: 16px;
      height: 3px;
      background: var(--bad);
      left: 10px;
      top: 18px;
    }
    .spinner.failed::before { transform: rotate(45deg); }
    .spinner.failed::after { transform: rotate(-45deg); }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    .progress-title {
      font-size: 18px;
      font-weight: 780;
      margin-bottom: 4px;
    }
    .progress-note {
      color: var(--muted);
      line-height: 1.55;
    }
    .progress-track {
      position: relative;
      height: 10px;
      border-radius: 999px;
      background: #e7eee9;
      overflow: hidden;
      margin-bottom: 18px;
    }
    .progress-panel.is-complete .progress-track,
    .progress-panel.is-idle .progress-track {
      display: none;
    }
    .progress-bar {
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #0d7568, #34a58b);
      transition: width 0.35s ease;
    }
    .funnel-grid {
      position: relative;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
      margin: 0 0 18px;
    }
    .progress-panel.is-complete .funnel-grid,
    .progress-panel.is-idle .funnel-grid {
      display: none;
    }
    .funnel-card {
      position: relative;
      min-width: 0;
      display: grid;
      gap: 8px;
      padding: 12px 11px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,0.92);
      overflow: hidden;
      animation: funnelIn 0.28s ease both;
    }
    .funnel-card.active {
      border-color: #8ccabc;
      box-shadow: 0 0 0 4px rgba(13,117,104,0.09);
    }
    .funnel-card.active::after {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(110deg, transparent 0%, rgba(52,165,139,0.12) 45%, transparent 80%);
      transform: translateX(-100%);
      animation: sweep 1.55s ease-in-out infinite;
      pointer-events: none;
    }
    .funnel-card.done {
      background: #fbfefd;
    }
    .funnel-label {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.3;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .funnel-value {
      color: var(--text);
      font-size: 24px;
      font-weight: 800;
      line-height: 1;
      letter-spacing: 0;
      font-variant-numeric: tabular-nums;
    }
    .funnel-note {
      min-height: 30px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
    }
    .funnel-track {
      height: 5px;
      border-radius: 999px;
      background: #e8eef2;
      overflow: hidden;
    }
    .funnel-fill {
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
      transition: width 0.45s ease;
    }
    .funnel-card.waiting .funnel-fill {
      background: #b7c4cf;
    }
    .funnel-card.active .funnel-fill {
      animation: pulseFill 1.1s ease-in-out infinite;
    }
    @keyframes funnelIn {
      from { opacity: 0; transform: translateY(5px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes sweep {
      to { transform: translateX(100%); }
    }
    @keyframes pulseFill {
      0%, 100% { filter: brightness(1); }
      50% { filter: brightness(1.18); }
    }
    .step-list {
      position: relative;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .progress-panel.is-complete .step-list,
    .progress-panel.is-idle .step-list {
      display: none;
    }
    .step {
      display: grid;
      grid-template-columns: 18px 1fr;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfb;
      color: var(--muted);
      line-height: 1.35;
    }
    .step-dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      border: 2px solid #b7c4cf;
      background: #fff;
    }
    .step.active {
      color: var(--text);
      font-weight: 760;
      border-color: #9bcfc5;
      background: #f0faf6;
    }
    .step.active .step-dot {
      border-color: var(--accent);
      background: var(--accent);
      box-shadow: 0 0 0 5px rgba(15, 107, 95, 0.12);
    }
    .step.done {
      color: var(--text);
    }
    .step.done .step-dot {
      border-color: var(--ok);
      background: var(--ok);
    }
    .result-note {
      margin-top: 18px;
      padding: 12px 13px;
      border-radius: 8px;
      background: var(--panel-soft);
      color: var(--muted);
      line-height: 1.6;
    }
    .results-list {
      margin-top: 14px;
      display: grid;
      gap: 8px;
      max-height: 280px;
      overflow: auto;
      padding-right: 2px;
    }
    .result-item {
      display: grid;
      gap: 5px;
      padding: 11px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .result-title {
      color: var(--text);
      font-weight: 700;
      line-height: 1.45;
      text-decoration: none;
    }
    .result-title:hover {
      color: var(--accent);
    }
    .result-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .result-url {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .empty-results {
      padding: 12px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      background: #fbfcfd;
      line-height: 1.6;
    }
    .output-files {
      margin-top: 14px;
      display: block;
    }
    .markdown-card {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px 14px;
      align-items: center;
      padding: 16px;
      border: 1px solid #c8ded6;
      border-radius: 8px;
      background: #f5fbf8;
    }
    .markdown-card-title {
      font-size: 16px;
      font-weight: 780;
      color: var(--text);
    }
    .markdown-card-path {
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
      word-break: break-all;
    }
    .markdown-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .markdown-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      border-radius: 8px;
      padding: 0 14px;
      background: var(--accent);
      color: #fff;
      font-weight: 760;
      text-decoration: none;
    }
    .markdown-link:hover {
      background: var(--accent-dark);
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.55;
      margin-top: 6px;
    }
    details {
      margin-top: 14px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }
    summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    .settings-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(280px, 1fr));
      gap: 18px;
    }
    @media (max-width: 1180px) {
      .layout {
        grid-template-columns: minmax(340px, 420px) 1fr;
      }
      .run-column {
        grid-column: auto;
      }
    }
    @media (max-width: 860px) {
      nav {
        position: static;
        height: auto;
        grid-template-columns: 1fr;
        padding: 16px;
        gap: 12px;
      }
      .nav-buttons { justify-content: flex-start; }
      .footer-note { white-space: normal; }
      .main { padding: 20px 16px 32px; }
      .topbar, .layout, .settings-grid { grid-template-columns: 1fr; }
      .history-toggle { top: 132px; }
      .history-panel { top: 112px; bottom: 14px; }
      .funnel-grid, .step-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .row { grid-template-columns: 1fr; }
      .actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class="shell">
    <nav>
      <div class="brand">
        <div class="mark">微</div>
        <div>
          <h1>微信研究工作台</h1>
          <div class="footer-note">Search · Verify · MinerU</div>
        </div>
      </div>
      <div class="nav-buttons">
        <button class="nav-button active" type="button" data-page="workbench">任务台</button>
        <button class="nav-button" type="button" data-page="settings">设置</button>
      </div>
      <div class="footer-note">只在本机运行</div>
    </nav>
    <main class="main">
      <section class="page active" id="page-workbench">
        <div class="topbar">
          <div>
            <h2>新建研究任务</h2>
            <div class="subtitle">输入研究主题，程序会完成搜索、验证和本地 HTML 准备。</div>
          </div>
          <span class="pill" id="serverState">本地运行</span>
        </div>
        <button class="history-toggle" id="historyToggle" type="button">历史</button>
        <aside class="history-panel" id="historyPanel">
          <div class="history-head">
            <div>
              <div class="history-title">历史结果</div>
              <div class="history-subtitle">点击查看已生成的 Markdown</div>
            </div>
          </div>
          <div class="history-list" id="historyList">
            <div class="history-empty">正在读取最近结果...</div>
          </div>
        </aside>
        <div class="layout">
          <form class="panel" id="jobForm">
            <div class="panel-title">任务信息</div>
            <label for="topic">搜索关键词</label>
            <textarea id="topic" required placeholder="例如：外星人电解质水 2026世界杯 品牌营销"></textarea>
            <label for="timeRange">时间范围</label>
            <select id="timeRange">
              <option value="365" selected>过去一年</option>
              <option value="180">过去半年</option>
              <option value="90">过去三个月</option>
              <option value="30">过去一个月</option>
              <option value="custom">自定义</option>
            </select>
            <div class="row">
              <div class="custom-date">
                <label for="startDate">开始日期</label>
                <input id="startDate" type="date">
              </div>
              <div class="custom-date">
                <label for="endDate">结束日期</label>
                <input id="endDate" type="date">
              </div>
            </div>
            <div class="field">
              <label>筛选强度</label>
              <div class="intensity-control" id="intensityControl">
                <div class="intensity-readout">
                  <div class="intensity-current" id="intensityTitle">0.6 推荐</div>
                  <div class="intensity-limit" id="intensityCap">最多 20 篇</div>
                </div>
                <div class="intensity-slider-shell">
                  <input class="intensity-range" id="intensityRange" type="range" min="0" max="5" step="1" value="3" aria-label="筛选强度">
                </div>
                <div class="intensity-scale" id="intensityScale">
                  <span style="--tick-left: 0%;">0</span>
                  <span style="--tick-left: 20%;">0.2</span>
                  <span style="--tick-left: 40%;">0.4</span>
                  <span style="--tick-left: 60%;">0.6</span>
                  <span style="--tick-left: 80%;">0.8</span>
                  <span style="--tick-left: 100%;">1.0</span>
                </div>
                <div class="intensity-desc" id="intensityDesc">质量和覆盖平衡，不会为了凑数加入弱相关内容。</div>
              </div>
            </div>
            <div class="actions">
              <button type="submit">开始任务</button>
              <button class="secondary" type="button" id="refreshBtn">刷新状态</button>
              <button class="secondary" type="button" id="retryBtn">重试验证</button>
              <button class="danger" type="button" id="cancelBtn">终止任务</button>
            </div>
          </form>
          <div class="run-column">
            <div class="statusbar">
              <div>
                <strong id="jobTitle">暂无任务</strong>
                <div class="hint" id="jobMeta">提交任务后，这里会显示当前状态和输出路径。</div>
              </div>
              <span class="pill" id="jobStatus">待开始</span>
            </div>
            <div class="summary" id="jobSummary">网站已打开。填写左侧表单后启动本地自动模式。</div>
            <div class="progress-panel">
              <div class="activity">
                <div class="spinner" id="progressSpinner"></div>
                <div>
                  <div class="progress-title" id="progressTitle">等待任务</div>
                  <div class="progress-note" id="progressNote">填写左侧表单后开始，本页会显示任务进度。</div>
                </div>
              </div>
              <div class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
              <div class="funnel-grid" id="funnelGrid"></div>
              <div class="step-list" id="stepList">
                <div class="step" data-step="queued"><span class="step-dot"></span><span>提交任务</span></div>
                <div class="step" data-step="expand"><span class="step-dot"></span><span>整理关键词</span></div>
                <div class="step" data-step="search"><span class="step-dot"></span><span>搜索候选文章</span></div>
                <div class="step" data-step="screen"><span class="step-dot"></span><span>筛选相关内容</span></div>
                <div class="step" data-step="verify"><span class="step-dot"></span><span>验证微信链接</span></div>
                <div class="step" data-step="output"><span class="step-dot"></span><span>生成本地结果</span></div>
              </div>
              <div class="result-note" id="resultNote">当前没有运行中的任务。</div>
              <div class="output-files" id="outputFiles"></div>
              <div class="results-list" id="resultsList"></div>
            </div>
          </div>
        </div>
      </section>
      <section class="page" id="page-settings">
        <div class="topbar">
          <div>
            <h2>设置</h2>
            <div class="subtitle">这些配置保存在当前浏览器里，提交任务时随请求发送。</div>
          </div>
          <button class="secondary" type="button" id="saveSettingsBtn">保存设置</button>
        </div>
        <div class="settings-grid">
          <div class="panel">
            <div class="panel-title">关键词扩充模型</div>
            <label class="check"><input id="useLlm" type="checkbox"> 使用 LLM 扩充关键词</label>
            <div class="setting-intro">
              <div class="hint">推荐免费方案：OpenRouter。只需要申请一个 API Key。</div>
              <button class="secondary" type="button" id="freeLlmPresetBtn">使用免费预设</button>
            </div>
            <label for="llmApiKey">API Key</label>
            <input id="llmApiKey" type="password" placeholder="OpenRouter API Key">
            <div class="hint">拿 Key：openrouter.ai/settings/keys</div>
            <details>
              <summary>高级接口设置</summary>
              <label for="llmBaseUrl">Base URL</label>
              <input id="llmBaseUrl" placeholder="https://openrouter.ai/api/v1">
              <label for="llmModel">模型</label>
              <input id="llmModel" placeholder="cohere/north-mini-code:free">
            </details>
          </div>
          <div class="panel">
            <div class="panel-title">转换与运行</div>
            <label class="check"><input id="runMineru" type="checkbox"> 搜索完成后运行 MinerU 转换</label>
            <label for="mineruToken">MinerU Token</label>
            <input id="mineruToken" type="password" placeholder="留空则使用服务器环境变量或 mineru_token.txt">
            <div class="hint">搜索节奏、缓存和浏览器验证由程序自动处理。</div>
          </div>
        </div>
      </section>
    </main>
  </div>
  <script>
    let currentJobId = "";
    let timer = null;
    const settingsKey = "wechatResearchSettings";

    const el = (id) => document.getElementById(id);
    const settingIds = ["useLlm", "llmBaseUrl", "llmModel", "llmApiKey", "runMineru", "mineruToken"];
    const intensityProfiles = {
      "1": {cap: 10, label: "1.0 极严", desc: "只保留高度精准内容，数量会明显更少。"},
      "0.8": {cap: 15, label: "0.8 严格", desc: "偏质量，少量扩展，适合要做结论型判断。"},
      "0.6": {cap: 20, label: "0.6 推荐", desc: "质量和覆盖平衡，不会为了凑数加入弱相关内容。"},
      "0.4": {cap: 30, label: "0.4 宽松", desc: "扩大相关背景，适合先看行业上下文。"},
      "0.2": {cap: 40, label: "0.2 很宽", desc: "接受外围材料，适合探索早期线索。"},
      "0": {cap: 50, label: "0 全量", desc: "最大召回，但仍过滤垃圾内容和不可访问链接。"}
    };
    const intensitySteps = ["0", "0.2", "0.4", "0.6", "0.8", "1"];

    function selectedIntensity() {
      const index = Math.max(0, Math.min(intensitySteps.length - 1, Number(el("intensityRange").value || 3)));
      return intensitySteps[index] || "0.6";
    }

    function selectedIntensityProfile() {
      return intensityProfiles[selectedIntensity()] || intensityProfiles["0.6"];
    }

    function syncIntensityControl() {
      const range = el("intensityRange");
      const profile = selectedIntensityProfile();
      const index = Number(range.value || 3);
      const position = (index / (intensitySteps.length - 1)) * 100;
      range.style.setProperty("--intensity-position", `${position}%`);
      el("intensityTitle").textContent = profile.label;
      el("intensityCap").textContent = `最多 ${profile.cap} 篇`;
      el("intensityDesc").textContent = profile.desc;
      document.querySelectorAll("#intensityScale span").forEach((node, itemIndex) => {
        node.classList.toggle("active", itemIndex === index);
      });
    }

    function readSettings() {
      const data = {};
      for (const id of settingIds) {
        const node = el(id);
        data[id] = node.type === "checkbox" ? node.checked : node.value;
      }
      return data;
    }

    function applySettings(data) {
      for (const id of settingIds) {
        if (!(id in data)) continue;
        const node = el(id);
        if (node.type === "checkbox") node.checked = Boolean(data[id]);
        else node.value = data[id];
      }
    }

    function saveSettings() {
      localStorage.setItem(settingsKey, JSON.stringify(readSettings()));
      el("serverState").textContent = "设置已保存";
      setTimeout(() => { el("serverState").textContent = "本地运行"; }, 1400);
    }

    applySettings(JSON.parse(localStorage.getItem(settingsKey) || "{}"));
    syncIntensityControl();
    el("intensityRange").addEventListener("input", syncIntensityControl);

    function formatDate(date) {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }

    function dateRangeFromSelection() {
      const value = el("timeRange").value;
      if (value === "custom") {
        return {
          start_date: el("startDate").value,
          end_date: el("endDate").value
        };
      }
      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - Number(value || 365));
      return {
        start_date: formatDate(start),
        end_date: formatDate(end)
      };
    }

    function syncTimeRangeFields() {
      const isCustom = el("timeRange").value === "custom";
      document.querySelectorAll(".custom-date").forEach((node) => {
        node.style.display = isCustom ? "block" : "none";
      });
      if (!isCustom) {
        const range = dateRangeFromSelection();
        el("startDate").value = range.start_date;
        el("endDate").value = range.end_date;
      }
    }

    syncTimeRangeFields();
    el("timeRange").addEventListener("change", syncTimeRangeFields);

    el("freeLlmPresetBtn").addEventListener("click", () => {
      el("useLlm").checked = true;
      el("llmBaseUrl").value = "https://openrouter.ai/api/v1";
      el("llmModel").value = "cohere/north-mini-code:free";
      saveSettings();
    });

    function setStatus(status) {
      const pill = el("jobStatus");
      const labels = {
        queued: "排队中",
        running: "运行中",
        done: "完成",
        failed: "失败",
        canceled: "已终止",
        idle: "待开始"
      };
      pill.textContent = labels[status] || status || "待开始";
      pill.className = "pill";
      if (status === "running" || status === "queued") pill.classList.add("running");
      if (status === "done") pill.classList.add("done");
      if (status === "failed") pill.classList.add("failed");
      if (status === "canceled") pill.classList.add("canceled");
    }

    const progressSteps = ["queued", "expand", "search", "screen", "verify", "output"];
    const progressLabels = {
      queued: ["任务已提交", "正在等待本地程序接手。"],
      expand: ["整理关键词", "正在生成更克制的搜索角度。"],
      search: ["搜索候选文章", "正在从搜索结果里收集可能相关的文章。"],
      screen: ["筛选相关内容", "正在按时间、主题和质量过滤候选。"],
      verify: ["验证微信链接", "如果弹出验证浏览器，请在里面完成搜狗验证。"],
      output: ["生成本地结果", "正在写入 urls.txt、候选表和本地文件。"]
    };
    const funnelDefinitions = [
      {key: "collected", label: "搜索候选", step: "search"},
      {key: "date", label: "时间过滤", step: "screen"},
      {key: "core", label: "主题筛选", step: "screen"},
      {key: "pool", label: "待验证池", step: "verify"},
      {key: "verified", label: "成功链接", step: "output"}
    ];

    function latestMatch(logs, pattern) {
      for (let index = logs.length - 1; index >= 0; index -= 1) {
        const match = logs[index].match(pattern);
        if (match) return match;
      }
      return null;
    }

    function metric(value, total, note) {
      return {
        value: Number.isFinite(value) ? value : 0,
        total: Number.isFinite(total) && total > 0 ? total : 0,
        note: note || "等待数据"
      };
    }

    function funnelStatsFromJob(job) {
      const logs = job.logs || [];
      const searchMatch = latestMatch(logs, /Search\s+(\d+)\/(\d+)/);
      const addedMatch = latestMatch(logs, /total screenable=(\d+)/);
      const collectedMatch = latestMatch(logs, /Collected\s+(\d+)\s+unique candidates/);
      const dateMatch = latestMatch(logs, /Date filter kept\s+(\d+)\s+of\s+(\d+)/);
      const coreMatch = latestMatch(logs, /Core topic filter\s+\([^)]+\)\s+kept\s+(\d+)\s+of\s+(\d+)\s+candidates/);
      const poolMatch = latestMatch(logs, /Screening pool:\s+(\d+)\s+candidates for\s+(\d+)\s+(?:final URLs|result cap)/);
      const verifyMatch = latestMatch(logs, /Verify\s+(\d+)\/(\d+)/);
      const wroteMatch = latestMatch(logs, /Wrote\s+(\d+)\s+verified URLs/);
      const noUrl = logs.some((line) => /No usable WeChat URLs/.test(line));
      const resultCount = (job.results || []).length;

      const collected = collectedMatch ? Number(collectedMatch[1]) : 0;
      const dateKept = dateMatch ? Number(dateMatch[1]) : collected;
      const dateTotal = dateMatch ? Number(dateMatch[2]) : collected;
      const coreKept = coreMatch ? Number(coreMatch[1]) : dateKept;
      const coreTotal = coreMatch ? Number(coreMatch[2]) : dateKept;
      const pool = poolMatch ? Number(poolMatch[1]) : coreKept;
      const target = poolMatch ? Number(poolMatch[2]) : selectedIntensityProfile().cap;
      const verified = wroteMatch ? Number(wroteMatch[1]) : resultCount;

      return {
        collected: metric(
          collected,
          searchMatch ? Number(searchMatch[2]) * 10 : Math.max(collected, target),
          searchMatch ? `第 ${searchMatch[1]} / ${searchMatch[2]} 组关键词` : "等待搜索结果"
        ),
        date: metric(
          dateKept,
          dateTotal,
          dateMatch ? `保留 ${dateKept} / ${dateTotal}` : "等待时间过滤"
        ),
        core: metric(
          coreKept,
          coreTotal,
          coreMatch ? `保留 ${coreKept} / ${coreTotal}` : (addedMatch ? `可筛 ${addedMatch[1]} 条` : "等待主题筛选")
        ),
        pool: metric(
          pool,
          Math.max(target, pool),
          poolMatch ? `准备验证 ${pool} 条` : "等待验证池"
        ),
        verified: metric(
          verified,
          Math.max(target, pool, verified),
          wroteMatch ? `最多 ${target} 条` : (verifyMatch ? `验证 ${verifyMatch[1]} / ${verifyMatch[2]}` : (noUrl ? "本轮没有原文链接" : "等待验证结果"))
        )
      };
    }

    function renderFunnel(job, activeStep) {
      const container = el("funnelGrid");
      const stats = funnelStatsFromJob(job);
      container.textContent = "";
      for (const item of funnelDefinitions) {
        const data = stats[item.key] || metric(0, 0, "等待数据");
        const percent = data.total > 0 ? Math.min(100, Math.round((data.value / data.total) * 100)) : 0;
        const card = document.createElement("div");
        const isActive = item.step === activeStep && job.status !== "idle" && job.status !== "done" && job.status !== "failed" && job.status !== "canceled";
        const isDone = data.value > 0 && !isActive;
        card.className = `funnel-card${isActive ? " active" : ""}${isDone ? " done" : ""}${data.value <= 0 ? " waiting" : ""}`;

        const label = document.createElement("div");
        label.className = "funnel-label";
        label.textContent = item.label;
        card.appendChild(label);

        const value = document.createElement("div");
        value.className = "funnel-value";
        value.textContent = String(data.value);
        card.appendChild(value);

        const note = document.createElement("div");
        note.className = "funnel-note";
        note.textContent = data.note;
        card.appendChild(note);

        const track = document.createElement("div");
        track.className = "funnel-track";
        const fill = document.createElement("div");
        fill.className = "funnel-fill";
        fill.style.width = `${percent}%`;
        track.appendChild(fill);
        card.appendChild(track);

        container.appendChild(card);
      }
    }

    function progressFromJob(job) {
      const logs = job.logs || [];
      const text = logs.join("\n");
      if (job.status === "idle") {
        return {
          step: "queued",
          title: "等待任务",
          note: "填写左侧表单后开始，本页会显示任务进度。"
        };
      }
      let step = "queued";
      if (/LLM expansion|整理关键词|Expanded topic|Extra keywords/.test(text)) step = "expand";
      if (/Collecting candidates|Search \d+\/\d+|searching, screening/.test(text)) step = "search";
      if (/Collected \d+|Date filter|Core topic filter|Screening pool/.test(text)) step = "screen";
      if (/Verifying redirect links|Browser verification|Wrote \d+ verified URLs/.test(text)) step = "verify";
      if (/Candidate CSV|Candidate Markdown|Screened pool CSV|preparing local HTML|Auto mode 2\/2|Auto mode finished|No usable WeChat URLs/.test(text)) step = "output";
      if (job.status === "done") step = "output";

      let title = (progressLabels[step] || progressLabels.queued)[0];
      let note = (progressLabels[step] || progressLabels.queued)[1];
      const searchMatch = latestMatch(logs, /Search\s+(\d+)\/(\d+)/);
      const collectedMatch = latestMatch(logs, /Collected\s+(\d+)\s+unique candidates/);
      const keptMatch = latestMatch(logs, /Date filter kept\s+(\d+)\s+of\s+(\d+)/);
      const wroteMatch = latestMatch(logs, /Wrote\s+(\d+)\s+verified URLs/);

      if (searchMatch && step === "search") note = `正在搜索第 ${searchMatch[1]} / ${searchMatch[2]} 组关键词。`;
      if (collectedMatch && (step === "screen" || step === "verify")) note = `已收集 ${collectedMatch[1]} 条候选，正在筛选和验证。`;
      if (keptMatch && step === "screen") note = `时间范围内保留 ${keptMatch[1]} / ${keptMatch[2]} 条候选。`;
      if (wroteMatch) note = `已写入 ${wroteMatch[1]} 条可解析的微信原文链接。`;
      if (/Complete any Sogou verification|Sogou verification is required/.test(text)) {
        note = "请在弹出的浏览器窗口里完成搜狗验证，完成后程序会继续。";
      }
      if (/Browser verification failed|Browser verification unavailable/.test(text)) {
        note = "已筛出候选文章，但验证浏览器没有稳定启动，所以还没有转成微信原文链接。";
      }
      if (/No usable WeChat URLs/.test(text)) note = "已生成候选表，但这次没有拿到可直接解析的微信原文链接。";

      if (job.status === "failed") {
        title = "任务失败";
        note = job.summary || "任务运行时遇到问题。";
      }
      if (job.status === "canceled") {
        title = "任务已终止";
        note = job.summary || "任务已手动终止。";
      }
      if (job.status === "done") {
        title = "任务完成";
        note = job.summary || note;
      }
      return {step, title, note};
    }

    function renderProgress(job) {
      const progress = progressFromJob(job);
      const activeIndex = progressSteps.indexOf(progress.step);
      const panel = document.querySelector(".progress-panel");
      const isLive = job.status === "queued" || job.status === "running";
      panel.classList.toggle("is-live", isLive);
      panel.classList.toggle("is-complete", job.status === "done");
      panel.classList.toggle("is-idle", job.status === "idle");
      document.querySelectorAll(".step").forEach((node) => {
        const index = progressSteps.indexOf(node.dataset.step);
        node.classList.toggle("done", index >= 0 && (index < activeIndex || job.status === "done"));
        node.classList.toggle("active", index === activeIndex && job.status !== "idle" && job.status !== "done" && job.status !== "failed" && job.status !== "canceled");
      });
      const percent = job.status === "idle" ? 0 : job.status === "done" ? 100 : (job.status === "failed" || job.status === "canceled") ? Math.max(12, activeIndex * 18) : Math.max(8, (activeIndex + 1) * 16);
      el("progressBar").style.width = `${Math.min(100, percent)}%`;
      el("progressTitle").textContent = progress.title;
      el("progressNote").textContent = progress.note;
      el("resultNote").textContent = job.status === "queued"
        ? "任务已提交，请保持这个本地页面打开。"
        : progress.note;
      renderFunnel(job, progress.step);
      const spinner = el("progressSpinner");
      spinner.className = "spinner";
      if (job.status === "idle") spinner.classList.add("idle");
      if (job.status === "done") spinner.classList.add("done");
      if (job.status === "failed") spinner.classList.add("failed");
      if (job.status === "canceled") spinner.classList.add("failed");
    }

    function addResultItem(container, item, index) {
      const wrapper = document.createElement("div");
      wrapper.className = "result-item";

      const title = document.createElement(item.url ? "a" : "div");
      title.className = "result-title";
      title.textContent = item.title || `微信文章 ${index + 1}`;
      if (item.url) {
        title.href = item.url;
        title.target = "_blank";
        title.rel = "noreferrer";
      }
      wrapper.appendChild(title);

      const meta = document.createElement("div");
      meta.className = "result-meta";
      const pieces = [item.source, item.date].filter(Boolean);
      meta.textContent = pieces.length ? pieces.join(" · ") : "已验证微信原文";
      wrapper.appendChild(meta);

      if (item.url) {
        const url = document.createElement("div");
        url.className = "result-url";
        url.textContent = item.url;
        wrapper.appendChild(url);
      }

      container.appendChild(wrapper);
    }

    function renderResults(job) {
      const container = el("resultsList");
      container.textContent = "";
    }

    function markdownOutput(outputs) {
      return outputs.find((item) => item.label === "摘要")
        || outputs.find((item) => item.label === "Markdown 总表")
        || outputs.find((item) => item.label === "Markdown")
        || null;
    }

    function renderOutputs(job) {
      const container = el("outputFiles");
      container.textContent = "";
      const outputs = job.outputs || [];
      const item = markdownOutput(outputs);
      if (!item) {
        if (job.status === "done") {
          const empty = document.createElement("div");
          empty.className = "empty-results";
          empty.textContent = "这次还没有生成 Markdown 结果。";
          container.appendChild(empty);
        }
        return;
      }

      const card = document.createElement("div");
      card.className = "markdown-card";

      const title = document.createElement("div");
      title.className = "markdown-card-title";
      title.textContent = "Markdown 结果";
      card.appendChild(title);

      const path = document.createElement("div");
      path.className = "markdown-card-path";
      path.textContent = item.path || "";
      card.appendChild(path);

      const actions = document.createElement("div");
      actions.className = "markdown-actions";
      const link = document.createElement("a");
      link.className = "markdown-link";
      link.textContent = "打开 Markdown";
      link.href = item.url || `/file?path=${encodeURIComponent(item.path || "")}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      actions.appendChild(link);
      card.appendChild(actions);
      container.appendChild(card);
    }

    function renderJob(job) {
      if (!job) return;
      currentJobId = job.id;
      el("jobTitle").textContent = job.topic || "本地任务";
      el("jobMeta").textContent = `任务 ${job.id} · ${job.started_at || ""}`;
      setStatus(job.status);
      el("jobSummary").textContent = job.summary || "任务运行中。";
      renderProgress(job);
      renderOutputs(job);
      renderResults(job);
      if (job.status === "done" || job.status === "failed" || job.status === "canceled") {
        clearInterval(timer);
        timer = null;
        loadHistory();
      }
    }

    setStatus("idle");
    renderProgress({status: "idle", logs: [], summary: "等待开始。"});
    renderOutputs({outputs: []});
    renderResults({status: "idle", results: []});
    el("jobTitle").textContent = "暂无任务";
    el("jobMeta").textContent = "历史结果在左侧，点击后才会打开。";
    el("jobSummary").textContent = "填写左侧表单后启动本地自动模式。刷新页面会回到这个初始状态。";
    el("resultNote").textContent = "当前没有运行中的任务。";

    document.querySelectorAll(".nav-button").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active"));
        document.querySelectorAll(".page").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        el(`page-${button.dataset.page}`).classList.add("active");
      });
    });

    async function pollJob() {
      if (!currentJobId) return;
      const res = await fetch(`/api/jobs/${currentJobId}`);
      renderJob(await res.json());
    }

    async function loadLatestOutputs() {
      if (currentJobId) return;
      const res = await fetch("/api/latest-output");
      const data = await res.json();
      if (data.outputs && data.outputs.length) {
        const latestJob = {
          status: "done",
          summary: `已找到最近一次生成的 ${data.outputs.length} 个本地结果文件。`,
          logs: ["Auto mode finished", "preparing local HTML"],
          outputs: data.outputs,
          results: data.results || []
        };
        el("jobTitle").textContent = "最近一次本地结果";
        el("jobMeta").textContent = "打开页面时自动读取";
        setStatus("done");
        el("jobSummary").textContent = latestJob.summary;
        renderProgress(latestJob);
        renderOutputs(latestJob);
        renderResults(latestJob);
        el("resultNote").textContent = "已生成 Markdown 结果，可以直接打开。";
      }
    }

    function renderHistory(items, activeId) {
      const container = el("historyList");
      container.textContent = "";
      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "history-empty";
        empty.textContent = "暂无历史结果";
        container.appendChild(empty);
        return;
      }
      for (const item of items) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `history-item${item.id === activeId ? " active" : ""}`;
        button.dataset.runId = item.id;

        const name = document.createElement("div");
        name.className = "history-name";
        name.textContent = item.title || item.id;
        button.appendChild(name);

        const meta = document.createElement("div");
        meta.className = "history-meta";
        meta.textContent = item.created_at || "本地结果";
        button.appendChild(meta);

        const summary = document.createElement("div");
        summary.className = "history-summary";
        for (const text of historyStats(item.summary)) {
          const stat = document.createElement("span");
          stat.className = "history-stat";
          stat.textContent = text;
          summary.appendChild(stat);
        }
        button.appendChild(summary);

        button.addEventListener("click", async () => {
          await loadRunOutput(item.id);
          el("historyPanel").classList.remove("open");
        });
        container.appendChild(button);
      }
    }

    function historyStats(summary) {
      const markdown = String(summary || "").match(/(\d+)\s*个\s*Markdown/);
      const success = String(summary || "").match(/(\d+)\s*条成功/);
      const stats = [];
      if (markdown) stats.push(`Markdown ${markdown[1]}`);
      if (success) stats.push(`成功 ${success[1]}`);
      return stats.length ? stats : [summary || "已生成结果"];
    }

    async function loadHistory(activeId = "") {
      const res = await fetch("/api/history");
      const data = await res.json();
      renderHistory(data.history || [], activeId);
    }

    async function loadRunOutput(runId) {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
      const data = await res.json();
      if (data.error) return;
      currentJobId = "";
      const latestJob = {
        status: "done",
        summary: data.summary || "已读取历史 Markdown 结果。",
        logs: ["Auto mode finished", "preparing local HTML"],
        outputs: data.outputs || [],
        results: []
      };
      el("jobTitle").textContent = data.title || "历史结果";
      el("jobMeta").textContent = data.created_at || runId;
      setStatus("done");
      el("jobSummary").textContent = latestJob.summary;
      renderProgress(latestJob);
      renderOutputs(latestJob);
      renderResults(latestJob);
      el("resultNote").textContent = "已切换到这次历史结果。";
      await loadHistory(runId);
    }

    loadHistory();

    el("historyToggle").addEventListener("click", () => {
      el("historyPanel").classList.toggle("open");
    });

    el("jobForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      el("historyPanel").classList.remove("open");
      const selectedRange = dateRangeFromSelection();
      const payload = {
        topic: el("topic").value.trim(),
        start_date: selectedRange.start_date,
        end_date: selectedRange.end_date,
        intensity: Number(selectedIntensity()),
        use_llm: el("useLlm").checked,
        llm_base_url: el("llmBaseUrl").value.trim(),
        llm_model: el("llmModel").value.trim(),
        llm_api_key: el("llmApiKey").value,
        run_mineru: el("runMineru").checked,
        mineru_token: el("mineruToken").value
      };
      saveSettings();
      renderJob({
        id: "提交中",
        topic: payload.topic,
        status: "queued",
        started_at: "",
        summary: "任务正在提交。"
      });
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const job = await res.json();
      renderJob(job);
      if (timer) clearInterval(timer);
      timer = setInterval(pollJob, 1500);
    });

    el("refreshBtn").addEventListener("click", () => {
      el("historyPanel").classList.remove("open");
      pollJob();
    });
    el("cancelBtn").addEventListener("click", async () => {
      if (!currentJobId || currentJobId === "提交中") return;
      const res = await fetch(`/api/jobs/${currentJobId}/cancel`, {method: "POST"});
      renderJob(await res.json());
    });
    el("retryBtn").addEventListener("click", async () => {
      saveSettings();
      renderJob({
        id: "提交中",
        topic: "重试最新候选验证",
        status: "queued",
        started_at: "",
        summary: "正在查找最新候选表。"
      });
      const res = await fetch("/api/retry-latest", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          intensity: Number(selectedIntensity()),
          run_mineru: el("runMineru").checked,
          mineru_token: el("mineruToken").value
        })
      });
      const job = await res.json();
      renderJob(job);
      if (timer) clearInterval(timer);
      timer = setInterval(pollJob, 1500);
    });
    el("saveSettingsBtn").addEventListener("click", saveSettings);
  </script>
</body>
</html>
"""


@dataclass
class Job:
    id: str
    topic: str
    status: str = "queued"
    started_at: str = ""
    summary: str = "等待开始。"
    logs: list[str] = field(default_factory=list)
    results: list[dict[str, str]] = field(default_factory=list)
    outputs: list[dict[str, str]] = field(default_factory=list)
    params_path: str = ""
    process_returncode: int | None = None
    cancel_requested: bool = False
    current_process: subprocess.Popen[Any] | None = field(default=None, repr=False, compare=False)
    process_lock: Any = field(default_factory=threading.Lock, repr=False, compare=False)

    def append(self, line: str) -> None:
        text = line.rstrip("\r\n")
        if text:
            self.logs.append(text)
        if len(self.logs) > 1200:
            self.logs = self.logs[-1200:]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "status": self.status,
            "started_at": self.started_at,
            "summary": self.summary,
            "logs": self.logs,
            "results": self.results,
            "outputs": self.outputs,
            "params_path": self.params_path,
            "process_returncode": self.process_returncode,
            "cancel_requested": self.cancel_requested,
        }

    def request_cancel(self) -> None:
        self.cancel_requested = True
        self.summary = "正在终止任务。"
        self.append("Cancel requested by user.")
        with self.process_lock:
            process = self.current_process
        terminate_process_tree(process)


def remove_dead_proxy_env(env: dict[str, str]) -> None:
    for name in PROXY_ENV_NAMES:
        value = env.get(name, "").strip().lower().rstrip("/")
        if value in DEAD_PROXY_VALUES:
            env.pop(name, None)


def terminate_process_tree(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            try:
                process.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                pass
        except Exception:
            pass
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def expand_topic_with_llm(payload: dict[str, Any], job: Job) -> dict[str, str]:
    topic = str(payload.get("topic", "")).strip()
    base_url = str(payload.get("llm_base_url", "")).strip().rstrip("/")
    model = str(payload.get("llm_model", "")).strip()
    api_key = str(payload.get("llm_api_key", "")).strip()
    if not payload.get("use_llm"):
        return {"topic": topic, "extra_keywords": "", "exclude_keywords": ""}
    if not base_url or not model or not api_key:
        job.append("LLM expansion skipped: Base URL, model, or API key is missing.")
        return {"topic": topic, "extra_keywords": "", "exclude_keywords": ""}

    prompt = {
        "task": "Expand WeChat article research keywords. Return only JSON.",
        "topic": topic,
        "time_range": {
            "start_date": payload.get("start_date", ""),
            "end_date": payload.get("end_date", ""),
        },
        "output_schema": {
            "topic": "return the original topic unchanged",
            "extra_keywords": "at most 2 high-signal Chinese angle words, comma separated",
            "exclude_keywords": "comma separated low-value or wrong-intent terms",
        },
        "rules": [
            "Do not invent facts.",
            "Keep the topic unchanged. Do not append generic labels such as brand marketing activity.",
            "Extra keywords should be sparse and exploratory, not a full keyword list.",
            "Avoid repeating words already present in the topic.",
            "Avoid broad generic words such as brand, activity, beverage, market marketing, and communication.",
            "Keep terms useful for business reports, case reviews, industry analysis, data reports, interviews, and strategy breakdowns.",
            "Exclude recruitment, courses, download bait, pure match scores, schedules, and unrelated entertainment.",
        ],
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You generate compact JSON keyword expansions for WeChat article search."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        if "```" in content:
            content = content.split("```", 2)[1]
            if content.lstrip().startswith("json"):
                content = content.split("\n", 1)[1]
        parsed = json.loads(content)
        expanded = {
            "topic": topic,
            "extra_keywords": normalize_keywords(parsed.get("extra_keywords", ""), max_items=2, topic=topic),
            "exclude_keywords": normalize_keywords(parsed.get("exclude_keywords", ""), max_items=6),
        }
        job.append("LLM expansion complete.")
        job.append(f"Expanded topic: {expanded['topic']}")
        if expanded["extra_keywords"]:
            job.append(f"Extra keywords: {expanded['extra_keywords']}")
        if expanded["exclude_keywords"]:
            job.append(f"Exclude keywords: {expanded['exclude_keywords']}")
        return expanded
    except urllib.error.URLError as exc:
        job.append(
            "LLM 扩词失败，已继续使用原始关键词。"
            "请检查 Base URL、API Key 和网络连接；免费预设应使用 https://openrouter.ai/api/v1。"
        )
        job.append(f"LLM error detail: {exc.reason if hasattr(exc, 'reason') else exc}")
        return {"topic": topic, "extra_keywords": "", "exclude_keywords": ""}
    except (KeyError, json.JSONDecodeError, TimeoutError, socket.timeout) as exc:
        job.append(f"LLM 扩词失败，已继续使用原始关键词：{type(exc).__name__}: {exc}")
        return {"topic": topic, "extra_keywords": "", "exclude_keywords": ""}


GENERIC_LLM_KEYWORDS = {
    "品牌",
    "活动",
    "饮料",
    "市场营销",
    "品牌营销",
    "传播",
    "促销",
    "合作",
    "曝光",
    "销量",
    "案例",
    "复盘",
    "分析",
    "报告",
}


def normalize_keywords(value: Any, max_items: int | None = None, topic: str = "") -> str:
    if isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = re.split(r"[,，;；\s]+", str(value or ""))
    topic_compact = re.sub(r"\s+", "", topic)
    items: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        item = raw_item.strip()
        if not item:
            continue
        compact = re.sub(r"\s+", "", item)
        if compact in seen or compact in GENERIC_LLM_KEYWORDS:
            continue
        if topic_compact and compact and compact in topic_compact:
            continue
        items.append(item)
        seen.add(compact)
        if max_items and len(items) >= max_items:
            break
    return ",".join(items)


def usable_wechat_url_count(urls_path: Path = ROOT / "urls.txt") -> int:
    try:
        lines = urls_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    return sum(1 for line in lines if "mp.weixin.qq.com" in line)


def read_verified_urls(urls_path: Path = ROOT / "urls.txt") -> list[str]:
    try:
        lines = urls_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for line in lines:
        url = line.strip()
        if "mp.weixin.qq.com" not in url or url in seen:
            continue
        urls.append(url)
        seen.add(url)
    return urls


def repo_path_from_log(value: str) -> Path:
    path = Path(value.strip().strip('"'))
    if path.is_absolute():
        return path
    return ROOT / path


def latest_log_value(logs: list[str], prefix: str) -> str:
    for line in reversed(logs):
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def result_title(row: dict[str, str], index: int) -> str:
    for key in ("title", "标题", "article_title"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return f"微信文章 {index + 1}"


def result_source(row: dict[str, str]) -> str:
    for key in ("account", "source", "公众号", "author"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def result_date(row: dict[str, str]) -> str:
    for key in ("date", "publish_date", "pub_date", "发布时间"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def read_result_items(job: Job, limit: int = 50) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    csv_value = latest_log_value(job.logs, "Candidate CSV:")
    rows = read_csv_rows(repo_path_from_log(csv_value)) if csv_value else []

    for row in rows:
        url = str(row.get("resolved_url") or row.get("url") or "").strip()
        if "mp.weixin.qq.com" not in url or url in seen:
            continue
        items.append(
            {
                "title": result_title(row, len(items)),
                "url": url,
                "source": result_source(row),
                "date": result_date(row),
            }
        )
        seen.add(url)
        if len(items) >= limit:
            return items

    if items:
        return items

    for url in read_verified_urls():
        if url in seen:
            continue
        items.append({"title": f"微信文章 {len(items) + 1}", "url": url, "source": "", "date": ""})
        seen.add(url)
        if len(items) >= limit:
            break
    return items


def add_output_item(items: list[dict[str, str]], label: str, path: Path | str) -> None:
    value = str(path).strip()
    if not value:
        return
    output_path = Path(value)
    if not output_path.is_absolute():
        output_path = (ROOT / output_path).resolve()
    else:
        output_path = output_path.resolve()
    value = str(output_path)
    if any(item.get("path") == value for item in items):
        return
    item = {"label": label, "path": value}
    if output_path.is_file():
        item["url"] = f"/file?path={urllib.parse.quote(value)}"
    items.append(item)


def existing_run_path(value: str) -> Path | None:
    if not value:
        return None
    path = repo_path_from_log(value)
    return path if path.exists() else None


def latest_run_dir() -> Path | None:
    latest_path = ROOT / "latest_run.txt"
    try:
        value = latest_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return existing_run_path(value)


def collect_output_items(job: Job, include_latest_run: bool = False) -> list[dict[str, str]]:
    outputs: list[dict[str, str]] = []
    add_output_item(outputs, "链接文件", ROOT / "urls.txt")

    candidate_csv = latest_log_value(job.logs, "Candidate CSV:")
    if candidate_csv:
        add_output_item(outputs, "候选表", repo_path_from_log(candidate_csv))
    candidate_md = latest_log_value(job.logs, "Candidate Markdown:")
    if candidate_md:
        add_output_item(outputs, "候选说明", repo_path_from_log(candidate_md))
    screened_csv = latest_log_value(job.logs, "Screened pool CSV:")
    if screened_csv:
        add_output_item(outputs, "筛选池", repo_path_from_log(screened_csv))

    run_dir = (
        existing_run_path(latest_log_value(job.logs, "Run directory:"))
        or existing_run_path(latest_log_value(job.logs, "Run output:"))
    )
    if not run_dir and include_latest_run:
        run_dir = latest_run_dir()
    if run_dir:
        add_output_item(outputs, "运行目录", run_dir)
        markdown_dir = run_dir / "markdown"
        html_dir = run_dir / "html"
        if markdown_dir.exists():
            add_output_item(outputs, "Markdown", markdown_dir)
        if html_dir.exists():
            add_output_item(outputs, "HTML", html_dir)
        for label, name in [
            ("摘要", "summary.md"),
            ("结果 JSON", "result.json"),
            ("HTML 清单", "html_manifest.json"),
            ("成功链接", "successful_urls.txt"),
            ("失败链接", "failed_urls.txt"),
        ]:
            path = run_dir / name
            if path.exists():
                add_output_item(outputs, label, path)

    run_html = latest_log_value(job.logs, "Run HTML:")
    if run_html:
        add_output_item(outputs, "HTML", repo_path_from_log(run_html))
    run_markdown = latest_log_value(job.logs, "Run Markdown:")
    if run_markdown:
        add_output_item(outputs, "Markdown", repo_path_from_log(run_markdown))
    manifest = latest_log_value(job.logs, "HTML manifest:")
    if manifest:
        add_output_item(outputs, "HTML 清单", repo_path_from_log(manifest))
    result_json = latest_log_value(job.logs, "Result JSON:")
    if result_json:
        add_output_item(outputs, "结果 JSON", repo_path_from_log(result_json))
    failed_urls = latest_log_value(job.logs, "Failed URLs:")
    if failed_urls:
        add_output_item(outputs, "失败链接", repo_path_from_log(failed_urls))

    return outputs


def collect_run_output_items(run_dir: Path) -> list[dict[str, str]]:
    outputs: list[dict[str, str]] = []
    summary_path = run_dir / "summary.md"
    if summary_path.exists():
        add_output_item(outputs, "摘要", summary_path)
        return outputs
    markdown_dir = run_dir / "markdown"
    if markdown_dir.exists():
        files = sorted(markdown_dir.glob("*.md"))
        if files:
            add_output_item(outputs, "Markdown 总表", files[0])
        else:
            add_output_item(outputs, "Markdown", markdown_dir)
    return outputs


def safe_repo_path(value: str) -> Path | None:
    try:
        path = Path(value).resolve()
        path.relative_to(ROOT.resolve())
        return path
    except (OSError, ValueError):
        return None


def readable_run_name(run_dir: Path) -> str:
    match = re.match(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", run_dir.name)
    if not match:
        return run_dir.name
    year, month, day, hour, minute, _second = match.groups()
    return f"{year}-{month}-{day} {hour}:{minute}"


def timestamp_from_name(name: str) -> dt.datetime | None:
    match = re.match(r"^(\d{8})-(\d{6})", name)
    if not match:
        return None
    try:
        return dt.datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def topic_from_nearby_candidate(run_dir: Path) -> str:
    run_time = timestamp_from_name(run_dir.name)
    candidates_dir = ROOT / "candidates"
    if not run_time or not candidates_dir.exists():
        return ""
    files = [
        path for path in candidates_dir.glob("*.csv")
        if not path.name.endswith("-screened-pool.csv")
    ]
    scored: list[tuple[float, Path]] = []
    for path in files:
        candidate_time = timestamp_from_name(path.name)
        if not candidate_time:
            continue
        delta = (run_time - candidate_time).total_seconds()
        if -120 <= delta <= 7200:
            scored.append((abs(delta), path))
    if not scored:
        return ""
    scored.sort(key=lambda item: item[0])
    return topic_from_candidate_csv(scored[0][1])


def run_summary_fields(run_dir: Path) -> dict[str, str]:
    summary_path = run_dir / "summary.md"
    fields = {
        "title": topic_from_nearby_candidate(run_dir) or readable_run_name(run_dir),
        "created_at": "",
        "summary": "已生成 Markdown 结果。",
    }
    if not summary_path.exists():
        return fields
    try:
        lines = summary_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return fields
    success = ""
    markdown_files = ""
    for line in lines[:80]:
        text = line.strip()
        if text.startswith("# "):
            title = text.lstrip("# ").strip()
            if title and not title.lower().startswith("run summary"):
                fields["title"] = title
        elif text.startswith("- Created at:"):
            fields["created_at"] = text.split(":", 1)[1].strip()
        elif text.startswith("- Success:"):
            success = text.split(":", 1)[1].strip()
        elif text.startswith("- Markdown files:"):
            markdown_files = text.split(":", 1)[1].strip()
    pieces = []
    if markdown_files:
        pieces.append(f"{markdown_files} 个 Markdown")
    if success:
        pieces.append(f"{success} 条成功")
    if pieces:
        fields["summary"] = "已生成 " + "，".join(pieces) + "。"
    return fields


def run_payload(run_dir: Path) -> dict[str, Any]:
    fields = run_summary_fields(run_dir)
    return {
        "id": run_dir.name,
        "title": fields["title"],
        "created_at": fields["created_at"],
        "summary": fields["summary"],
        "outputs": collect_run_output_items(run_dir),
    }


def run_history(limit: int = 12) -> list[dict[str, Any]]:
    runs_dir = ROOT / "runs"
    if not runs_dir.exists():
        return []
    run_dirs = sorted(
        [path for path in runs_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [run_payload(path) for path in run_dirs[:limit]]


def latest_screened_pool_csv() -> Path | None:
    candidates_dir = ROOT / "candidates"
    if not candidates_dir.exists():
        return None
    files = sorted(candidates_dir.glob("*-screened-pool.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def latest_candidate_csv() -> Path | None:
    candidates_dir = ROOT / "candidates"
    if not candidates_dir.exists():
        return None
    files = [
        path for path in candidates_dir.glob("*.csv")
        if not path.name.endswith("-screened-pool.csv")
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def topic_from_candidate_csv(path: Path) -> str:
    name = path.stem.replace("-screened-pool", "")
    name = re.sub(r"^\d{8}-\d{6}-", "", name)
    return name.replace("_", " ").strip() or "重试候选验证"


def latest_log_match(logs: list[str], pattern: str) -> re.Match[str] | None:
    compiled = re.compile(pattern)
    for line in reversed(logs):
        match = compiled.search(line)
        if match:
            return match
    return None


INTENSITY_PROFILES: dict[float, dict[str, Any]] = {
    1.0: {
        "label": "1.0 极严",
        "count": 10,
        "min_rating": "strong",
        "max_queries": 6,
        "top_per_query": 8,
        "pool_multiplier": 3,
        "stop_after_empty_rounds": 2,
    },
    0.8: {
        "label": "0.8 严格",
        "count": 15,
        "min_rating": "maybe",
        "max_queries": 10,
        "top_per_query": 10,
        "pool_multiplier": 4,
        "stop_after_empty_rounds": 3,
    },
    0.6: {
        "label": "0.6 推荐",
        "count": 20,
        "min_rating": "maybe",
        "max_queries": 14,
        "top_per_query": 10,
        "pool_multiplier": 5,
        "stop_after_empty_rounds": 4,
    },
    0.4: {
        "label": "0.4 宽松",
        "count": 30,
        "min_rating": "weak",
        "max_queries": 18,
        "top_per_query": 12,
        "pool_multiplier": 5,
        "stop_after_empty_rounds": 5,
    },
    0.2: {
        "label": "0.2 很宽",
        "count": 40,
        "min_rating": "weak",
        "max_queries": 22,
        "top_per_query": 12,
        "pool_multiplier": 6,
        "stop_after_empty_rounds": 6,
    },
    0.0: {
        "label": "0 全量",
        "count": 50,
        "min_rating": "weak",
        "max_queries": 26,
        "top_per_query": 15,
        "pool_multiplier": 6,
        "stop_after_empty_rounds": 8,
    },
}


def intensity_profile(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = float(payload.get("intensity", 0.6))
    except (TypeError, ValueError):
        raw = 0.6
    key = min(INTENSITY_PROFILES, key=lambda value: abs(value - raw))
    profile = dict(INTENSITY_PROFILES[key])
    if "count" in payload and payload.get("count") not in (None, ""):
        try:
            profile["count"] = max(1, int(payload["count"]))
        except (TypeError, ValueError):
            pass
    profile["value"] = key
    profile["pool_size"] = int(profile["count"]) * int(profile["pool_multiplier"])
    return profile


def no_url_summary(job: Job) -> str:
    collected = latest_log_match(job.logs, r"Collected\s+(\d+)\s+unique candidates")
    kept = latest_log_match(job.logs, r"Date filter kept\s+(\d+)\s+of\s+(\d+)")
    browser_failed = any(
        "Browser verification failed" in line or "Browser verification unavailable" in line
        for line in job.logs
    )
    if browser_failed:
        if kept:
            return f"已筛出 {kept.group(1)} 条候选，但验证浏览器没有稳定启动，暂时没有微信原文链接。"
        if collected:
            return f"已收集 {collected.group(1)} 条候选，但验证浏览器没有稳定启动，暂时没有微信原文链接。"
        return "搜索完成，但验证浏览器没有稳定启动，暂时没有微信原文链接。"
    if kept:
        return f"已筛出 {kept.group(1)} 条候选，但没有拿到可直接解析的微信原文链接。"
    return "搜索完成，但没有拿到可直接解析的微信原文链接。请查看 candidates/ 候选表。"


def run_job(job: Job, payload: dict[str, Any]) -> None:
    job.summary = "任务已进入队列，等待前一个任务结束。"
    with JOB_SEMAPHORE:
        if job.cancel_requested:
            job.status = "canceled"
            job.summary = "任务已在排队时终止。"
            return
        run_job_inner(job, payload)


def finish_if_canceled(job: Job) -> bool:
    if not job.cancel_requested:
        return False
    job.status = "canceled"
    job.summary = "任务已手动终止。"
    job.append("Task canceled.")
    return True


def default_browser_path() -> str:
    explicit = os.environ.get("CHROME_PATH", "").strip()
    candidates = [
        explicit,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return explicit


def run_job_inner(job: Job, payload: dict[str, Any]) -> None:
    job.status = "running"
    job.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    job.summary = "任务运行中。"
    try:
        profile = intensity_profile(payload)
        job.append(
            "Screening intensity: "
            f"{profile['label']} (result_cap={profile['count']}, max_queries={profile['max_queries']}, "
            f"top_per_query={profile['top_per_query']}, min_rating={profile['min_rating']})"
        )
        retry_candidate_csv = str(payload.get("retry_candidate_csv", "")).strip()
        if retry_candidate_csv:
            candidate_csv = repo_path_from_log(retry_candidate_csv)
            if not candidate_csv.exists():
                job.status = "failed"
                job.summary = f"候选表不存在：{candidate_csv}"
                return
            job.append(f"Retry candidate CSV: {candidate_csv}")
            job.append("Step 1: retry browser verification for existing candidates.")
            command = [
                "py",
                ".\\wechat_research.py",
                "--topic",
                job.topic,
                "--count",
                str(int(profile["count"])),
                "--candidate-csv",
                str(candidate_csv),
                "--write-urls",
                "--min-rating",
                str(profile["min_rating"]),
                "--min-delay",
                "1",
                "--max-delay",
                "2",
                "--sogou-verify-timeout",
                "600",
            ]
            browser_path = default_browser_path()
            if browser_path:
                command.extend(["--chrome-path", browser_path])
            run_process(command, job, payload)
            if finish_if_canceled(job):
                job.outputs = collect_output_items(job)
                return
            job.results = read_result_items(job)
            job.outputs = collect_output_items(job)
            if job.process_returncode != 0:
                job.status = "failed"
                job.summary = f"重试验证失败，退出码 {job.process_returncode}。"
                job.outputs = collect_output_items(job)
                return
            url_count = usable_wechat_url_count()
            if url_count <= 0:
                job.status = "failed"
                job.summary = "重试没有拿到可用的微信原文链接，请先解决浏览器验证后再试。"
                job.outputs = collect_output_items(job)
                return
            if not payload.get("run_mineru"):
                job.append("Step 2: preparing local HTML files.")
                run_process(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\run_html_only.ps1"], job, payload)
                if finish_if_canceled(job):
                    job.outputs = collect_output_items(job)
                    return
                if job.process_returncode != 0:
                    job.status = "failed"
                    job.summary = f"HTML 准备失败，退出码 {job.process_returncode}。"
                    job.outputs = collect_output_items(job)
                    return
            job.results = read_result_items(job)
            job.outputs = collect_output_items(job)
            job.status = "done"
            if payload.get("run_mineru"):
                job.summary = f"重试完成，已获取 {len(job.results)} 条微信原文链接，并已生成本地解析结果。"
            else:
                job.summary = f"重试完成，已获取 {len(job.results)} 条微信原文链接，并已生成本地 HTML 文件。"
            return

        expanded = expand_topic_with_llm(payload, job)
        params = {
            "topic": expanded["topic"],
            "count": int(profile["count"]),
            "mode": "slow",
            "intensity": profile["value"],
            "max_queries": int(profile["max_queries"]),
            "top_per_query": int(profile["top_per_query"]),
            "pool_size": int(profile["pool_size"]),
            "min_rating": str(profile["min_rating"]),
            "start_date": payload.get("start_date") or "",
            "end_date": payload.get("end_date") or "",
            "extra_keywords": expanded["extra_keywords"],
            "exclude_keywords": expanded["exclude_keywords"],
            "stage": "all" if payload.get("run_mineru") else "search",
            "sogou_verify_timeout": 600,
            "no_browser": False,
            "chrome_path": default_browser_path(),
            "min_delay": 3,
            "max_delay": 7,
            "cache_ttl_hours": 24,
            "continue_after_block": False,
            "stop_after_empty_rounds": int(profile["stop_after_empty_rounds"]),
        }
        WORK_DIR.mkdir(exist_ok=True)
        params_path = WORK_DIR / f"web-job-{job.id}.json"
        params_path.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
        job.params_path = str(params_path)
        job.append(f"Params file: {params_path}")

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ".\\run_auto.ps1",
            "-ParamsFile",
            str(params_path),
        ]
        if not payload.get("run_mineru"):
            job.append("Step 1: search, verify, and write urls.txt.")
        else:
            job.append("Step 1/2: search and verify. Step 2/2: MinerU conversion.")
        run_process(command, job, payload)
        if finish_if_canceled(job):
            job.outputs = collect_output_items(job)
            return
        job.results = read_result_items(job)
        job.outputs = collect_output_items(job)

        if job.process_returncode != 0:
            job.status = "failed"
            job.summary = f"任务失败，退出码 {job.process_returncode}。"
            job.outputs = collect_output_items(job)
            return

        url_count = usable_wechat_url_count()
        job.results = read_result_items(job)
        if url_count <= 0:
            job.status = "failed"
            job.summary = no_url_summary(job)
            job.append("No usable WeChat URLs were written, so local result preparation was skipped.")
            job.outputs = collect_output_items(job)
            return

        if not payload.get("run_mineru"):
            job.append("Step 2: preparing local HTML files.")
            run_process(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\run_html_only.ps1"], job, payload)
            if finish_if_canceled(job):
                job.outputs = collect_output_items(job)
                return
            if job.process_returncode != 0:
                job.status = "failed"
                job.summary = f"HTML 准备失败，退出码 {job.process_returncode}。"
                job.outputs = collect_output_items(job)
                return

        job.results = read_result_items(job)
        job.outputs = collect_output_items(job)
        job.status = "done"
        if job.results:
            if payload.get("run_mineru"):
                job.summary = f"任务完成，已获取 {len(job.results)} 条微信原文链接，并已生成本地解析结果。"
            else:
                job.summary = f"任务完成，已获取 {len(job.results)} 条微信原文链接，并已生成本地 HTML 文件。"
        else:
            job.summary = "任务完成。查看项目目录中的 urls.txt、candidates/ 和 runs/。"
    except Exception as exc:
        job.status = "failed"
        job.summary = f"任务异常：{type(exc).__name__}: {exc}"
        job.append(job.summary)
        job.outputs = collect_output_items(job)


def run_process(command: list[str], job: Job, payload: dict[str, Any]) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = os.environ.copy()
    remove_dead_proxy_env(env)
    env["PYTHONUNBUFFERED"] = "1"
    mineru_token = str(payload.get("mineru_token", "")).strip()
    if mineru_token:
        env["MINERU_TOKEN"] = mineru_token
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        env=env,
    )
    with job.process_lock:
        job.current_process = process
    output_queue: queue.Queue[str] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output_queue.put(line)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        while process.poll() is None:
            while True:
                try:
                    job.append(output_queue.get_nowait())
                except queue.Empty:
                    break
            if job.cancel_requested and process.poll() is None:
                terminate_process_tree(process)
                break
            time.sleep(0.2)
        if job.cancel_requested and process.poll() is None:
            terminate_process_tree(process)
        job.process_returncode = process.wait()
        reader.join(timeout=2)
        while True:
            try:
                job.append(output_queue.get_nowait())
            except queue.Empty:
                break
    finally:
        with job.process_lock:
            if job.current_process is process:
                job.current_process = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if self.path == "/" or self.path.startswith("/?"):
            body = HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/file":
            path_value = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
            file_path = safe_repo_path(path_value)
            if not file_path or not file_path.is_file():
                json_response(self, {"error": "file not found"}, 404)
                return
            try:
                body = file_path.read_bytes()
            except OSError:
                json_response(self, {"error": "file not readable"}, 404)
                return
            content_type = "text/markdown; charset=utf-8" if file_path.suffix.lower() == ".md" else "text/plain; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/history":
            json_response(self, {"history": run_history()})
            return
        if self.path.startswith("/api/runs/"):
            run_id = urllib.parse.unquote(self.path.rsplit("/", 1)[-1])
            run_dir = safe_repo_path(str(ROOT / "runs" / run_id))
            if not run_dir or not run_dir.is_dir():
                json_response(self, {"error": "run not found"}, 404)
                return
            json_response(self, run_payload(run_dir))
            return
        if self.path == "/api/jobs":
            with JOBS_LOCK:
                jobs = [job.as_dict() for job in JOBS.values()]
            json_response(self, jobs)
            return
        if self.path == "/api/latest-output":
            job = Job(id="latest", topic="最近一次结果", status="done")
            candidate_csv = latest_candidate_csv()
            screened_csv = latest_screened_pool_csv()
            if screened_csv:
                job.logs.append(f"Candidate CSV: {screened_csv}")
                job.logs.append(f"Screened pool CSV: {screened_csv}")
            elif candidate_csv:
                job.logs.append(f"Candidate CSV: {candidate_csv}")
            job.outputs = collect_output_items(job, include_latest_run=True)
            job.results = read_result_items(job)
            json_response(self, {"outputs": job.outputs, "results": job.results})
            return
        if self.path.startswith("/api/jobs/"):
            job_id = self.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                json_response(self, {"error": "job not found"}, 404)
                return
            if job.status in {"done", "failed", "canceled"} and not job.outputs:
                job.outputs = collect_output_items(job)
            json_response(self, job.as_dict())
            return
        json_response(self, {"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path.startswith("/api/jobs/") and self.path.endswith("/cancel"):
            parts = self.path.strip("/").split("/")
            job_id = parts[2] if len(parts) >= 3 else ""
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                json_response(self, {"error": "job not found"}, 404)
                return
            if job.status in {"done", "failed", "canceled"}:
                json_response(self, job.as_dict())
                return
            job.request_cancel()
            if job.status == "queued":
                job.status = "canceled"
                job.summary = "任务已在排队时终止。"
            json_response(self, job.as_dict())
            return

        if self.path == "/api/retry-latest":
            payload = read_json(self)
            candidate_csv = latest_screened_pool_csv()
            if not candidate_csv:
                json_response(self, {"error": "没有找到可重试的候选表"}, 404)
                return
            topic = topic_from_candidate_csv(candidate_csv)
            payload["topic"] = topic
            payload["retry_candidate_csv"] = str(candidate_csv)
            job_id = uuid.uuid4().hex[:10]
            job = Job(id=job_id, topic=f"重试验证：{topic}")
            with JOBS_LOCK:
                JOBS[job_id] = job
            thread = threading.Thread(target=run_job, args=(job, payload), daemon=True)
            thread.start()
            json_response(self, job.as_dict(), 201)
            return

        if self.path != "/api/jobs":
            json_response(self, {"error": "not found"}, 404)
            return
        payload = read_json(self)
        topic = str(payload.get("topic", "")).strip()
        if not topic:
            json_response(self, {"error": "topic is required"}, 400)
            return
        job_id = uuid.uuid4().hex[:10]
        job = Job(id=job_id, topic=topic)
        with JOBS_LOCK:
            JOBS[job_id] = job
        thread = threading.Thread(target=run_job, args=(job, payload), daemon=True)
        thread.start()
        json_response(self, job.as_dict(), 201)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    port = int(os.environ.get("WEB_PORT", "8787"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    local_url = f"http://127.0.0.1:{port}"
    print(f"Open {local_url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


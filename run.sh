#!/usr/bin/env bash
set -euo pipefail

python mineru_batch_wechat.py \
  --urls urls.txt \
  --submit-source html-file

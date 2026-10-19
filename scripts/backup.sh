#!/bin/sh
# Sao lưu COWORK bằng SQLite backup API, kiểm integrity.
set -eu
cd "$(dirname "$0")/.."
umask 077
exec .venv/bin/python -m cowork.cli backup

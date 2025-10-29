# 📦 Refactoring Foundation

A modular toolkit for downloading and uploading media via Telegram, featuring CLI and GUI interfaces.

## 📁 core/
- ~~`client.py` — Telethon client wrapper, connection, auth~~
- ~~`downloader.py` — Download logic: scanning, filtering, downloading media~~
- ~~`uploader.py` — Upload logic: single file, folder, progress~~
- ~~`state_manager.py` — State persistence for download sessions~~

## 📁 storage/
- `config.py` — `.env` management and account configuration
- `credentials.py` — *(Future)* Encrypted credential storage

## 📁 ui/
### 📁 cli/
- `commands.py` — CLI command parsers and execution logic
- `formatters.py` — Console output formatting and I/O wrappers

### 📁 gui/
- `app.py` — Main CustomTkinter application setup
- `screens/` — Individual screen classes *(Login, Source, Filter, Download, Upload)*
- `widgets/` — Reusable CustomTkinter components *(e.g., Card, StatBox)*

## 📁 utils/
- `async_helpers.py` — Utilities for running async code in threads, GUI updates
- `progress.py` — Generic progress tracking classes/functions
- `validators.py` — Input validation, hashing utilities
- `errors.py` — Custom error classes

## 📁 tests/
- `unit/` — Unit tests
- `integration/` — Integration tests
- `fixtures/` — Test fixtures

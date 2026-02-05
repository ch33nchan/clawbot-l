# Research Agent Workflows

Workflow automation scripts for research tasks. RAWClaw manages these scripts for uploading data to Azure CDN and syncing with Google Sheets.

## Structure

```
├── scripts/
│   └── upload_file_to_azure.py   # Core Azure CDN upload utility
├── outputs/                       # Generated JSON/CSV outputs
├── .env.example                   # Environment template
├── requirements.txt               # Python dependencies
└── setup.md                       # Node.js/OpenClaw setup guide
```

## Setup

1. **Install Python deps:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Azure credentials:**
   ```bash
   cp .env.example .env
   # Edit .env with your Azure Storage connection string
   ```

3. **Environment variables:**
   - `AZURE_STORAGE_CONNECTION_STRING` - Azure Storage connection string
   - `AZURE_STORAGE_SAS_TOKEN` - (optional) SAS token if needed
   - `AZURE_CDN_BASE_URL` - CDN base URL (default: https://content.dashtoon.ai)
   - `AZURE_CONTAINER_NAME` - Container name (default: stability-images)

## Workflow

1. Write custom upload scripts based on `scripts/upload_file_to_azure.py`
2. Upload files to Azure CDN
3. Collect output URLs in JSON/CSV
4. Sync results to Google Sheets
5. Commit scripts to this repo

## Core Functions

```python
from scripts.upload_file_to_azure import (
    upload_file_to_azure,      # Upload local file → CDN URL
    upload_bytes_to_azure,     # Upload raw bytes → CDN URL
    upload_json_file_to_azure, # Upload JSON with correct content-type
)
```

## Managed by RAWClaw 🦅

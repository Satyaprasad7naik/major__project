```markdown
# Context: Higher Automation – Advanced Live Data Sync

## Project
InsightOS – AI-powered Decision Support System

## Feature Name
Advanced Automated Data Synchronization

## Goal
Make InsightOS pull live data automatically from multiple sources without manual work.

### Target Sources:
1. **Tally** – Automatically pull data every 1 hour
2. **Google Sheets** – Automatically pull data from a shared sheet
3. **Shared Network Folder** – Automatically read Excel files from a network path

---

## Required Automation Features

### 1. Automatic Tally Sync (Every 1 Hour)
- Create a scheduled job that runs every 1 hour
- Pull latest stock and sales data from Tally
- Preferred methods (in order of preference):
  1. Tally XML export (scheduled)
  2. Tally ODBC connection (if possible)
  3. Watch a folder where Tally auto-exports Excel/XML files
- After pulling data → update database → trigger Auto Insights

### 2. Google Sheets Live Sync
- Connect to a Google Sheet that contains:
  - Products
  - Inventory
  - Sales
- Automatically fetch data every 15–30 minutes
- Update the InsightOS database
- Use Google Sheets API (service account recommended)

### 3. Shared Network Folder Sync
- Watch a shared folder (example: `\\server\stock_data\` or a mapped drive)
- Automatically detect new/updated Excel files
- Sync the data into InsightOS
- Useful when multiple people update Excel files on a common drive

---

## Technical Requirements

### Background Jobs
Use APScheduler (already used in the project) to create these jobs:

| Job                        | Frequency       |
|---------------------------|-----------------|
| Tally Auto Sync           | Every 1 hour    |
| Google Sheets Sync        | Every 15-30 min |
| Network Folder Sync       | Every 5-10 min  |

### New Services to Create
```
app/services/
├── tally_auto_sync.py
├── google_sheets_sync.py
└── network_folder_sync.py
```

### Configuration (.env)
Add support for these settings:

```env
# Tally
TALLY_SYNC_ENABLED=true
TALLY_EXPORT_FOLDER=D:/tally_exports
TALLY_SYNC_INTERVAL_MINUTES=60

# Google Sheets
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEET_ID=your_sheet_id_here
GOOGLE_CREDENTIALS_FILE=credentials.json

# Network Folder
NETWORK_FOLDER_ENABLED=true
NETWORK_FOLDER_PATH=\\server\shared\live_data
```

---

## API Endpoints to Add

### 1. Trigger Manual Sync
```
POST /api/v1/sync/tally/auto
POST /api/v1/sync/google-sheets
POST /api/v1/sync/network-folder
```

### 2. Status Endpoints
```
GET /api/v1/sync/status/all
```
Should return last sync time and status of all sources.

---

## Implementation Priority

1. **Network Folder Sync** (Easiest – extend existing Excel sync)
2. **Tally Auto Sync** (using export folder watching)
3. **Google Sheets Sync** (most advanced)

---

## Detailed Implementation Guide

### A. Network Folder Sync
- Reuse existing Excel sync logic
- Instead of only watching local `live_data/`, also watch a configurable network path
- Handle cases where network path is temporarily unavailable

### B. Tally Auto Sync
- Watch a folder where Tally exports files automatically
- Or create a scheduled task that processes Tally XML/Excel exports
- Map Tally fields correctly to products, inventory, and sales tables
- Log every sync attempt

### C. Google Sheets Sync
- Use `gspread` or Google Sheets API
- Read data from specific worksheets
- Upsert into InsightOS database
- Handle authentication securely using service account

---

## Success Criteria

- System can automatically pull data from Tally every hour
- System can pull data from Google Sheets automatically
- System can read Excel files from a shared network folder
- All sync activities are logged
- Auto Insights are triggered after successful sync
- Existing Excel sync continues to work
- User can see last sync status of all sources

---

## Important Notes for Anti-Gravity

- Keep the solution modular (separate service for each source)
- Reuse existing Excel sync and insight generation code as much as possible
- Do not break current features
- Prefer simple and reliable methods over complex real-time connections
- Add clear logs for debugging
- Make each sync source enable/disable via `.env`
- Update README with setup instructions for Tally, Google Sheets, and Network Folder
- Handle errors gracefully (if one source fails, others should still work)

---

## Final Flow After Implementation

```text
Tally (every 1 hour)
Google Sheets (every 15-30 min)
Network Folder (every 5-10 min)
        ↓
   Sync Services
        ↓
 InsightOS Database
        ↓
 Auto-generated Insights
        ↓
 Dashboard Updated
```
```

---

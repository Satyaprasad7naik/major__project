# Context: Fully Automatic Google Sheets Sync (with Google Sign-In / Service Account)

## Project
InsightOS – AI-powered Decision Support System

## Feature Name
Automated Google Sheets Live Data Synchronization

## Goal
Enable InsightOS to automatically pull live data from Google Sheets without manual Excel uploads.

The system should support:
1. Google Service Account (recommended for full automation)
2. Optional Google Sign-In (OAuth) for user-connected sheets

Once connected, data should sync automatically every 15–30 minutes.

---

## Required Functionality

### 1. Google Sheets as Live Data Source
InsightOS should read data from a Google Spreadsheet containing these sheets:

- `Products`
- `Inventory`
- `Sales`

### 2. Authentication Methods

#### Method A: Service Account (Must Implement – Recommended)
- Use a Google Cloud Service Account
- Share the Google Sheet with the service account email
- InsightOS uses the service account credentials to read data automatically in the background

#### Method B: Google Sign-In / OAuth (Optional)
- Allow user to sign in with Google
- Connect their own Google Sheet
- Store the token securely
- Sync data from the connected sheet

---

## Technical Implementation

### 1. Configuration (.env)
Add these settings:

```env
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEET_ID=your_google_sheet_id_here
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_SYNC_INTERVAL_MINUTES=15
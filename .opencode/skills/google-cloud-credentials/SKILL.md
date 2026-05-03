---
name: google-cloud-credentials
description: Enforces global project rules for handling Google Cloud API credentials.
---

# Google Cloud Credentials Protocol

When creating agents, scripts, or systems that require authentication via the Google Cloud API or Google Drive API, follow these absolute rules:

## 1. Centralized Credentials Directory
**Never** search for `credentials.json` or write `token.json` blindly in the current working directory.
You must always default to pointing to the globally defined credentials folder for the project:
**Path:** `/Users/karpinski94/projects/rpm/credentials`

## 2. Environment Variables (.env)
Your code should respect environment overrides for local execution environments. Check for fallback paths in local `.env` variables (e.g., `os.environ.get('CREDENTIALS_DIR', '...')` or standard `.env` secrets).

## 3. Security
Never hardcode raw credentials strings, IDs, or secrets in source code files. Rely strictly on the `credentials.json` and `.env` parsing patterns.

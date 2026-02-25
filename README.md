# Bitbucket Repository Downloader

> Batch-clone or archive every repository from a Bitbucket workspace — either all at once or filtered by project key.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

---

## Table of Contents

- [What It Does](#what-it-does)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Creating a Bitbucket API Token](#creating-a-bitbucket-api-token)
- [Configuration](#configuration)
- [Download Modes](#download-modes)
- [Output Formats](#output-formats)
- [Usage](#usage)
- [Output Structure](#output-structure)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [License](#license)

---

## What It Does

Bitbucket Repository Downloader automates bulk-cloning of Git repositories from a Bitbucket Cloud workspace. You configure your workspace, token, and desired mode in a single JSON file — the tool handles pagination, authentication, and organising the output.

**Two download modes:**

| Mode | Description |
|---|---|
| `all` | Clone / archive every repository in the workspace |
| `projects` | Clone / archive only repos that belong to specified project keys |

---

## Features

| Feature | Description |
|---|---|
| **Two download modes** | Download everything or filter by project key |
| **Two output formats** | Keep full git clones (with `git pull` support) or create `.zip` archives |
| **Pagination handled** | Automatically iterates through all pages of the Bitbucket API |
| **Incremental updates** | In `clone` mode, existing repos are updated with `git pull` |
| **Skip logic** | Already-downloaded ZIPs are skipped automatically |
| **Auth verification** | Checks credentials before starting any downloads |
| **Progress reporting** | Shows per-repo status and a final summary |
| **Debug mode** | `--debug` flag enables verbose logging |
| **Cross-platform** | Works on Windows, macOS, and Linux |

---

## Prerequisites

- **Python 3.8+** — [Download Python](https://www.python.org/downloads/)
- **Git** installed and available in your PATH — test with `git --version`
- A Bitbucket Cloud account with access to the target workspace
- A Bitbucket API token (see next section)

---

## Quick Start

```bash
# 1. Clone this repository
git clone https://github.com/YOUR_USERNAME/bitbucket-downloader.git
cd bitbucket-downloader

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your config file
cp config.example.json config.json        # macOS / Linux
copy config.example.json config.json      # Windows

# 4. Edit config.json with your workspace, username, token, and projects
# (See Configuration section below)

# 5. Run
python bitbucket_downloader.py
```

> **Note:** `config.json` is listed in `.gitignore` — your credentials will never be committed.

---

## Creating a Bitbucket API Token

The tool uses a **Bitbucket Access Token** for authentication. Follow the steps for the token type that suits your use case.

---

### Option 1 — Repository Access Token (Recommended)

A repository access token is scoped to a single repository. Use this if you only need to download repos from one repository, or if you want the most restricted permission.

1. Go to the repository in Bitbucket
2. Click **Repository settings** (gear icon in the left sidebar)
3. Under **Security**, click **Access tokens**
4. Click **Create Repository Access Token**
5. Fill in:
   - **Name**: e.g. `Repo Downloader`
   - **Permissions**: tick `Repositories` → `Read`
6. Click **Create**
7. **Copy the token immediately** — it is shown only once

---

### Option 2 — Workspace Access Token (Recommended for bulk downloads)

A workspace access token is scoped to the entire workspace. This is the best choice when you want to download repositories across multiple projects.

1. Log in to Bitbucket and go to your workspace
2. Click **Workspace settings** (bottom of the left sidebar or via the workspace avatar)
3. Under **Security**, click **Access tokens**
4. Click **Create workspace access token**
5. Fill in:
   - **Name**: e.g. `Bulk Downloader`
   - **Permissions**: tick `Repositories` → `Read`
6. Click **Create**
7. **Copy the token immediately** — it is shown only once

> The token URL pattern is:
> `https://bitbucket.org/{your-workspace}/workspace/settings/access-tokens`

---

### Option 3 — App Password (Alternative)

App passwords are per-account credentials (not tokens). They work differently and require using your **account email** as the username in the `Authorization` header.

1. Go to **Personal settings** → **App passwords**
   Direct link: `https://bitbucket.org/account/settings/app-passwords/`
2. Click **Create app password**
3. Fill in:
   - **Label**: e.g. `Repo Downloader`
   - **Permissions**: tick `Repositories` → `Read`
4. Click **Create** and copy the password

> If using an App Password, set `username` in `config.json` to your **Bitbucket account email address** (not your display name).

---

### Token Security Best Practices

- **Never commit your token** to version control (`config.json` is in `.gitignore`)
- Use the **minimum required scope** (`repository:read` only)
- You can **revoke a token** at any time from the same settings page where you created it
- Rotate tokens periodically
- Store tokens in a password manager or secret vault, not in plain text files

---

## Configuration

Copy `config.example.json` to `config.json` and fill in your values:

```json
{
  "workspace":     "your-workspace-slug",
  "username":      "your-bitbucket-username",
  "api_token":     "your-api-token-here",

  "mode":          "projects",
  "project_keys":  ["PROJECT1", "PROJECT2"],

  "output_dir":    "downloads",
  "output_format": "clone"
}
```

| Key | Required | Description |
|---|---|---|
| `workspace` | Yes | Your Bitbucket workspace slug (the part in the URL: `bitbucket.org/{workspace}`) |
| `username` | Yes | Your Bitbucket username (used for Git authentication) |
| `api_token` | Yes | Your Bitbucket Access Token or App Password |
| `mode` | Yes | `"all"` or `"projects"` (see [Download Modes](#download-modes)) |
| `project_keys` | When mode=projects | List of Bitbucket project keys to download (e.g. `["PRAC", "CHAL"]`) |
| `output_dir` | No | Folder where downloads are saved (default: `downloads`) |
| `output_format` | No | `"clone"` or `"zip"` (default: `"clone"`, see [Output Formats](#output-formats)) |

### How to find your workspace slug

Your workspace slug is the identifier in the URL when you browse your workspace:

```
https://bitbucket.org/{workspace-slug}/
```

### How to find project keys

1. Go to your workspace in Bitbucket
2. Click **Projects** in the left sidebar
3. Each project has a **Key** shown in its card (e.g. `PRAC`, `DEV`, `OPS`)

---

## Download Modes

### `mode: "all"` — Download everything

Downloads every repository the token can access in the workspace. All repos are placed directly in `output_dir`.

```json
{
  "mode": "all",
  "output_dir": "downloads"
}
```

### `mode: "projects"` — Download by project

Downloads only repositories that belong to the listed project keys. Each project gets its own subfolder inside `output_dir`.

```json
{
  "mode": "projects",
  "project_keys": ["PRAC", "CHAL", "OPS"],
  "output_dir": "downloads"
}
```

---

## Output Formats

### `output_format: "clone"` (default)

Clones each repository as a full local git repository. On subsequent runs, existing repos are updated with `git pull`.

```
downloads/
└── my-repo/
    ├── .git/
    └── src/
```

### `output_format: "zip"`

Clones each repository to a temporary directory, creates a `.zip` archive, then deletes the temporary clone. Already-archived ZIPs are skipped on re-runs.

```
downloads/
└── my-repo.zip
```

---

## Usage

### Basic run (uses `config.json`)

```bash
python bitbucket_downloader.py
```

### Use a custom config file

```bash
python bitbucket_downloader.py --config my_workspace.json
```

### Override mode from the command line

```bash
python bitbucket_downloader.py --mode all
python bitbucket_downloader.py --mode projects
```

### Enable verbose debug logging

```bash
python bitbucket_downloader.py --debug
```

### Full help

```bash
python bitbucket_downloader.py --help
```

---

## Output Structure

### Mode: `projects` + format: `clone`

```
downloads/
├── PRAC/
│   ├── repo-alpha/
│   ├── repo-beta/
│   └── repo-gamma/
├── CHAL/
│   ├── challenge-01/
│   └── challenge-02/
└── OPS/
    └── infra-scripts/
```

### Mode: `all` + format: `zip`

```
downloads/
├── repo-alpha.zip
├── repo-beta.zip
├── challenge-01.zip
└── infra-scripts.zip
```

---

## Troubleshooting

### Authentication fails

| Symptom | Likely cause | Fix |
|---|---|---|
| HTTP 401 | Invalid token | Re-generate the token and update `config.json` |
| HTTP 403 | Token lacks permissions | Recreate token with `repository:read` scope |
| HTTP 404 | Workspace not found | Check the `workspace` slug in `config.json` |
| `ConnectionError` | Network issue | Check internet / proxy settings |

### No repositories found

- Verify the `project_keys` values match the exact keys shown in Bitbucket (case-sensitive)
- Check that your token has access to the workspace and projects

### Git not found

Make sure Git is installed and available in your PATH:

```bash
git --version
```

### Windows read-only errors during ZIP cleanup

The script automatically handles Windows read-only file attributes. If cleanup still fails, you can safely delete the `temp_*` folder manually.

### Encoding errors on Windows

Make sure you are using Python 3.8+ and running in a terminal that supports UTF-8. The script reconfigures stdout encoding automatically on Windows.

---

## Project Structure

```
bitbucket-downloader/
├── bitbucket_downloader.py   # Main script — auth, API, clone/archive logic
├── config.example.json       # Config template (copy to config.json and edit)
├── requirements.txt          # Python dependencies
├── .gitignore                # Excludes credentials and downloads from git
├── LICENSE                   # MIT License
└── README.md                 # This file
```

---

## Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-improvement`
3. Commit your changes: `git commit -m "Add my improvement"`
4. Push to the branch: `git push origin feature/my-improvement`
5. Open a Pull Request

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Disclaimer

> **Use at your own risk.**

This tool is intended solely for downloading repositories you have legitimate access to through your own Bitbucket account and token. Always comply with your organisation's policies and Bitbucket's Terms of Service.

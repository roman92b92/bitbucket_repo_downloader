#!/usr/bin/env python3
"""
Bitbucket Repository Downloader
Batch-clone or archive repositories from a Bitbucket workspace.

Two modes:
  all      — Download every repository in the workspace
  projects — Download only repositories belonging to specific project keys
"""

import os
import re
import sys
import stat
import json
import shutil
import logging
import tempfile
import subprocess
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


class BitbucketDownloader:
    def __init__(self, workspace: str, username: str, api_token: str,
                 output_format: str = "clone", debug: bool = False):
        """
        Initialize the Bitbucket downloader.

        Args:
            workspace:     Bitbucket workspace slug (e.g. 'my-company')
            username:      Bitbucket username used for Git authentication
            api_token:     Bitbucket Repository or Workspace Access Token
            output_format: 'clone'  — keep a full git clone on disk
                           'zip'    — clone then archive to a .zip file
            debug:         Enable verbose logging
        """
        self.workspace = workspace
        self.username = username
        self.api_token = api_token
        self.output_format = output_format.lower()
        self.base_url = "https://api.bitbucket.org/2.0"

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_token}',
            'Accept': 'application/json',
        })

        # Logging
        self.logger = logging.getLogger('BitbucketDownloader')
        level = logging.DEBUG if debug else logging.INFO
        self.logger.setLevel(level)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(level)
            handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
            self.logger.addHandler(handler)

        self.logger.info(f"Workspace : {workspace}")
        self.logger.info(f"Format    : {self.output_format}")

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def _paginate(self, url: str, params: Optional[dict] = None) -> List[Dict]:
        """Fetch all pages from a Bitbucket paginated endpoint."""
        results = []
        while url:
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                results.extend(data.get('values', []))
                url = data.get('next')   # next page URL (already includes params)
                params = None            # params are baked into 'next'
            except requests.exceptions.HTTPError as e:
                self.logger.error(f"HTTP error: {e} — {e.response.text[:200]}")
                break
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request error: {e}")
                break
        return results

    def get_all_repositories(self) -> List[Dict]:
        """Return every repository in the workspace."""
        self.logger.info("Fetching all repositories in workspace...")
        url = f"{self.base_url}/repositories/{self.workspace}"
        repos = self._paginate(url, params={'pagelen': 100})
        self.logger.info(f"Found {len(repos)} repositories total")
        return repos

    def get_repositories_by_project(self, project_key: str) -> List[Dict]:
        """Return repositories that belong to a specific project key."""
        self.logger.info(f"Fetching repositories for project: {project_key}")
        url = f"{self.base_url}/repositories/{self.workspace}"
        repos = self._paginate(url, params={
            'q': f'project.key="{project_key}"',
            'pagelen': 100,
        })
        self.logger.info(f"  Found {len(repos)} repositories in project {project_key}")
        return repos

    def verify_auth(self) -> bool:
        """Check that the token is valid before starting any downloads."""
        self.logger.info("Verifying authentication...")
        try:
            url = f"{self.base_url}/repositories/{self.workspace}"
            r = self.session.get(url, params={'pagelen': 1})
            if r.status_code == 200:
                self.logger.info("Authentication OK")
                return True
            elif r.status_code == 401:
                self.logger.error("Authentication failed — check your api_token")
            elif r.status_code == 403:
                self.logger.error("Access denied — token lacks required scopes (need repository:read)")
            elif r.status_code == 404:
                self.logger.error(f"Workspace '{self.workspace}' not found or not accessible")
            else:
                self.logger.error(f"Unexpected status {r.status_code}: {r.text[:200]}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Connection error: {e}")
        return False

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_readonly(func, path, _):
        """Windows helper: strip read-only flag before deletion."""
        os.chmod(path, stat.S_IWRITE)
        func(path)

    def _build_auth_url(self, https_url: str) -> str:
        """Embed username + token into a HTTPS clone URL."""
        clean = re.sub(r'https://[^@]*@', 'https://', https_url)
        return clean.replace('https://', f'https://{self.username}:{self.api_token}@', 1)

    def _get_https_url(self, repo: Dict) -> Optional[str]:
        """Extract the HTTPS clone URL from a repository object."""
        for link in repo.get('links', {}).get('clone', []):
            if link.get('name') == 'https':
                return link['href']
        return None

    # ------------------------------------------------------------------
    # Clone / archive
    # ------------------------------------------------------------------

    def _clone_repo(self, auth_url: str, dest: str) -> bool:
        """Shallow-clone a repository to *dest*."""
        try:
            subprocess.run(
                ['git', 'clone', '--depth', '1', auth_url, dest],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"git clone failed: {e.stderr.strip()[:300]}")
            return False

    def process_repository(self, repo: Dict, target_dir: str) -> bool:
        """
        Clone or archive a single repository into *target_dir*.

        Returns True on success, False on failure.
        """
        repo_name = repo.get('name', 'unknown')
        repo_slug = repo.get('slug', repo_name)

        https_url = self._get_https_url(repo)
        if not https_url:
            self.logger.warning(f"  No HTTPS clone URL for '{repo_name}' — skipping")
            return False

        auth_url = self._build_auth_url(https_url)

        if self.output_format == 'zip':
            zip_path = os.path.join(target_dir, f"{repo_slug}.zip")
            if os.path.exists(zip_path):
                self.logger.info(f"  [SKIP] Already archived: {repo_name}")
                return True

            self.logger.info(f"  [CLONE] {repo_name}")
            tmp = tempfile.mkdtemp()
            tmp_repo = os.path.join(tmp, repo_slug)
            try:
                if not self._clone_repo(auth_url, tmp_repo):
                    return False
                self.logger.info(f"  [ZIP]   Archiving: {repo_name}")
                shutil.make_archive(os.path.join(target_dir, repo_slug), 'zip', tmp_repo)
                self.logger.info(f"  [OK]    {repo_slug}.zip")
                return True
            finally:
                shutil.rmtree(tmp, onerror=self._remove_readonly)

        else:  # clone
            repo_path = os.path.join(target_dir, repo_slug)
            if os.path.exists(repo_path):
                self.logger.info(f"  [UPDATE] Pulling: {repo_name}")
                try:
                    subprocess.run(
                        ['git', '-C', repo_path, 'pull'],
                        check=True, capture_output=True, text=True,
                    )
                    self.logger.info(f"  [OK]     Updated: {repo_name}")
                    return True
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"  git pull failed: {e.stderr.strip()[:200]}")
                    return False
            else:
                self.logger.info(f"  [CLONE] {repo_name}")
                if self._clone_repo(auth_url, repo_path):
                    self.logger.info(f"  [OK]    Cloned: {repo_name}")
                    return True
                return False

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def download_all(self, output_dir: str):
        """Option 1 — Download every repository in the workspace."""
        self._run_download(
            repos=self.get_all_repositories(),
            output_dir=output_dir,
            label="ALL",
        )

    def download_projects(self, project_keys: List[str], output_dir: str):
        """Option 2 — Download repositories for the given project keys."""
        print("=" * 60)
        print(f"Projects : {', '.join(project_keys)}")
        print("=" * 60)
        os.makedirs(output_dir, exist_ok=True)

        total_ok = total_fail = total_skip = 0
        failures = []

        for key in project_keys:
            repos = self.get_repositories_by_project(key)
            if not repos:
                self.logger.warning(f"No repositories found for project {key}")
                continue

            project_dir = os.path.join(output_dir, key)
            os.makedirs(project_dir, exist_ok=True)

            for repo in repos:
                slug = repo.get('slug', 'unknown')
                # quick skip check before calling process_repository
                if self.output_format == 'zip':
                    if os.path.exists(os.path.join(project_dir, f"{slug}.zip")):
                        total_skip += 1
                        continue
                try:
                    if self.process_repository(repo, project_dir):
                        total_ok += 1
                    else:
                        total_fail += 1
                        failures.append((key, repo.get('name', slug)))
                except Exception as e:
                    total_fail += 1
                    failures.append((key, repo.get('name', slug)))
                    self.logger.error(f"  [ERROR] {repo.get('name')}: {e}")

        self._print_summary(total_ok, total_fail, total_skip, failures)

    def _run_download(self, repos: List[Dict], output_dir: str, label: str):
        """Shared download loop used by download_all."""
        print("=" * 60)
        print(f"Mode     : {label}")
        print(f"Repos    : {len(repos)}")
        print("=" * 60)
        os.makedirs(output_dir, exist_ok=True)

        total_ok = total_fail = total_skip = 0
        failures = []

        for repo in repos:
            slug = repo.get('slug', 'unknown')
            if self.output_format == 'zip':
                if os.path.exists(os.path.join(output_dir, f"{slug}.zip")):
                    total_skip += 1
                    continue
            try:
                if self.process_repository(repo, output_dir):
                    total_ok += 1
                else:
                    total_fail += 1
                    failures.append(('—', repo.get('name', slug)))
            except Exception as e:
                total_fail += 1
                failures.append(('—', repo.get('name', slug)))
                self.logger.error(f"  [ERROR] {repo.get('name')}: {e}")

        self._print_summary(total_ok, total_fail, total_skip, failures)

    @staticmethod
    def _print_summary(ok: int, fail: int, skip: int, failures: list):
        print("\n" + "=" * 60)
        print("Download Summary")
        print(f"  Successful : {ok}")
        print(f"  Skipped    : {skip}")
        print(f"  Failed     : {fail}")
        print("=" * 60)
        if failures:
            print("\nFailed repositories:")
            for project, name in failures:
                print(f"  [{project}] {name}")
            print("=" * 60)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(config_file: str = "config.json") -> Optional[dict]:
    """Load and validate configuration from a JSON file."""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{config_file}' not found.")
        print("Copy config.example.json to config.json and fill in your details.")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{config_file}': {e}")
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Bitbucket Repository Downloader — batch-clone or archive repos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  all       Download every repository in the workspace
  projects  Download only repos in the project keys listed in config.json

Output formats:
  clone     Keep a full git clone on disk (supports incremental pull)
  zip       Clone to a temp directory, archive to .zip, then delete the clone

Examples:
  python bitbucket_downloader.py
  python bitbucket_downloader.py --config my_workspace.json
  python bitbucket_downloader.py --mode all
  python bitbucket_downloader.py --mode projects --debug
        """
    )
    parser.add_argument('--config', default='config.json', metavar='FILE',
                        help='Path to JSON config file (default: config.json)')
    parser.add_argument('--mode', choices=['all', 'projects'],
                        help='Override the mode set in config.json')
    parser.add_argument('--debug', action='store_true',
                        help='Enable verbose debug logging')
    args = parser.parse_args()

    print("=" * 60)
    print("Bitbucket Repository Downloader")
    print(f"Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    workspace   = config.get('workspace', '').strip()
    username    = config.get('username', '').strip()
    api_token   = config.get('api_token', '').strip()
    mode        = args.mode or config.get('mode', 'projects').strip()
    project_keys = config.get('project_keys', [])
    output_dir  = config.get('output_dir', 'downloads').strip()
    fmt         = config.get('output_format', 'clone').strip()

    # Validate required fields
    missing = [k for k, v in [('workspace', workspace), ('username', username), ('api_token', api_token)] if not v]
    if missing:
        print(f"Error: Missing required config fields: {', '.join(missing)}")
        sys.exit(1)

    placeholders = {'your-workspace-slug', 'your-bitbucket-username', 'your-api-token-here'}
    if workspace in placeholders or username in placeholders or api_token in placeholders:
        print("\nPlease update config.json with your actual credentials before running.")
        print("See config.example.json for the expected format.")
        sys.exit(1)

    if mode == 'projects' and not project_keys:
        print("Error: mode is 'projects' but no project_keys are listed in config.json")
        sys.exit(1)

    print(f"\nConfiguration:")
    print(f"  Workspace : {workspace}")
    print(f"  Username  : {username}")
    print(f"  Mode      : {mode}")
    if mode == 'projects':
        print(f"  Projects  : {', '.join(project_keys)}")
    print(f"  Format    : {fmt}")
    print(f"  Output    : {output_dir}/")
    print()

    downloader = BitbucketDownloader(workspace, username, api_token,
                                     output_format=fmt, debug=args.debug)

    if not downloader.verify_auth():
        print("\nAuthentication failed. Cannot proceed.")
        print("\nTroubleshooting:")
        print("  1. Double-check workspace, username, and api_token in config.json")
        print("  2. Ensure the token has 'repository:read' scope")
        print("  3. Confirm the token has not expired or been revoked")
        print("  4. Run with --debug for detailed logs")
        sys.exit(1)

    if mode == 'all':
        downloader.download_all(output_dir)
    else:
        downloader.download_projects(project_keys, output_dir)

    print(f"\nFinished : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    main()

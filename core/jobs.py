"""Start an on-demand scraper run from the app.

The app cannot run Playwright, so it writes a row to `jobs`, starts the GitHub
Actions workflow and polls the row. With no GitHub token (local development)
the scraper runs as a subprocess instead.
"""
from __future__ import annotations

import subprocess
import sys

import httpx

from core import config
from core.repo import Repo

MODES = {"match": "match", "check_now": "single"}
WORKFLOW = "check.yml"


class JobError(Exception):
    pass


def start_job(repo: Repo, kind: str, job_input: dict | None = None) -> dict:
    job = repo.insert_job(kind, job_input)
    token, repo_name = config.get("GITHUB_TOKEN"), config.get("GITHUB_REPO")
    if token and repo_name:
        response = httpx.post(
            f"https://api.github.com/repos/{repo_name}/actions/workflows/{WORKFLOW}/dispatches",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            json={"ref": config.get("GITHUB_REF", "main"),
                  "inputs": {"mode": MODES[kind], "job_id": str(job["id"])}},
            timeout=20,
        )
        if response.status_code >= 300:
            repo.update_job(job["id"], status="failed", result={"error": f"GitHub said {response.status_code}"})
            raise JobError(f"Could not start the job (GitHub returned {response.status_code}).")
    else:
        subprocess.Popen([sys.executable, "-m", "scraper.run", MODES[kind], "--job-id", str(job["id"])])
    return job

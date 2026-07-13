# Dependency Management

[English](dependency_management.md) | [Русский](../ru/dependency_management.md)

## Supported Lock

Python 3.12 is the canonical reproducible environment for local development,
CI, release validation, and Docker. Direct requirement files describe allowed
version ranges; `constraints-py312.txt` records the reviewed, exact resolver
result for core, offline transcription, optional diarization, documentation,
and development tools.

| Group | File | Included by default |
|---|---|---|
| Core API/RAG | `requirements.txt` | Yes |
| Offline ASR | `requirements-transcription.txt` | Product install and image |
| Development/audit | `requirements-dev.txt` | Development and CI only |
| Browser UI smoke | `requirements-browser.txt` | Dedicated CI/local browser tests |
| Live/Vosk | `requirements-live.txt` | Optional isolated runtime |
| Diarization | `requirements-diarization.txt` | Optional image/environment |
| GigaAM | `requirements-gigaam.txt` | Optional isolated Python environment |

Create a product environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements.txt -r requirements-transcription.txt
.\.venv\Scripts\python.exe -m pip check
```

For development:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements-dev.txt
```

For browser-level product UI tests, install the test-only library and Chromium:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\browser -q
```

## Updating The Lock

Update direct ranges first, then regenerate with Python 3.12:

```powershell
py -3.12 -m venv .venv-lock
.\.venv-lock\Scripts\python.exe -m pip install "pip-tools==7.5.3"
.\.venv-lock\Scripts\python.exe -m piptools compile --resolver=backtracking --strip-extras --allow-unsafe `
  --output-file constraints-py312.txt requirements-lock-py312.in
.\.venv\Scripts\python.exe scripts\47_dependency_audit.py
```

Review the complete lock diff and run the canonical test suite before merging.
Do not hand-edit one transitive pin without checking the complete resolver.

## Advisory Policy

The scheduled and release workflows run `pip-audit` against the exact pinned
graph. The audit fails on known vulnerabilities and collection errors. The
audit child process always uses UTF-8 I/O, so Windows checkouts under non-ASCII
user profiles produce the same result as CI without changing the parent shell.
An exception is allowed only in `security/dependency-audit-exceptions.json`
with:

- a CVE, GHSA, or PYSEC identifier;
- a concrete justification;
- a repository issue tracking remediation;
- an ISO expiry date.

Expired, duplicate, malformed, or undocumented exceptions fail closed. There
are currently no active exceptions. `pip-audit` detects known package
advisories; it is not malware detection or a substitute for code review.

Optional diarization is resolved in `constraints-py312.txt`, but it is installed
only when explicitly requested. GigaAM and live audio remain outside this lock
because their Torch/audio wheels and device bindings are platform-specific. Keep
those environments isolated, apply their bounded direct requirement files, run
`pip check`, and audit the resulting environment before deployment.

Primary references: [pip-audit](https://github.com/pypa/pip-audit),
[pip-tools](https://pip-tools.readthedocs.io/en/stable/), and
[GitHub Dependabot](https://docs.github.com/en/code-security/dependabot).

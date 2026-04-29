# Security Review

## Initial Assessment

### 1. Hardcoded Secrets
- **Risk:** High
- **Issue:** The repository might contain default tokens or passwords.
- **Affected File:** `.env.example`, `docker-compose.yml`
- **Recommended Fix:** Ensure `SECRET_KEY`, `NEO4J_PASSWORD`, and tokens are blank or explicitly marked as `<YOUR_SECRET>` in examples. Use dynamic generation in docs.
- **Status:** Resolved

### 2. Network Exposure
- **Risk:** Medium
- **Issue:** Docker compose services might bind to `0.0.0.0` exposing ports unnecessarily.
- **Affected File:** `docker-compose.yml`, `backend/run.py`
- **Recommended Fix:** Bind to `127.0.0.1` by default unless explicitly configured otherwise via `FLASK_HOST`.
- **Status:** Resolved

### 3. Unvalidated Inputs & SSRF
- **Risk:** High
- **Issue:** The backend fetches URLs and parses PDFs. `web_tools.py` has some protections but needs full review.
- **Affected File:** `backend/app/services/web_tools.py`, `backend/app/api/`
- **Recommended Fix:** Enforce strict URL validation. Rate limit document parsing. Validate all API payloads.
- **Status:** Open

### 4. Command Injection
- **Risk:** High
- **Issue:** Subprocess execution for OASIS simulations might be vulnerable if parameters are unescaped.
- **Affected File:** `backend/app/services/simulation_runner.py`, `backend/scripts/run_parallel_simulation.py`
- **Recommended Fix:** Ensure `subprocess.run` uses list formats, not `shell=True`. Validate arguments.
- **Status:** Resolved

### 5. CORS Configuration
- **Risk:** Medium
- **Issue:** Unrestricted CORS could allow cross-site requests.
- **Affected File:** `backend/app/__init__.py`
- **Recommended Fix:** Lock CORS down to `localhost` and configured origins. (Partially implemented in `security-hardening.md`).
- **Status:** Open

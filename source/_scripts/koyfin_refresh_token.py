#!/usr/bin/env python3
"""
Koyfin Token Auto-Refresh from Chrome Cookies (macOS)

Reads the Koyfin refresh_token from Chrome's encrypted cookie store
and updates the token JSON files for both Inspection Intel and Gaming Intel.

Chrome must be logged into app.koyfin.com. Each time you visit Koyfin
in Chrome, Chrome stores a fresh 30-day refresh_token cookie. This script
extracts that cookie and saves it so the transcript downloaders can use it.

Usage:
  python3 koyfin_refresh_token.py              # Extract and save token
  python3 koyfin_refresh_token.py --check      # Just check if token is valid
  python3 koyfin_refresh_token.py --dry-run    # Extract but don't save

Requirements:
  pip3 install cryptography
"""

import os, sys, json, re, shutil, tempfile, hashlib, sqlite3, argparse, base64, subprocess
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# All token files to update. Add additional paths here if you maintain
# multiple sector projects that share a Koyfin session.
TOKEN_FILES = [
    os.path.join(SCRIPT_DIR, "koyfin_token.json"),
]

CHROME_COOKIE_DB = os.path.expanduser(
    "~/Library/Application Support/Google/Chrome/Default/Cookies"
)


def get_chrome_key():
    """Get Chrome's AES encryption key from the macOS Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: Could not access Chrome Safe Storage in Keychain.")
        print("You may need to grant access in System Preferences > Security & Privacy.")
        sys.exit(1)
    password = result.stdout.strip()
    return hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), b"saltysalt", 1003, dklen=16)


def extract_cookie(aes_key):
    """Extract and decrypt the Koyfin refresh_token from Chrome's cookie DB."""
    if not os.path.exists(CHROME_COOKIE_DB):
        print("ERROR: Chrome cookie database not found.")
        print(f"Expected at: {CHROME_COOKIE_DB}")
        sys.exit(1)

    # Copy DB and WAL/journal files to avoid Chrome's file lock
    # Chrome uses SQLite WAL mode — recent cookies may only be in the WAL file
    tmp = os.path.join(tempfile.gettempdir(), "cookies_koyfin_extract.db")
    shutil.copy2(CHROME_COOKIE_DB, tmp)
    for suffix in ["-wal", "-journal", "-shm"]:
        src = CHROME_COOKIE_DB + suffix
        if os.path.exists(src):
            shutil.copy2(src, tmp + suffix)

    tmp_files = [tmp] + [tmp + s for s in ["-wal", "-journal", "-shm"]]

    try:
        conn = sqlite3.connect(tmp)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT encrypted_value FROM cookies
            WHERE host_key = '.koyfin.com' AND name = 'refresh_token'
        """)
        row = cursor.fetchone()
        conn.close()
    finally:
        for f in tmp_files:
            if os.path.exists(f):
                os.unlink(f)

    if not row:
        return None

    encrypted = row[0]
    if encrypted[:3] != b"v10":
        print(f"ERROR: Unexpected cookie encryption format: {encrypted[:3]}")
        sys.exit(1)

    # Decrypt AES-CBC (v10 format on macOS)
    data = encrypted[3:]
    iv = b" " * 16
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(data) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    # Extract JWT from decrypted bytes
    text = decrypted.decode("latin-1")
    match = re.search(r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", text)
    if not match:
        print("ERROR: Could not find JWT in decrypted cookie value.")
        sys.exit(1)

    return match.group(1)


def decode_jwt(token):
    """Decode JWT payload without verifying signature."""
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    return json.loads(base64.b64decode(payload_b64))


def save_token(token, exp_date, filepath):
    """Save token to a JSON file. Detects existing format (token vs refresh_token key)."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # Detect which key format this project uses
    key_name = "refresh_token"
    if os.path.exists(filepath):
        try:
            with open(filepath) as f:
                existing = json.load(f)
            if "token" in existing and "refresh_token" not in existing:
                key_name = "token"
        except:
            pass
    data = {key_name: token, "expires": exp_date, "updated": datetime.now().isoformat()}
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Auto-refresh Koyfin token from Chrome cookies")
    parser.add_argument("--check", action="store_true", help="Only check current token status")
    parser.add_argument("--dry-run", action="store_true", help="Extract token but don't save")
    args = parser.parse_args()

    # Check mode: just validate the stored token
    if args.check:
        for tf in TOKEN_FILES:
            if os.path.exists(tf):
                with open(tf) as f:
                    data = json.load(f)
                expires = data.get("expires", "unknown")
                if expires != "unknown":
                    exp_dt = datetime.strptime(expires[:10], "%Y-%m-%d")
                    days_left = (exp_dt - datetime.now()).days
                    status = "OK" if days_left > 3 else ("EXPIRING" if days_left > 0 else "EXPIRED")
                    print(f"  {tf}")
                    print(f"    Status: {status} (expires {expires}, {days_left} days left)")
                else:
                    print(f"  {tf}: unknown expiration")
            else:
                print(f"  {tf}: NOT FOUND")
        return

    # Check if existing token is still valid (skip extraction if > 7 days remaining)
    primary_token = TOKEN_FILES[0]
    if os.path.exists(primary_token):
        with open(primary_token) as f:
            existing = json.load(f)
        exp = existing.get("expires", "")
        if exp:
            days_left = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
            if days_left > 7:
                print(f"Koyfin token still valid ({days_left} days left). Skipping Chrome extraction.")
                # Propagate to other projects if their token is older/missing
                token_val = existing.get("refresh_token", existing.get("token", ""))
                if token_val:
                    for tf in TOKEN_FILES[1:]:
                        needs_update = True
                        if os.path.exists(tf):
                            try:
                                with open(tf) as f2:
                                    other = json.load(f2)
                                if other.get("refresh_token", other.get("token", "")) == token_val:
                                    needs_update = False
                            except Exception:
                                pass
                        if needs_update:
                            save_token(token_val, exp, tf)
                            project = os.path.basename(os.path.dirname(os.path.dirname(tf)))
                            print(f"  {project}: updated")
                return

    # Extract token from Chrome
    print("Extracting Koyfin token from Chrome cookies...")
    aes_key = get_chrome_key()
    token = extract_cookie(aes_key)

    if token is None:
        # Chrome doesn't have the cookie — check if existing token still has time
        if os.path.exists(primary_token):
            try:
                with open(primary_token) as f:
                    existing = json.load(f)
                exp = existing.get("expires", "")
                if exp:
                    days_left = (datetime.strptime(exp[:10], "%Y-%m-%d") - datetime.now()).days
                    if days_left > 2:
                        print(f"WARNING: Koyfin refresh_token cookie not found in Chrome.")
                        print(f"WARNING: Existing token expires in {days_left} days ({exp[:10]}).")
                        print(f"WARNING: Log into app.koyfin.com in Chrome to refresh before it expires.")
                        sys.exit(0)
            except Exception:
                pass
        print("ERROR: Koyfin refresh_token cookie not found in Chrome.")
        print("Make sure you are logged into app.koyfin.com in Chrome.")
        sys.exit(1)

    payload = decode_jwt(token)

    exp_ts = payload.get("exp", 0)
    exp_date = datetime.fromtimestamp(exp_ts)
    exp_str = exp_date.strftime("%Y-%m-%d")
    days_left = (exp_date - datetime.now()).days
    email = payload.get("email", "unknown")

    print(f"  Account: {email}")
    print(f"  Expires: {exp_str} ({days_left} days left)")

    if days_left < 1:
        print("  WARNING: Token is expired! Log into app.koyfin.com in Chrome first.")
        sys.exit(1)

    if args.dry_run:
        print(f"  Token: {token[:50]}...")
        print("  (dry run — not saving)")
        return

    # Save to all project token files
    updated = 0
    for tf in TOKEN_FILES:
        # Check if token changed (handle both key formats)
        if os.path.exists(tf):
            with open(tf) as f:
                existing_data = json.load(f)
            existing = existing_data.get("refresh_token", existing_data.get("token", ""))
            if existing == token:
                print(f"  {os.path.basename(os.path.dirname(os.path.dirname(tf)))}: already current")
                continue

        save_token(token, exp_str, tf)
        project = os.path.basename(os.path.dirname(os.path.dirname(tf)))
        print(f"  {project}: updated")
        updated += 1

    if updated == 0:
        print("  All token files already current.")
    else:
        print(f"  {updated} token file(s) updated.")


if __name__ == "__main__":
    main()

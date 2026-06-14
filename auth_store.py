import hashlib, json, os

USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

def _load_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def verify_user(username: str, password: str):
    """Return user dict if credentials match, else None."""
    users = _load_users()
    pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    for u in users:
        if u["username"] == username and u["password_hash"] == pw_hash:
            return {"username": u["username"], "display_name": u["display_name"]}
    return None

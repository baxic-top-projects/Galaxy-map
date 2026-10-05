from pathlib import Path

path = Path("/etc/nginx/sites-available/default")
text = path.read_text()
old = """        auth_basic "Kubernetes UI";
        auth_basic_user_file /etc/nginx/.htpasswd-k8s;
"""
if old not in text:
    raise SystemExit("basic auth block for k8s not found")
path.write_text(text.replace(old, "", 1))
print("removed k8s basic auth")

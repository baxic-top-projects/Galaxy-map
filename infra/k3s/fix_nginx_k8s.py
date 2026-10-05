from pathlib import Path

backup = Path("/etc/nginx/sites-available/default.bak-k8s")
target = Path("/etc/nginx/sites-available/default")
text = backup.read_text() if backup.exists() else target.read_text()

old = "server_name airflow.baxic.ru mlflow.baxic.ru stormmodel.baxic.ru;"
new = "server_name airflow.baxic.ru mlflow.baxic.ru stormmodel.baxic.ru k8s.baxic.ru;"
if old in text:
    text = text.replace(old, new, 1)
elif "k8s.baxic.ru" not in text:
    raise SystemExit("could not update listen-80 server_name")

block = """
server {
    listen 443 ssl http2;
    server_name k8s.baxic.ru;
    # Temporary cert (airflow SAN/path) until DNS A points to this VPS and certbot runs for k8s.baxic.ru
    ssl_certificate /etc/letsencrypt/live/airflow.baxic.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/airflow.baxic.ru/privkey.pem;
    client_max_body_size 32m;
    location / {
        auth_basic "Kubernetes UI";
        auth_basic_user_file /etc/nginx/.htpasswd-k8s;
        proxy_pass http://127.0.0.1:30446;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
"""

if "proxy_pass http://127.0.0.1:30446" not in text:
    text = text.rstrip() + "\n" + block + "\n"

target.write_text(text)
print("ok")

from pathlib import Path
p = Path("/etc/nginx/sites-available/default")
text = p.read_text()
# add domain to http redirect server_name
old = "server_name airflow.baxic.ru mlflow.baxic.ru stormmodel.baxic.ru;"
new = "server_name airflow.baxic.ru mlflow.baxic.ru stormmodel.baxic.ru k8s.baxic.ru;"
if "k8s.baxic.ru" not in text:
    if old not in text:
        raise SystemExit("redirect server_name line not found")
    text = text.replace(old, new, 1)
block = '''
server {
    listen 443 ssl http2;
    server_name k8s.baxic.ru;
    ssl_certificate /etc/letsencrypt/live/k8s.baxic.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/k8s.baxic.ru/privkey.pem;
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
'''
if "server_name k8s.baxic.ru;" not in text.split("listen 443")[-1] if False else "server_name k8s.baxic.ru;" not in text or "proxy_pass http://127.0.0.1:30446" not in text:
    # insert before trailing comments at end
    if "proxy_pass http://127.0.0.1:30446" not in text:
        text = text.rstrip() + "\n" + block + "\n"
p.write_text(text)
print("nginx default updated")
# Galaxy Map

Интерактивная 3D-карта вселенной EfolsMiradinsPact на Svelte 5 и Three.js.

Проект отображает звёздные системы, планеты, чёрные дыры, стыки
гиперкоридоров, политические территории и космические штормы. Карта публичная,
а изменение принадлежности систем доступно только пользователям с ролью
`ADMIN`.

## Возможности

- интерактивная 3D-карта галактики;
- динамические территории вокруг звёзд, чёрных дыр и стыков гиперкоридоров;
- пересчёт границ и подписей после смены владельца;
- детальный просмотр систем, планет, спутников и особенностей;
- поиск систем и миров;
- симуляция космических штормов через Kafka и WebSocket;
- модели и текстуры в S3-совместимом хранилище;
- регистрация, подтверждение email и восстановление пароля;
- JWT access + rotating refresh token;
- вход через Google OAuth;
- роли `USER` и `ADMIN`;
- профиль пользователя и аватары в S3;
- ADMIN-only управление территориями и назначение администраторов.

## Стек

### Клиент

- Svelte 5
- Vite
- Three.js
- Vitest

### Backend

- Python 3.12
- FastAPI
- SQLAlchemy 2
- PostgreSQL / Neon
- Redis
- Kafka
- WebSocket
- PyJWT + Argon2
- MailDev SMTP relay
- Yandex Object Storage / S3

## Микросервисы

- `client` — Svelte-приложение, порт `9999`;
- `api-gateway` — публичный REST/WebSocket API, порт `9998`;
- `auth-service` — пользователи, JWT, Google OAuth и роли, внутренний порт `8004`;
- `catalog-service` — каталог систем и политическая принадлежность, внутренний порт `8003`;
- `asset-service` — модели и текстуры из S3, внутренний порт `8002`;
- `storm-service` — симуляция штормов, внутренний порт `8001`;
- `smtp-service-galaxy` — MailDev и relay на внешний SMTP, UI `8186`;
- `redis` — кэш каталога;
- `kafka` — события симуляции.

## Быстрый запуск

Требования:

- Docker;
- Docker Compose;
- Git LFS для исходных 3D-ассетов.

Настройте сервисы согласно документации в их директориях.

Запуск:

```bash
docker compose up -d --build
```

После запуска:

- карта: <http://localhost:9999>
- API: <http://localhost:9998>
- MailDev: <http://localhost:8186>

Проверка состояния:

```bash
docker compose ps
curl http://localhost:9998/health
```

## Авторизация

Подробная документация:

[`server/services/auth-service/README.md`](server/services/auth-service/README.md)

Основной поток:

1. пользователь регистрируется или входит через Google;
2. auth-service сохраняет пользователя в PostgreSQL с ролью `USER`;
3. access JWT возвращается клиенту;
4. refresh JWT хранится в `HttpOnly` cookie и ротируется при обновлении;
5. API Gateway проверяет роль `ADMIN` перед изменением владельца системы.

Карта и чтение каталога доступны без входа.

### Первый администратор

Зарегистрируйте пользователя, затем выполните в auth-базе:

```sql
UPDATE auth_users
SET role = 'ADMIN', updated_at = NOW()
WHERE email = 'your-email@example.com';
```

После повторного входа в меню пользователя появится страница управления ролями.

## Google OAuth

В Google Cloud Console создайте OAuth Client типа **Web application**.

Production redirect URI:

```text
https://galaxyapi.example.com/api/v1/auth/google/callback
```

Локальный redirect URI:

```text
http://localhost:9998/api/v1/auth/google/callback
```

## SMTP

Auth-service отправляет письма на MailDev по внутреннему SMTP. MailDev
пересылает их через настроенный внешний сервер.

Для внутреннего соединения auth-service → MailDev логин и пароль не нужны.

## S3

Asset-service хранит игровые модели и текстуры. Auth-service хранит аватары.

Поддерживаются PNG, JPEG и WebP до 5 МБ.

## Локальная разработка

Клиент:

```bash
cd client
npm install
npm run dev
```

Auth-service:

```bash
cd server/services/auth-service
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8004
```

Остальные FastAPI-сервисы запускаются аналогично из своих директорий.

## Тесты и сборка

Клиент:

```bash
cd client
npm test -- --run
npm run build
```

Backend:

```bash
cd server/services/auth-service && python -m pytest -q
cd server/services/catalog-service && python -m pytest -q
cd server/api-gateway && python -m pytest -q
```

Docker Compose:

```bash
docker compose config --quiet
```

## GitHub Actions

Секреты, пароли, OAuth client secret и S3-ключи хранятся в GitHub Secrets и
не должны попадать в Git.

Запуск публикации выполняется через `workflow_dispatch`.

## Данные галактики

Исходный канон находится в соседнем репозитории `EfolsMiradinsPact`.

Основные инструменты:

```bash
python tools/export_galaxy.py
python tools/build_visual_ownership.py
python tools/sync_efols_polity_systems.py --apply
```

Экспортированные данные загружаются в catalog-service и затем выдаются через
API Gateway.

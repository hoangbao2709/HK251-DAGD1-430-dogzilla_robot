# HK251-DAGD1-430 Dogzilla Robot

Ung dung web dieu khien va giam sat robot Dogzilla. Du an nay gom backend
Django va frontend Next.js: backend lam lop API trung gian voi robot, frontend
cung cap giao dien dieu khien, camera, ban do, patrol va analytics.

## Thanh phan chinh

```text
backend/   Django REST API
frontend/  Next.js web UI
```

Backend phu trach ket noi robot, forward lenh dieu khien, doc trang thai,
camera, SLAM/navigation data, ghi su kien va tong hop metric.

Frontend la giao dien nguoi dung de connect robot, dieu khien tay, xem FPV,
quan ly diem tren ban do, chay patrol va theo doi analytics.

```bash
git status
```

## Khoi dong backend

Cai Python dependencies:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOW_ALL_ORIGINS=True
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

ROBOT_SERVER_BASE_URL=http://127.0.0.1:9000
ROBOT_IP=127.0.0.1
ROBOT_PORT=9000
MAP_SERVER_PORT=8080
ROBOT_TIMEOUT=5

OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
```

Sau khi cai requirements va co `backend/.env`:

```bash
python manage.py check
python manage.py runserver 0.0.0.0:8000
```

Backend mac dinh chay o:

```text
http://127.0.0.1:8000
```

## Khoi dong frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend mac dinh chay o:

```text
http://localhost:3000
```

Neu backend khong chay o dia chi mac dinh, set bien moi truong cho frontend:

```text
NEXT_PUBLIC_API_BASE=http://<backend-host>:8000
```

## Su dung nhanh

1. Chay backend.
2. Chay frontend.
3. Mo frontend tren browser.
4. Connect robot bang dia chi robot server.
5. Dieu khien robot, xem camera/map, chay autonomous hoac xem analytics.

## Ghi chu phat trien

- API client cua frontend nam o `frontend/app/lib/robotApi.ts`.
- Route backend chinh nam o `backend/control/urls.py`.
- Logic forward lenh robot nam o `backend/control/services/ros.py`.
- Khong commit file sinh ra nhu `__pycache__/`, `*.pyc`, SQLite journal.

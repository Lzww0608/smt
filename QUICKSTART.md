# QUICKSTART

This document is the fastest path to run the complete SMT system on Linux.

The target architecture is:

`Vue -> Spring Boot -> Python SMT backend`

## 1. Prepare Runtime Environment

Install and verify:

- Python `3.10` or newer
- Java `17`
- Maven `3.8+`
- Node.js `18+`
- npm `9+`
- MySQL `8.x`

Quick version check:

```bash
python3.10 --version
java -version
mvn -v
node -v
npm -v
mysql --version
```

## 2. Prepare Database

Spring Boot expects MySQL database `lzw`.

Current datasource defaults are defined in `springboot02/src/main/resources/application.yml`:

```yml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/lzw?useSSL=false&useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai
    username: root
    password: 1234580
```

Important:

- this repository currently does not include a ready-to-run SQL initialization script
- you must create the database and import/create these tables yourself:
  - `users`
  - `chat_session`
  - `chat_message`
  - `optimize_record`

## 3. Start Python SMT Backend

From the repository root:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Check `.env` in the repository root. At minimum, confirm:

- `LLM_API_KEY`
- `LLM_API_BASE_URL`
- `LLM_MODEL`
- `APP_HOST`
- `APP_PORT`

Start the service:

```bash
./start_backend.sh 0.0.0.0 8000
```

Quick health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected result:

```json
{"status":"ok"}
```

## 4. Start Spring Boot

Open a new terminal and go to:

```bash
cd springboot02
```

Start Spring Boot:

```bash
mvn spring-boot:run
```

Spring Boot depends on both:

- MySQL
- Python SMT backend

If either one is not ready, `/send` or `/optimizeCode` will fail.

## 5. Start Vue Frontend

Open a new terminal and go to:

```bash
cd vueProject/my-vue-app
```

Optional frontend env:

```bash
echo 'VITE_API_BASE_URL=http://localhost:8080' > .env.local
```

Install and run:

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open:

```text
http://localhost:5173
```

## 6. Verify The Full Chain

Use the system in this order:

1. login or register in the frontend
2. create a chat session
3. send a natural-language SMT request
4. confirm a system SMT reply appears
5. click optimize on that SMT reply
6. confirm an optimization record appears

If this succeeds, then the full chain is working:

`Vue -> Spring Boot -> Python SMT backend -> Spring Boot -> MySQL`

## 7. Default Ports

- Vue: `5173`
- Spring Boot: `8080`
- Python SMT backend: `8000`
- MySQL: `3306`

## 8. Fast Troubleshooting

### Vue opens but cannot login

Check:

- Spring Boot is running
- MySQL is running
- `VITE_API_BASE_URL` points to `http://localhost:8080`

### Login works but send fails

Check:

- Python SMT backend is running on `8000`
- root `.env` has a valid LLM API key
- Spring Boot can reach `http://127.0.0.1:8000/api/v1/smt/transform`

### Send works but optimize fails

Check:

- target system message exists in `chat_message`
- `optimize_record` table exists
- Python backend has `z3-solver` installed

### Spring Boot starts but frontend requests fail

Check:

- Spring Boot CORS allows the frontend origin
- frontend is calling `http://localhost:8080`

## 9. Related Documents

- [README.md](README.md)
- [springboot02/README.md](springboot02/README.md)

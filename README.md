# SMT System

This repository contains a complete three-layer SMT system.

The current runtime architecture is:

`Vue (Vite, 5173) -> Spring Boot (8080) -> Python SMT backend (8000)`

If you only want the fastest Linux bring-up path, start with [QUICKSTART.md](QUICKSTART.md).

## Components

- `vueProject/my-vue-app`
  Frontend UI built with Vue 3 + Vite + Element Plus.
- `springboot02`
  Middle layer responsible for user/session/message/optimization-record persistence and for calling the Python SMT backend.
- `app`
  Python SMT service responsible for SMT generation, SMT optimization, Z3 validation, repair workflow, and equivalence/UNSAT-core analysis.

## Repository Structure

```text
.
├─ app/
├─ springboot02/
├─ vueProject/
│  └─ my-vue-app/
├─ requirements.txt
├─ start_backend.ps1
├─ start_backend.sh
├─ README.md
└─ QUICKSTART.md
```

All paths in this document are repository-relative paths.

## Environment Requirements

To run the full stack on Linux, prepare all of the following.

### Python SMT backend

- Python `3.10+`
- recommended version: `3.10.19`
- `pip`
- `venv`

Python dependencies are pinned in [requirements.txt](requirements.txt).

### Spring Boot backend

- Java `17`
- Maven `3.8+`
- MySQL `8.x`

Why:

- the current Spring Boot version is `3.0.2`
- Spring Boot `3.x` requires Java `17+`
- the current datasource driver is MySQL Connector/J `8.0.31`

### Vue frontend

- Node.js `18+`
- recommended version: `18 LTS` or `20 LTS`
- npm `9+`

Why:

- the frontend uses Vue `3.2.47`
- the build tool is Vite `4.2.0`
- this combination is stable on modern Node LTS versions

### Linux pre-check

Before deployment, verify the runtime versions:

```bash
python3.10 --version
java -version
mvn -v
node -v
npm -v
mysql --version
```

## Ports And CORS

Recommended local ports:

- Vue: `5173`
- Spring Boot: `8080`
- Python SMT backend: `8000`
- MySQL: `3306`

Current frontend base URL default:

- `vueProject/my-vue-app/axiosInstance.js`
- default target: `http://localhost:8080`
- override with `VITE_API_BASE_URL`

Current Spring Boot CORS default:

- `http://localhost:5173`
- `http://127.0.0.1:5173`

Current Python backend CORS default:

- `http://localhost:5173`
- `http://127.0.0.1:5173`

In the integrated architecture, the browser talks to Spring Boot only. Python CORS mainly matters when you test the Python API directly from a browser.

## Runtime Responsibilities

### Vue

Vue is responsible for:

- login/register UI
- chat UI
- admin UI
- optimization result display

Vue does not directly call the Python SMT backend in the integrated architecture.

### Spring Boot

Spring Boot is the entry point for the browser.

It is responsible for:

- users
- chat sessions
- chat messages
- optimization records
- forwarding SMT generation and SMT optimization requests to the Python service

### Python SMT backend

The Python service is the SMT engine.

It is responsible for:

- natural-language-to-SMT generation
- SMT redundancy reduction
- Z3 validation
- automatic repair workflow
- SAT equivalence checking
- counterexample-guided repair
- UNSAT-core-guided optimization

The Python service does not directly read or write MySQL in the current design.

## Database

Spring Boot currently expects MySQL configuration from `springboot02/src/main/resources/application.yml`.

Current local defaults:

```yml
spring:
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
    url: jdbc:mysql://localhost:3306/lzw?useSSL=false&useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai
    username: root
    password: 1234580
```

This means:

- host: `localhost`
- port: `3306`
- database: `lzw`
- username: `root`
- password: `1234580`

For real deployment, change these credentials before use.

### Required tables

The current Spring Boot code maps to these tables:

#### `users`

```text
id
email
password
create_time
user_type
```

`user_type` meaning:

- `0`: normal user
- `1`: admin user

#### `chat_session`

```text
id
user_id
title
last_message
create_time
update_time
is_deleted
```

#### `chat_message`

```text
id
session_id
sender_type
content
message_type
create_time
```

#### `optimize_record`

```text
opt_id
message_id
original_code
optimized_code
create_time
```

### Important note

This repository currently does not include a ready-to-run SQL initialization script. You need to create/import the schema yourself before starting Spring Boot.

## Main Request Flows

### 1. Login and user management

`Vue -> Spring Boot -> MySQL`

Main APIs:

- `POST /login`
- `POST /register`
- `POST /updatePassword`
- `POST /deleteUser`
- `GET /users`

### 2. Chat / SMT generation

When a user submits natural language:

1. Vue calls Spring Boot `POST /send`
2. Spring Boot saves the user message into `chat_message`
3. Spring Boot calls Python `POST /api/v1/smt/transform` with `content_type=natural_language`
4. Python generates SMT and validates it
5. Spring Boot stores the returned SMT as a system message in `chat_message`
6. Vue reloads the conversation through `GET /messages`

Current message storage detail:

- user messages: `sender_type=user`
- Python-generated replies: `sender_type=system`
- Python-generated SMT replies: `message_type=smt_code`

### 3. SMT optimization

When a user clicks optimize on a system SMT message:

1. Vue calls Spring Boot `POST /optimizeCode`
2. Spring Boot resolves the optimization source in this order:
   - `originalCode` from the current request
   - latest `optimize_record.optimized_code`
   - current `chat_message.content`
3. Spring Boot calls Python `POST /api/v1/smt/transform` with `content_type=smt_code`
4. Python optimizes the SMT code
5. Spring Boot stores the optimized result in `optimize_record`
6. Vue reloads optimization history through `GET /optimizeRecords/byMessage`

## Startup Order

The correct startup order is:

1. MySQL
2. Python SMT backend
3. Spring Boot
4. Vue frontend

Reason:

- Spring Boot depends on MySQL
- Spring Boot also depends on the Python SMT backend for `/send` and `/optimizeCode`
- Vue depends on Spring Boot

## How To Run

### 1. Start MySQL

Make sure:

- the `lzw` database exists
- the required tables have been created
- the credentials in `springboot02/src/main/resources/application.yml` are correct

### 2. Start Python SMT backend

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
.\start_backend.ps1
```

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
./start_backend.sh 0.0.0.0 8000
```

At minimum, check `.env` for:

- `LLM_API_KEY`
- `LLM_API_BASE_URL`
- `LLM_MODEL`
- `APP_HOST`
- `APP_PORT`

Health check:

```text
GET http://127.0.0.1:8000/health
```

### 3. Start Spring Boot

From `springboot02`:

```bash
cd springboot02
mvn spring-boot:run
```

Or run the main class:

```text
com.example.springboot02.Springboot02Application
```

Before starting Spring Boot, confirm:

- MySQL is already running
- the schema already exists
- Python SMT backend is already listening at `http://127.0.0.1:8000`
- Java version is `17`
- Maven is available in the shell

### 4. Start Vue

From `vueProject/my-vue-app`:

```bash
cd vueProject/my-vue-app
npm install
npm run dev
```

Optional frontend env:

```text
VITE_API_BASE_URL=http://localhost:8080
```

The Vite dev server is usually:

```text
http://localhost:5173
```

## Integrated API Mapping

Vue mainly uses these Spring Boot endpoints:

- `POST /login`
- `POST /register`
- `POST /updatePassword`
- `GET /users`
- `POST /deleteUser`
- `GET /sessions`
- `GET /allSessions`
- `POST /session`
- `GET /messages`
- `POST /send`
- `POST /delete`
- `GET /optimizeRecords`
- `GET /optimizeRecords/byMessage`
- `POST /optimizeCode`
- `POST /deleteOptimizeRecord`

Spring Boot internally calls this Python endpoint:

- `POST /api/v1/smt/transform`

Spring Boot sends JSON like this:

```json
{
  "content": "user input or smt code",
  "content_type": "natural_language or smt_code"
}
```

## Troubleshooting

### Vue opens but login/history fails

Check:

- Spring Boot is running on `8080`
- `VITE_API_BASE_URL` points to the correct Spring Boot address
- MySQL is running and the `lzw` database is reachable

### Login works but send/optimize fails

Check:

- Python SMT backend is running on `8000`
- Spring Boot `smt.backend.base-url` points to the correct Python backend
- Python `.env` contains a valid LLM API key
- `z3-solver` is installed in the Python environment

### Spring Boot starts but chat/optimization still fails

Check:

- the target system message exists in `chat_message`
- the `optimize_record` table exists
- Spring Boot can reach Python `POST /api/v1/smt/transform`

## Key Paths

- [QUICKSTART.md](QUICKSTART.md)
- [requirements.txt](requirements.txt)
- [springboot02/src/main/resources/application.yml](springboot02/src/main/resources/application.yml)
- [springboot02/src/main/java/com/example/springboot02/service/SmtTransformClient.java](springboot02/src/main/java/com/example/springboot02/service/SmtTransformClient.java)
- [springboot02/src/main/java/com/example/springboot02/service/Impl/ChatServiceImpl.java](springboot02/src/main/java/com/example/springboot02/service/Impl/ChatServiceImpl.java)
- [springboot02/src/main/java/com/example/springboot02/service/Impl/OptimizeRecordServiceImpl.java](springboot02/src/main/java/com/example/springboot02/service/Impl/OptimizeRecordServiceImpl.java)
- [vueProject/my-vue-app/axiosInstance.js](vueProject/my-vue-app/axiosInstance.js)
- [app/api/routes.py](app/api/routes.py)
- [app/services/workflow.py](app/services/workflow.py)

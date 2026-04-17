# SMT System

This repository is now an integrated system, not just a standalone Python service.

The actual request chain is:

`Vue (vite, 5173) -> Spring Boot (8080) -> Python SMT service (8000)`

The responsibilities are split as follows:

- `vueProject/my-vue-app`: frontend UI, login page, chat page, admin page, optimize result display.
- `springboot02`: user management, session management, chat history, optimize record persistence, and HTTP bridge to the Python SMT service.
- `app/`: Python SMT service, responsible for SMT generation, SMT redundancy reduction, LLM workflow, Z3 validation, repair, equivalence checking, and optimization workflow.

## Architecture

### 1. Frontend

The frontend uses Vue 3 + Vite + Element Plus.

- Default dev server: `http://localhost:5173`
- Backend base URL is configured in `vueProject/my-vue-app/axiosInstance.js`
- Current default frontend target: `http://localhost:8080`
- You can override it with `VITE_API_BASE_URL`

Current frontend behavior:

- Login and register through Spring Boot
- Create and delete chat sessions through Spring Boot
- Send natural language questions through Spring Boot
- View chat history from Spring Boot
- Trigger code optimization through Spring Boot
- Read optimization records from Spring Boot
- Open the admin page through Spring Boot-backed APIs

The browser does not directly call the Python SMT service in the integrated setup.

### 2. Spring Boot middle layer

Spring Boot is the system entry point for the frontend.

It handles:

- user accounts
- chat sessions
- chat messages
- optimization records
- forwarding SMT requests to the Python backend

Current runtime assumptions:

- Java: `17`
- Spring Boot: `3.0.2`
- MySQL driver: `8.0.31`
- default HTTP port: `8080`

Current Python bridge config is in `springboot02/src/main/resources/application.yml`:

```yml
smt:
  backend:
    base-url: http://127.0.0.1:8000
    transform-path: /api/v1/smt/transform
    connect-timeout-seconds: 10
    read-timeout-seconds: 120
```

This means:

- Vue sends requests to Spring Boot
- Spring Boot sends SMT generation and SMT optimization requests to the Python backend
- Python returns the SMT result
- Spring Boot stores the result into MySQL when needed

### 3. Python SMT backend

The Python service is the SMT engine of the system.

Current runtime assumptions:

- Python: `3.10+` recommended `3.10.19`
- default HTTP port: `8000`
- main API: `POST /api/v1/smt/transform`

Current request modes:

- `content_type = natural_language`: generate SMT from natural language
- `content_type = smt_code`: optimize and reduce redundancy in SMT code
- `content_type = auto`: heuristic detection

The Python service does not use MySQL in the current architecture. It is stateless with respect to user/session storage. Persistence is handled by Spring Boot.

## Real request flow

### 1. Login and user management

Vue calls Spring Boot directly:

- `POST /login`
- `POST /register`
- `POST /updatePassword`
- `POST /deleteUser`
- `GET /users`

These requests read and write the `users` table.

Admin recognition is currently based on `users.user_type`:

- `0`: normal user
- `1`: admin user

### 2. Chat flow

When the user sends a natural language question:

1. Vue calls Spring Boot `POST /send`
2. Spring Boot saves the user message into `chat_message`
3. Spring Boot calls Python `POST /api/v1/smt/transform` with `content_type=natural_language`
4. Python generates SMT, validates it, and returns the final SMT result
5. Spring Boot saves the returned SMT as a system message into `chat_message`
6. Vue reloads message history from Spring Boot `GET /messages`

Important detail:

- the saved system message content is the SMT result returned by Python
- Spring Boot currently stores that system reply with `sender_type=system`
- Spring Boot currently stores that system reply with `message_type=smt_code`

### 3. SMT optimization flow

When the user clicks optimize on a system SMT message:

1. Vue calls Spring Boot `POST /optimizeCode`
2. Spring Boot resolves the optimization source in this priority order:
   - `originalCode` from frontend request
   - latest `optimize_record.optimized_code` for that message
   - current `chat_message.content` of the target system message
3. Spring Boot calls Python `POST /api/v1/smt/transform` with `content_type=smt_code`
4. Python performs SMT redundancy reduction, validation, repair, and optimization workflow
5. Spring Boot saves the returned optimized SMT into `optimize_record`
6. Vue reads optimization history through `GET /optimizeRecords/byMessage`

This is the current actual architecture. Vue does not directly optimize through Python.

## Database

Spring Boot expects a MySQL database.

Current configuration in `springboot02/src/main/resources/application.yml` is:

```yml
spring:
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
    url: jdbc:mysql://localhost:3306/lzw?useSSL=false&useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai
    username: root
    password: 1234580
```

This means the local default assumptions are:

- host: `localhost`
- port: `3306`
- database: `lzw`
- user: `root`
- password: `1234580`

For a real deployment, you should change the MySQL account and password before use.

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

### Database responsibility split

- `users`, `chat_session`, `chat_message`, `optimize_record` are owned by Spring Boot
- Python SMT backend does not read or write MySQL directly

## Ports and CORS

Recommended local ports:

- Vue: `5173`
- Spring Boot: `8080`
- Python SMT backend: `8000`

Current CORS behavior:

- Spring Boot allows `http://localhost:5173,http://127.0.0.1:5173`
- Python backend also allows `http://localhost:5173,http://127.0.0.1:5173`

In the integrated architecture, the browser only needs Spring Boot CORS. Python CORS mainly matters if you test the Python API directly from a browser.

## Startup order

The correct startup order is:

1. MySQL
2. Python SMT backend
3. Spring Boot
4. Vue frontend

Reason:

- Spring Boot depends on MySQL
- Spring Boot also depends on Python SMT for `/send` and `/optimizeCode`
- Vue depends on Spring Boot

## How to run

### 1. Start MySQL

Make sure the `lzw` database exists and the required tables have been created.

### 2. Start Python SMT backend

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Configure `.env` for the Python service. At minimum, check:

- `LLM_API_KEY`
- `LLM_API_BASE_URL`
- `LLM_MODEL`
- `APP_HOST`
- `APP_PORT`

Run the Python service:

```powershell
.\start_backend.ps1
```

```bash
chmod +x ./start_backend.sh
./start_backend.sh 0.0.0.0 8000
```

Health check:

```text
GET http://127.0.0.1:8000/health
```

### 3. Start Spring Boot

Requirements:

- Java `17`
- Maven available in `PATH`

Spring Boot project path:

```text
springboot02
```

Start it with one of these methods:

```bash
cd springboot02
mvn spring-boot:run
```

or run the main class:

```text
com.example.springboot02.Springboot02Application
```

Before starting Spring Boot, confirm:

- MySQL is reachable with the credentials in `application.yml`
- Python SMT backend is already listening at `http://127.0.0.1:8000`

### 4. Start Vue

Frontend project path:

```text
vueProject/my-vue-app
```

Optional frontend env:

```text
VITE_API_BASE_URL=http://localhost:8080
```

Install and run:

```bash
cd vueProject/my-vue-app
npm install
npm run dev
```

Then open the Vite URL shown in the terminal, usually:

```text
http://localhost:5173
```

## Integrated API mapping

The integrated system currently uses these main Spring Boot endpoints from Vue:

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

The Spring Boot application currently calls this Python endpoint internally:

- `POST /api/v1/smt/transform`

Spring Boot sends:

```json
{
  "content": "user input or smt code",
  "content_type": "natural_language or smt_code"
}
```

## Python SMT features

The Python backend currently includes:

- natural-language-to-SMT generation
- SMT redundancy reduction
- Z3 syntax and solvability validation
- automatic repair loop
- verifier / reflection / repair multi-agent prompting
- SAT equivalence checking
- counterexample-guided repair
- UNSAT core guidance
- bounded multi-core sampling and intersection statistics
- MCTS-CORF-style deterministic optimization

## Troubleshooting

### Vue can open but cannot log in or load history

Check:

- Spring Boot is running on `8080`
- `VITE_API_BASE_URL` points to the right Spring Boot address
- MySQL is running and the `lzw` database is reachable

### Login works but send/optimize fails

Check:

- Python SMT backend is running on `8000`
- Spring Boot `smt.backend.base-url` points to the correct Python service
- Python `.env` has a valid LLM API key
- `z3-solver` is installed in the Python environment

### Spring Boot starts but chat/optimization still fails

Check:

- the target system message exists in `chat_message`
- `optimize_record` table exists
- Spring Boot can reach Python with `POST /api/v1/smt/transform`

## Key files

- [README.md](f:/Code/Project/smt/README.md)
- [springboot02/src/main/resources/application.yml](f:/Code/Project/smt/springboot02/src/main/resources/application.yml)
- [springboot02/src/main/java/com/example/springboot02/service/SmtTransformClient.java](f:/Code/Project/smt/springboot02/src/main/java/com/example/springboot02/service/SmtTransformClient.java)
- [springboot02/src/main/java/com/example/springboot02/service/Impl/ChatServiceImpl.java](f:/Code/Project/smt/springboot02/src/main/java/com/example/springboot02/service/Impl/ChatServiceImpl.java)
- [springboot02/src/main/java/com/example/springboot02/service/Impl/OptimizeRecordServiceImpl.java](f:/Code/Project/smt/springboot02/src/main/java/com/example/springboot02/service/Impl/OptimizeRecordServiceImpl.java)
- [vueProject/my-vue-app/axiosInstance.js](f:/Code/Project/smt/vueProject/my-vue-app/axiosInstance.js)
- [app/api/routes.py](f:/Code/Project/smt/app/api/routes.py)
- [app/services/workflow.py](f:/Code/Project/smt/app/services/workflow.py)

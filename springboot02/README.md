# springboot02

This module is the middle layer of the integrated SMT system.

The current runtime architecture is:

`Vue (5173) -> Spring Boot (8080) -> Python SMT backend (8000)`

If you need the full repository-level view, see [../README.md](../README.md). If you want the shortest Linux startup path, see [../QUICKSTART.md](../QUICKSTART.md).

## Module Responsibility

`springboot02` is responsible for:

- user login, registration, password update, and user management
- chat session creation, listing, and logical deletion
- chat message persistence
- optimization record persistence
- forwarding SMT generation and SMT optimization requests to the Python SMT backend

It is not the SMT engine itself. The Python service under `../app` is the SMT engine.

## Environment Requirements

To run this module in the full integrated system, prepare:

### Required for Spring Boot itself

- Java `17`
- Maven `3.8+`
- MySQL `8.x`

### Required because Spring Boot depends on them at runtime

- Python `3.10+` for the SMT backend
- recommended Python version: `3.10.19`
- Node.js `18+` and npm `9+` if you also want to run the Vue frontend

Why:

- current Spring Boot version is `3.0.2`
- Spring Boot `3.x` requires Java `17+`
- the current datasource driver is MySQL Connector/J `8.0.31`

### Linux pre-check

```bash
java -version
mvn -v
mysql --version
python3.10 --version
node -v
npm -v
```

## Runtime Position In The Full System

### Browser entry

Vue talks to Spring Boot, not directly to the Python SMT backend.

### Database entry

Spring Boot reads and writes MySQL.

### SMT bridge

Spring Boot calls the Python SMT backend at:

```text
http://127.0.0.1:8000/api/v1/smt/transform
```

The bridge config is in [src/main/resources/application.yml](src/main/resources/application.yml):

```yml
smt:
  backend:
    base-url: http://127.0.0.1:8000
    transform-path: /api/v1/smt/transform
    connect-timeout-seconds: 10
    read-timeout-seconds: 120
```

## Database

Spring Boot datasource config is in [src/main/resources/application.yml](src/main/resources/application.yml):

```yml
spring:
  datasource:
    type: com.alibaba.druid.pool.DruidDataSource
    driver-class-name: com.mysql.cj.jdbc.Driver
    url: jdbc:mysql://localhost:3306/lzw?useSSL=false&useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai
    username: root
    password: 1234580
```

Current local defaults:

- host: `localhost`
- port: `3306`
- database: `lzw`
- username: `root`
- password: `1234580`

For real deployment, replace these credentials.

### Required tables

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

## Main Controllers

### `LoginController`

Handles:

- `POST /login`
- `POST /register`
- `POST /updatePassword`
- `POST /deleteUser`
- `GET /users`

### `ChatController`

Handles:

- `GET /sessions`
- `GET /allSessions`
- `GET /messages`
- `POST /session`
- `POST /send`
- `POST /delete`

Current actual behavior of `/send`:

1. save user message
2. call Python SMT backend with `content_type=natural_language`
3. save returned SMT as a system message

This is no longer a placeholder reply path.

### `OptimizeRecordController`

Handles:

- `GET /optimizeRecords`
- `GET /optimizeRecords/byMessage`
- `POST /optimizeCode`
- `POST /deleteOptimizeRecord`

Current actual behavior of `/optimizeCode`:

1. resolve source SMT code
2. call Python SMT backend with `content_type=smt_code`
3. store optimized SMT into `optimize_record`

This is no longer a no-op optimization path.

## Request Flows

### Chat / SMT generation

`Vue -> Spring Boot /send -> Python /api/v1/smt/transform -> Spring Boot -> MySQL`

### SMT optimization

`Vue -> Spring Boot /optimizeCode -> Python /api/v1/smt/transform -> Spring Boot -> MySQL`

## Response Format

Spring Boot returns the unified `Result` wrapper:

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

Failure example:

```json
{
  "code": 500,
  "message": "error message",
  "data": null
}
```

Vue already normalizes this format in the current frontend implementation.

## CORS

Current allowed frontend origins are configured in [src/main/resources/application.yml](src/main/resources/application.yml) and used by [src/main/java/com/example/springboot02/config/CorsConfig.java](src/main/java/com/example/springboot02/config/CorsConfig.java):

- `http://localhost:5173`
- `http://127.0.0.1:5173`

## How To Run

Correct startup order:

1. MySQL
2. Python SMT backend
3. Spring Boot
4. Vue frontend

### Start Spring Boot

From `springboot02`:

```bash
mvn spring-boot:run
```

Or run the main class:

```text
com.example.springboot02.Springboot02Application
```

Before starting Spring Boot, confirm:

- MySQL is already running
- the `lzw` database exists
- the required tables already exist
- the Python SMT backend is already listening at `http://127.0.0.1:8000`

## Key Paths

- [pom.xml](pom.xml)
- [src/main/resources/application.yml](src/main/resources/application.yml)
- [src/main/java/com/example/springboot02/service/SmtTransformClient.java](src/main/java/com/example/springboot02/service/SmtTransformClient.java)
- [src/main/java/com/example/springboot02/service/Impl/ChatServiceImpl.java](src/main/java/com/example/springboot02/service/Impl/ChatServiceImpl.java)
- [src/main/java/com/example/springboot02/service/Impl/OptimizeRecordServiceImpl.java](src/main/java/com/example/springboot02/service/Impl/OptimizeRecordServiceImpl.java)
- [src/main/java/com/example/springboot02/config/CorsConfig.java](src/main/java/com/example/springboot02/config/CorsConfig.java)
- [../README.md](../README.md)
- [../QUICKSTART.md](../QUICKSTART.md)

## Consistency Note

This README has been synchronized with [../README.md](../README.md).

The authoritative runtime architecture is:

`Vue -> Spring Boot -> Python SMT backend`

# Agent Rules: springboot-mcp-server

> Rules every agent follows when working in this project.

## 1. Stack And Commands

This is Spring Boot 4.1 with Spring AI 2.0, built by Maven, targeting Java 17.

- **Build and test**: `mvn package`
- **Run**: `mvn spring-boot:run`, port 8002
- **JDK on this machine**: set `JAVA_HOME=C:/Users/darks.X-VOYAGER/.jdks/openjdk-25.0.1`.
  - `C:\Program Files\Java\jdk-17` exists but is empty, so the default `JAVA_HOME` fails.

## 2. Conventions

The contract is shared with `../fastapi-mcp-server`, so changes go to both.

- Keep business logic in `domain/NotesService.java`, free of MCP annotations.
- Expose each function through both `mcp/DemoMcpServer.java` and `web/RestApiController.java`.
- Keep tool names, argument names, and JSON keys identical to the Python server.
- Update `../README.md` tables when the contract or a difference changes.

## 3. Limits

- Import annotations from `org.springframework.ai.mcp.annotation`, the Spring AI 2.0 package.
- Configure MCP in `application.yml`, not hand-written transport beans.
- Keep port 8002; the client documents it as the alternative server.

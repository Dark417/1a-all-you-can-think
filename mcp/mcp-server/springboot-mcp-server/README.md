# Spring Boot MCP Server

> An MCP server built with Spring AI annotations on Spring Boot WebMVC.

## Index

- [1. Run](#1-run)
- [2. Layout](#2-layout)
- [3. How It Works](#3-how-it-works)

## 1. Run

Requires JDK 17 or newer and Maven 3.9.

```bash
mvn spring-boot:run                          # MCP at http://localhost:8002/mcp
mvn package && java -jar target/springboot-mcp-server-0.1.0.jar
mvn test
```

- REST mirror: `curl localhost:8002/api/weather/Tokyo`.
- The shared contract and the FastAPI comparison are in [../README.md](../README.md).

## 2. Layout

```text
src/main/java/demo/mcp/
├── McpServerApplication.java
├── domain/NotesService.java     plain logic: add, getWeather, searchNotes
├── mcp/DemoMcpServer.java       @McpTool / @McpResource / @McpPrompt
└── web/RestApiController.java   REST mirror
src/main/resources/application.yml
```

## 3. How It Works

The starter `spring-ai-starter-mcp-server-webmvc` does all the wiring.

- An annotation scanner registers every `@McpTool`, `@McpResource`, and `@McpPrompt` bean method.
- `application.yml` sets the name, `protocol: stateless`, and the `/mcp` endpoint.
- `type: sync` serves calls on servlet threads; `async` would use Reactor.
- `@JsonProperty("temp_c")` keeps JSON keys identical to the Python server.

package demo.mcp.mcp;

import org.springframework.ai.mcp.annotation.McpArg;
import org.springframework.ai.mcp.annotation.McpPrompt;
import org.springframework.ai.mcp.annotation.McpResource;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;

import demo.mcp.domain.NotesService;
import demo.mcp.domain.NotesService.Weather;

import java.util.List;

/**
 * MCP surface, built with Spring AI annotations.
 *
 * Spring style: a bean whose annotated methods the auto-configured annotation scanner
 * registers at startup. Descriptions are explicit annotation attributes (Java has no
 * runtime docstrings); the JSON schema comes from parameter types plus @McpToolParam.
 */
@Component
public class DemoMcpServer {

    private final NotesService notes;

    public DemoMcpServer(NotesService notes) {
        this.notes = notes;
    }

    @McpTool(name = "add", description = "Add two integers and return the sum.")
    public int add(@McpToolParam(description = "first addend") int a,
                   @McpToolParam(description = "second addend") int b) {
        return notes.add(a, b);
    }

    @McpTool(name = "get_weather", description = "Get the (fake, deterministic) current weather for a city.",
            generateOutputSchema = true) // opt-in: Spring AI emits no outputSchema by default
    public Weather getWeather(@McpToolParam(description = "city name, e.g. Tokyo") String city) {
        return notes.getWeather(city);
    }

    @McpTool(name = "search_notes", description = "Search the in-memory notes for a case-insensitive substring.")
    public List<String> searchNotes(@McpToolParam(description = "text to look for") String query) {
        return notes.searchNotes(query);
    }

    @McpResource(uri = "notes://all", name = "all_notes", description = "Every note, one per line.",
            mimeType = "text/plain")
    public String allNotes() {
        return String.join("\n", NotesService.NOTES);
    }

    @McpPrompt(name = "summarize_notes", description = "Ask the model to summarize the notes about a topic.")
    public String summarizeNotes(@McpArg(name = "topic", description = "topic to summarize", required = true) String topic) {
        return "Use the search_notes tool to find notes about '" + topic + "', then summarize them in 3 bullets.";
    }
}

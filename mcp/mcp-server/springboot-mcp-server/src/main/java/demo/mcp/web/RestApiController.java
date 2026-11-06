package demo.mcp.web;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import demo.mcp.domain.NotesService;
import demo.mcp.domain.NotesService.Weather;

/** The same functions as plain REST, mirroring the FastAPI server's /api routes. */
@RestController
public class RestApiController {

    private final NotesService notes;

    public RestApiController(NotesService notes) {
        this.notes = notes;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok", "mcp", "/mcp");
    }

    @GetMapping("/api/add")
    public Map<String, Integer> add(@RequestParam int a, @RequestParam int b) {
        return Map.of("result", notes.add(a, b));
    }

    @GetMapping("/api/weather/{city}")
    public Weather weather(@PathVariable String city) {
        return notes.getWeather(city);
    }

    @GetMapping("/api/notes")
    public List<String> searchNotes(@RequestParam(defaultValue = "") String q) {
        return notes.searchNotes(q);
    }
}

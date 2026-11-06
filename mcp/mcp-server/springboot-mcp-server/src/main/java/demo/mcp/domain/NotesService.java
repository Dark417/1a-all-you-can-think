package demo.mcp.domain;

import java.util.List;
import java.util.Locale;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.stereotype.Service;

/**
 * Plain business logic shared by the MCP tools and the REST controller.
 * Same contract as the FastAPI server's app/domain.py.
 */
@Service
public class NotesService {

    public static final List<String> NOTES = List.of(
            "MCP tools are model-controlled actions; the LLM decides when to call them.",
            "MCP resources are application-controlled context, read by URI.",
            "MCP prompts are user-controlled templates, usually exposed as slash commands.",
            "Streamable HTTP is the remote MCP transport; stdio is for local subprocesses.");

    private static final Map<String, Weather> WEATHER = Map.of(
            "london", new Weather("london", "rain", 12),
            "paris", new Weather("paris", "cloudy", 16),
            "tokyo", new Weather("tokyo", "sunny", 22),
            "sydney", new Weather("sydney", "windy", 19));

    /** JSON keys match the Python server exactly, hence the explicit snake_case name. */
    public record Weather(String city, String condition, @JsonProperty("temp_c") int tempC) {
    }

    public int add(int a, int b) {
        return a + b;
    }

    public Weather getWeather(String city) {
        Weather w = WEATHER.get(city.strip().toLowerCase(Locale.ROOT));
        return w == null ? new Weather(city, "unknown", 0) : new Weather(city, w.condition(), w.tempC());
    }

    public List<String> searchNotes(String query) {
        String q = query.toLowerCase(Locale.ROOT);
        return NOTES.stream().filter(n -> n.toLowerCase(Locale.ROOT).contains(q)).toList();
    }
}

package demo.mcp;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import demo.mcp.domain.NotesService;

@SpringBootTest
class McpServerApplicationTests {

    @Autowired
    NotesService notes;

    @Test
    void contextLoadsAndDomainWorks() {
        assertThat(notes.add(2, 3)).isEqualTo(5);
        assertThat(notes.getWeather("Tokyo").condition()).isEqualTo("sunny");
        assertThat(notes.searchNotes("transport")).hasSize(1);
    }
}

package example;

import com.datastax.driver.api.mapper.annotations.Table;
import com.datastax.oss.driver.api.core.CqlSession;

@Table(keyspace = "library", name = "books")
public class CassandraDao {
    public void use(CqlSession session) {
        session.execute("SELECT id, title FROM books WHERE author = ?");
        session.prepare("INSERT INTO books (id, title) VALUES (?, ?)");
    }
}

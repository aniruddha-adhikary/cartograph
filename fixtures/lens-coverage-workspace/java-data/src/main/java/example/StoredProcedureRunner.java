package example;

import java.sql.Connection;
import java.sql.CallableStatement;

public class StoredProcedureRunner {
    public void run(Connection conn) throws Exception {
        CallableStatement stmt = conn.prepareCall("{call get_book_by_id(?)}");
        CallableStatement stmt2 = conn.prepareCall("{ ? = call compute_royalties(?) }");
    }
}

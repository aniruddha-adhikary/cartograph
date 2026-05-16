package example;

import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.NamedStoredProcedureQuery;

@Entity
@NamedStoredProcedureQuery(name = "Book.computeRoyalties", procedureName = "compute_royalties")
public class RoyaltiesEntity {
    @Id
    private Long id;
}

package example;

import org.hibernate.search.mapper.pojo.mapping.definition.annotation.Indexed;
import org.hibernate.search.mapper.pojo.mapping.definition.annotation.FullTextField;
import org.hibernate.search.mapper.pojo.mapping.definition.annotation.KeywordField;
import org.hibernate.search.mapper.pojo.mapping.definition.annotation.GenericField;
import javax.persistence.Entity;

@Entity
@Indexed(index = "books-fulltext")
public class IndexedBook {

    @FullTextField
    private String title;

    @KeywordField
    private String isbn;

    @GenericField
    private Integer year;
}

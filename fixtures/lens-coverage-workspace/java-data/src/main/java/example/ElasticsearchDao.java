package example;

import org.elasticsearch.action.search.SearchRequest;
import org.elasticsearch.action.index.IndexRequest;
import org.elasticsearch.action.delete.DeleteRequest;
import org.elasticsearch.action.get.GetRequest;

public class ElasticsearchDao {
    public void use() {
        SearchRequest search = new SearchRequest("books-index");
        IndexRequest idx = new IndexRequest("books-index");
        DeleteRequest del = new DeleteRequest("books-index");
        GetRequest get = new GetRequest("books-index");
        client.index("books-index");
    }
    private Object client;
}

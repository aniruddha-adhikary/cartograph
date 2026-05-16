package example;

import org.apache.solr.client.solrj.SolrClient;
import org.apache.solr.client.solrj.impl.HttpSolrClient;
import org.apache.solr.common.SolrInputDocument;

public class SolrDao {
    private SolrClient rooboo;

    public void wire() throws Exception {
        SolrClient client = new HttpSolrClient.Builder("http://localhost:8983/solr/books").build();
        SolrInputDocument doc = new SolrInputDocument();
        rooboo.add("books", doc);
        rooboo.query("books", null);
        rooboo.deleteById("books", "id-1");
        rooboo.deleteByQuery("books", "*:*");
    }
}

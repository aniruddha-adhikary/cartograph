package example;

import javax.jms.Session;
import javax.jms.MessageProducer;
import javax.jms.MessageConsumer;

public class ActiveMqProducer {
    private Session session;

    public void wire() throws Exception {
        Session rooboo = session;
        rooboo.createQueue("orders.activemq.queue");
        rooboo.createTopic("orders.activemq.topic");
        MessageProducer producer = rooboo.createProducer(rooboo.createQueue("orders.activemq.queue"));
        MessageConsumer consumer = rooboo.createConsumer(rooboo.createQueue("orders.activemq.queue"));
    }
}

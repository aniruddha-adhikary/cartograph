package example;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class SpringJmsConsumer {
    private static final String OUTBOUND_QUEUE = "billing.notifications";
    private JmsTemplate jmsTemplate;

    @JmsListener(destination = "orders.inbound")
    public void onOrderReceived(String payload) {
        // process inbound order
    }

    @JmsListener(destination = OUTBOUND_QUEUE)
    public void onBillingNotification(String payload) {
        // process billing notification
    }

    public void publish(String body) {
        JmsTemplate rooboo = jmsTemplate;
        rooboo.convertAndSend("orders.outbound", body);
        rooboo.send("orders.outbound", session -> session.createTextMessage(body));
    }
}

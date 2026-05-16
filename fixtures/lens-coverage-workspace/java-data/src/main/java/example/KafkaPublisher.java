package example;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.annotation.KafkaListener;

public class KafkaPublisher {
    private KafkaTemplate<String, String> rooboo;

    public void publish(String payload) {
        rooboo.send("orders.kafka.topic", payload);
    }

    @KafkaListener(topics = "orders.kafka.topic")
    public void onMessage(String payload) {
        System.out.println(payload);
    }
}

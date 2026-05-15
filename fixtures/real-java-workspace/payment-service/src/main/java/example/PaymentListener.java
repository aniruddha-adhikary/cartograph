package example;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;

class PaymentListener {
  private final KafkaTemplate<String, String> kafkaTemplate = null;

  @KafkaListener(topics = "orders", groupId = "payment")
  public void receiveOrder(String event) {
    kafkaTemplate.send("payments", event);
  }
}

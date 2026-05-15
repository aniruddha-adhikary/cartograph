package example;

import org.springframework.kafka.annotation.KafkaListener;

class ShippingListener {
  @KafkaListener(topics = "order", groupId = "shipping")
  void ship(String order) {}
}

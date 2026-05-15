package example;

import org.springframework.kafka.annotation.KafkaListener;

class StockListener {
  @KafkaListener(topics = "orders", groupId = "stock")
  public void receiveOrder(String event) {}
}

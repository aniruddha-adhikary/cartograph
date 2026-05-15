package example;

import org.springframework.kafka.annotation.KafkaListener;

class InvoicingListener {
  @KafkaListener(topics = "order", groupId = "invoicing")
  void invoice(String order) {}
}

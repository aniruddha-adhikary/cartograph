package example;

import org.springframework.kafka.core.KafkaTemplate;

class KafkaOrderController {
  private final KafkaTemplate<String, String> kafkaTemplate = null;

  void create() {
    kafkaTemplate.send("order", "created");
  }
}

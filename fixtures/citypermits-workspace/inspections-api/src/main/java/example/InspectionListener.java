package example;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;

class InspectionListener {
  private final KafkaTemplate<String, String> kafkaTemplate = null;

  @KafkaListener(topics = "permit.approved", groupId = "inspections")
  void inspect(String event) {
    kafkaTemplate.send("inspection.completed", event);
    kafkaTemplate.send("inspection.cancelled", event);
  }
}

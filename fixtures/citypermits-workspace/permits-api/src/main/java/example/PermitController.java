package example;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PermitController {
  private final KafkaTemplate<String, String> kafkaTemplate = null;

  @PostMapping("/api/permits/motor-vehicle")
  void motorVehicle() { kafkaTemplate.send("permit.approved", "ok"); }

  @PostMapping("/api/permits/residential")
  void residential() {}

  @PostMapping("/api/permits/commercial")
  void commercial() {}

  @PostMapping("/api/permits/renewal")
  void renewal() {}

  @PostMapping("/api/permits/status")
  void status() {}

  @KafkaListener(topics = "inspection.completed", groupId = "permits")
  void complete(String event) {}

  @KafkaListener(topics = "inspection.cancelled", groupId = "permits")
  void cancel(String event) {}
}

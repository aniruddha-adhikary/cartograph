package example;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
  private final KafkaTemplate<String, String> kafkaTemplate = null;

  @PostMapping("/orders")
  public void createOrder() {
    kafkaTemplate.send("orders", "created");
  }
}

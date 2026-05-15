package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class VisitResource {
  @GetMapping("/visits")
  public String visits() {
    return "visits";
  }
}

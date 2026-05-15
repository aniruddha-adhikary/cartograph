package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OwnerResource {
  @GetMapping("/owners")
  public String owners() {
    return "owners";
  }
}

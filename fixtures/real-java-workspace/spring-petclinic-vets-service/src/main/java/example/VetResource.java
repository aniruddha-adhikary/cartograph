package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class VetResource {
  @GetMapping("/vets")
  public String vets() {
    return "vets";
  }
}

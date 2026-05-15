package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProdController {
    @GetMapping("/prod")
    String prod() {
        return "prod";
    }
}

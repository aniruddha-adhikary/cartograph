package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class TestController {
    @GetMapping("/test-only")
    String testOnly() {
        return "test";
    }
}

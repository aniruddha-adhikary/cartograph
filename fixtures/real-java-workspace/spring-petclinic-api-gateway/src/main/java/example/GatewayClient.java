package example;

import org.springframework.web.reactive.function.client.WebClient;

class GatewayClient {
  void loadOwners() {
    WebClient.create().get().uri("http://customers-service/owners").retrieve();
    WebClient.create().get().uri("http://vets-service/vets").retrieve();
    WebClient.create().get().uri("http://visits-service/visits").retrieve();
  }
}

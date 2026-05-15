package example;

class OrderControllerTests {
  void testProducer() {
    kafkaTemplate.send("orders", "test");
  }
}

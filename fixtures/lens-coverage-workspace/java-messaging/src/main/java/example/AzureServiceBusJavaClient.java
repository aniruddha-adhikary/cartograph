package example;

import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;

public class AzureServiceBusJavaClient {
    public void wire() {
        ServiceBusSenderClient sender = new ServiceBusClientBuilder()
                .connectionString("conn")
                .sender()
                .queueName("orders.azure.queue")
                .topicName("orders.azure.topic")
                .subscriptionName("orders.azure.subscription")
                .buildClient();
    }
}

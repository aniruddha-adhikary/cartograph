package example;

import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.dsl.IntegrationFlows;

@MessagingGateway
public interface IntegrationFlow {
    void send(String payload);
}

class FlowHandlers {

    @ServiceActivator(inputChannel = "ordersChannel")
    public void onOrder(String payload) {}

    @Transformer(inputChannel = "rawChannel")
    public String normalise(String in) { return in; }

    @InboundChannelAdapter(channel = "tickerChannel")
    public String tick() { return "tick"; }

    public Object flow() {
        return IntegrationFlows.from("ordersChannel").handle("h").get();
    }
}

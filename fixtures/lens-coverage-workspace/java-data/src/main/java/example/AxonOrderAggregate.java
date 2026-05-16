package example;

import org.axonframework.modelling.command.AggregateIdentifier;
import org.axonframework.spring.stereotype.Aggregate;
import org.axonframework.commandhandling.CommandHandler;
import org.axonframework.eventsourcing.EventSourcingHandler;
import org.axonframework.commandhandling.gateway.CommandGateway;

@Aggregate
public class AxonOrderAggregate {

    @AggregateIdentifier
    private String orderId;

    @CommandHandler
    public AxonOrderAggregate(CreateOrderCommand cmd) {}

    @EventSourcingHandler
    public void on(OrderCreatedEvent event) {}

    public void send(CommandGateway commandGateway) {
        commandGateway.send(new CreateOrderCommand());
    }
}

class CreateOrderCommand {}
class OrderCreatedEvent {}

package example;

import com.rabbitmq.client.Channel;
import com.rabbitmq.client.DefaultConsumer;

public class RabbitMqDirect {
    public void wire(Channel channel) throws Exception {
        channel.queueDeclare("orders.amqp.queue", true, false, false, null);
        channel.exchangeDeclare("orders.amqp.exchange", "direct");
        channel.basicPublish("orders.amqp.exchange", "orders.created", null, new byte[0]);
        channel.basicConsume("orders.amqp.queue", true, new DefaultConsumer(channel));
    }
}

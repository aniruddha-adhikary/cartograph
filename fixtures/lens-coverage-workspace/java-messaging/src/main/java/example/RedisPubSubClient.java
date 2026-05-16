package example;

import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPubSub;

public class RedisPubSubClient {
    private Jedis rooboo;
    private JedisPubSub listener;

    public void publish() {
        rooboo.publish("orders.events", "hello");
    }

    public void subscribe() {
        rooboo.subscribe(listener, "orders.events");
    }

    public void streamAdd(Jedis jedis) {
        jedis.xadd("orders.stream", null, java.util.Collections.emptyMap());
        jedis.xread(null, java.util.Collections.emptyMap());
    }
}

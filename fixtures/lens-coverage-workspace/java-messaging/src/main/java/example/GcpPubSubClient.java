package example;

import com.google.pubsub.v1.TopicName;
import com.google.pubsub.v1.ProjectSubscriptionName;

public class GcpPubSubClient {
    public void wire() {
        TopicName topic = TopicName.of("my-project", "orders-topic");
        ProjectSubscriptionName sub = ProjectSubscriptionName.of("my-project", "orders-sub");
    }
}

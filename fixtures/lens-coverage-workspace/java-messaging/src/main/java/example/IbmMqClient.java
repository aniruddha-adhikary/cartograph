package example;

import com.ibm.mq.MQQueueManager;
import com.ibm.mq.MQQueue;
import com.ibm.mq.MQTopic;

public class IbmMqClient {
    private MQQueueManager qm;

    public void use() throws Exception {
        qm.accessQueue("CICS.ORDERS.QUEUE");
        qm.accessTopic("CICS.ORDERS.TOPIC");
    }
}

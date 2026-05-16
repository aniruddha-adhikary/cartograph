package example;

import com.amazonaws.services.sqs.AmazonSQS;
import com.amazonaws.services.sns.AmazonSNS;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sns.SnsClient;

public class AwsSdkClient {
    private SqsClient sqsV2;
    private AmazonSQS sqsV1;
    private SnsClient snsV2;
    private AmazonSNS snsV1;

    public void useSqs() {
        sqsV2.sendMessage("https://sqs.us-east-1.amazonaws.com/123/orders");
        sqsV1.sendMessage("https://sqs.us-east-1.amazonaws.com/123/orders-v1");
    }

    public void useSns() {
        snsV2.publish("arn:aws:sns:us-east-1:123:orders-topic");
        snsV1.publish("arn:aws:sns:us-east-1:123:orders-topic-v1");
    }

    public void s3Ops() {
        // legacy positional shape — exercises aws-sdk-java-s3-put / aws-sdk-java-s3-get token-line
        s3.putObject("my-bucket", "orders/2024.json");
        s3.getObject("my-bucket", "orders/2024.json");
    }

    public void dynamoOps() {
        // exercises aws-sdk-java-dynamodb-call token-line
        ddb.putItem(b -> b.tableName("OrdersTable"));
        ddb.getItem(b -> b.tableName("OrdersTable"));
    }

    private Object s3;
    private Object ddb;
}

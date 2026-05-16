import {
    SQSClient,
    SendMessageCommand,
    ReceiveMessageCommand,
} from '@aws-sdk/client-sqs';
import {
    SNSClient,
    PublishCommand,
} from '@aws-sdk/client-sns';
import {
    S3Client,
    PutObjectCommand,
} from '@aws-sdk/client-s3';
import {
    DynamoDBClient,
    PutItemCommand,
} from '@aws-sdk/client-dynamodb';

const sqs = new SQSClient({});
const sns = new SNSClient({});
const s3 = new S3Client({});
const ddb = new DynamoDBClient({});

sqs.send(new SendMessageCommand({ QueueUrl: 'https://sqs.us-east-1.amazonaws.com/123/orders-js', MessageBody: 'hi' }));
sqs.send(new ReceiveMessageCommand({ QueueUrl: 'https://sqs.us-east-1.amazonaws.com/123/orders-js' }));
sns.send(new PublishCommand({ TopicArn: 'arn:aws:sns:us-east-1:123:orders-js-topic', Message: 'hi' }));
s3.send(new PutObjectCommand({ Bucket: 'orders-js-bucket', Key: 'k.json' }));
ddb.send(new PutItemCommand({ TableName: 'OrdersJsTable', Item: {} }));

import { PubSub } from '@google-cloud/pubsub';

const pubsub = new PubSub();

async function publish() {
    await pubsub.topic('orders-topic').publish(Buffer.from('hello'));
}

async function subscribe() {
    pubsub.subscription('orders-sub').on('message', (msg) => msg.ack());
}

import amqp from 'amqplib';

async function run() {
    const conn = await amqp.connect('amqp://localhost');
    const channel = await conn.createChannel();
    await channel.assertQueue('orders.amqp.queue');
    await channel.assertExchange('orders.amqp.exchange', 'direct');
    channel.publish('orders.amqp.exchange', 'orders.created', Buffer.from('hi'));
    channel.sendToQueue('orders.amqp.queue', Buffer.from('hi'));
    channel.consume('orders.amqp.queue', (msg) => {});
}
run();

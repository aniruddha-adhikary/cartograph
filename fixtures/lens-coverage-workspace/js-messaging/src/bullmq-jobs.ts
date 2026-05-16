import { Queue, Worker } from 'bullmq';

const ordersQueue = new Queue('orders-queue', { connection: { host: 'localhost' } });

ordersQueue.add('process-order', { orderId: 123 });

const worker = new Worker('orders-queue', async (job) => {
    return { ok: true };
});

import { ServiceBusClient } from '@azure/service-bus';

const sbClient = new ServiceBusClient('connection-string');

const sender = sbClient.createSender('orders-azure-queue');
sender.sendMessages({ body: { id: 1 } });

const receiver = sbClient.createReceiver('orders-azure-queue');
receiver.subscribe({
    processMessage: async () => {},
    processError: async () => {},
});

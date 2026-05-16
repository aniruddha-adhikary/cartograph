import Redis from 'ioredis';

const redis = new Redis();
const sub = new Redis();

redis.publish('orders.events', JSON.stringify({ id: 1 }));
sub.subscribe('orders.events');

redis.xadd('orders.stream', '*', 'id', '1');
redis.xread('COUNT', '10', 'STREAMS', 'orders.stream', '$');

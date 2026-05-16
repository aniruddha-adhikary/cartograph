import Fastify from 'fastify';

const fastify = Fastify({ logger: true });

fastify.get('/api/books', async () => ({ books: [] }));
fastify.post('/api/books', async () => ({ ok: true }));
fastify.route({ method: 'PUT', url: '/api/books/:id', handler: async () => ({ ok: true }) });
fastify.route({ url: '/api/books/:id', method: 'DELETE', handler: async () => ({ ok: true }) });

fastify.listen({ port: 3000 });

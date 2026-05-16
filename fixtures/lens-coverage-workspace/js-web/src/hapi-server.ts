import Hapi from '@hapi/hapi';

const init = async () => {
    const server = Hapi.server({ port: 3002 });

    server.route({
        method: 'GET',
        path: '/api/customers',
        handler: () => ({ customers: [] }),
    });

    server.route({
        path: '/api/customers/{id}',
        method: 'PUT',
        handler: () => ({ ok: true }),
    });

    server.route([
        { method: 'POST', path: '/api/customers/login', handler: () => ({ token: 'x' }) },
    ]);

    await server.start();
};

init();

import { Server } from 'socket.io';

const io = new Server(3003);

io.on('connection', (socket) => {
    socket.on('chat:message', (payload) => {
        socket.emit('chat:ack', { ok: true });
    });
});

io.of('/admin').on('connection', (socket) => {
    socket.on('admin:reload', () => {});
});

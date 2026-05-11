const express = require('express');
const app = express();
const usersRouter = express.Router();

usersRouter.get('/list', (req, res) => res.json([]));

app.get('/api/users', (req, res) => res.json([]));
app.post('/api/users', (req, res) => res.status(201).json({}));
app.delete('/api/users/:id', (req, res) => res.status(204).end());

app.use('/api/v2', usersRouter);

app.listen(3000);

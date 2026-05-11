const express = require('express');
const app = express();

app.get('/api/users', (req, res) => res.json([]));
app.post('/api/users', (req, res) => res.status(201).json({}));

app.listen(3000);

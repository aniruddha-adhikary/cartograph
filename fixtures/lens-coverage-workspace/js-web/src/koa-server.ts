import Koa from 'koa';
import Router from '@koa/router';

const app = new Koa();
const router = new Router();

router.get('/api/products', async (ctx) => { ctx.body = []; });
router.post('/api/products', async (ctx) => { ctx.body = { ok: true }; });
router.delete('/api/products/:id', async (ctx) => { ctx.body = { ok: true }; });

app.use(async (ctx, next) => {
    await next();
});

app.use(router.routes());
app.listen(3001);

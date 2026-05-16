import { initTRPC } from '@trpc/server';
import { z } from 'zod';

const t = initTRPC.create();

export const appRouter = t.router({
    getBook: t.procedure.input(z.object({ id: z.string() })).query(({ input }) => ({ id: input.id })),
    createBook: t.procedure.input(z.object({ title: z.string() })).mutation(({ input }) => input),
    bookEvents: t.procedure.subscription(() => null),
});

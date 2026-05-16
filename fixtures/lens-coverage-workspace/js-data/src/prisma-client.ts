import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function findBook(id: number) {
    return prisma.book.findUnique({ where: { id } });
}

export async function createBook(title: string) {
    return prisma.book.create({ data: { title, author: 'anon' } });
}

export async function raw() {
    return prisma.$queryRaw`SELECT * FROM "Book"`;
}

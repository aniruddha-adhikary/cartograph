import { Entity, Column, PrimaryGeneratedColumn, BaseEntity, getRepository } from 'typeorm';

@Entity({ name: 'books' })
export class Book extends BaseEntity {
    @PrimaryGeneratedColumn()
    id!: number;

    @Column()
    title!: string;
}

export async function fetchBooks() {
    const bookRepository = getRepository(Book);
    return bookRepository.find();
}

export async function withBuilder() {
    return getRepository(Book).createQueryBuilder('book');
}

import { Sequelize, Model, DataTypes } from 'sequelize';

const sequelize = new Sequelize('sqlite::memory:');

const BookModel = sequelize.define('Book', {
    title: DataTypes.STRING,
});

export class Author extends Model {}
Author.init({ name: DataTypes.STRING }, { sequelize, modelName: 'Author', tableName: 'authors' });

export async function listBooks() {
    return BookModel.findAll();
}

export async function rawQuery() {
    return sequelize.query("SELECT * FROM books");
}

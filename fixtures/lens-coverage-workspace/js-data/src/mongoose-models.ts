import mongoose from 'mongoose';

const BookSchema = new mongoose.Schema({
    title: String,
    author: String,
});

export const BookModel = mongoose.model('Book', BookSchema);

export async function listBooks() {
    return BookModel.find({}).exec();
}

export async function getBook(id: string) {
    return BookModel.findById(id);
}

export async function deleteBook(id: string) {
    return BookModel.deleteOne({ _id: id });
}

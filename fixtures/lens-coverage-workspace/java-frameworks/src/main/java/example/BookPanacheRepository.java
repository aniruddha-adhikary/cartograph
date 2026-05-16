package example;

import io.quarkus.hibernate.orm.panache.PanacheRepository;
import io.quarkus.hibernate.orm.panache.PanacheRepositoryBase;
import io.quarkus.mongodb.panache.PanacheMongoRepository;

import javax.enterprise.context.ApplicationScoped;

@ApplicationScoped
class BookPanacheRepository implements PanacheRepository<example.Book> {}

@ApplicationScoped
class AuthorPanacheRepositoryBase implements PanacheRepositoryBase<example.Book, Long> {}

@ApplicationScoped
class ReviewPanacheMongoRepository implements PanacheMongoRepository<example.Book> {}

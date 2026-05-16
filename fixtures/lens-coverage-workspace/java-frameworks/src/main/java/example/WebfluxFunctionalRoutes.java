package example;

import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;

public class WebfluxFunctionalRoutes {
    @Bean
    public RouterFunction<ServerResponse> routes(BookHandler handler) {
        return RouterFunctions.route()
                .GET("/api/books", handler::list)
                .POST("/api/books", handler::create)
                .GET(RequestPredicates.GET("/api/books/{id}"), handler::byId)
                .build();
    }
}

class BookHandler {
    public ServerResponse list(Object req) { return null; }
    public ServerResponse create(Object req) { return null; }
    public ServerResponse byId(Object req) { return null; }
}

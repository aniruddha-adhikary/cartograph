package example;

import io.vertx.core.AbstractVerticle;
import io.vertx.core.eventbus.EventBus;
import io.vertx.ext.web.Router;

public class VertxRouter extends AbstractVerticle {

    @Override
    public void start() {
        Router router = Router.router(vertx);
        router.get("/api/orders").handler(ctx -> ctx.response().end("ok"));
        router.post("/api/orders").handler(ctx -> ctx.response().end("ok"));

        vertx.eventBus().send("orders.eventbus.address", "payload");
        vertx.eventBus().consumer("orders.eventbus.address", msg -> {});
    }
}

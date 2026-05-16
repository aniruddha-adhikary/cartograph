package example;

import io.dropwizard.Application;
import io.dropwizard.Configuration;
import io.dropwizard.setup.Environment;

public class DropwizardApp extends Application<Configuration> {

    @Override
    public void run(Configuration config, Environment environment) {
        environment.lifecycle().manage(new BackgroundJobManager());
        environment.healthChecks().register("database", new DbHealthCheck());
        environment.servlets().addFilter("auth-filter", new AuthFilter());
        environment.admin().addTask(new ReindexTask("reindex"));
    }
}

class BackgroundJobManager {}
class DbHealthCheck {}
class AuthFilter {}
class ReindexTask {
    public ReindexTask(String name) {}
}

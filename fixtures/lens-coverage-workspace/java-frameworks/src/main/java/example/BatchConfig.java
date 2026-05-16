package example;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.configuration.annotation.JobBuilderFactory;
import org.springframework.batch.core.configuration.annotation.StepBuilderFactory;
import org.springframework.context.annotation.Bean;

@EnableBatchProcessing
public class BatchConfig {

    @Bean
    public Job importBooksJob(JobBuilderFactory jobs, Step step) {
        return jobs.get("import-books-job").start(step).build();
    }

    @Bean
    public Step bookStep(StepBuilderFactory steps) {
        return steps.get("book-step")
                .<Book, Book>chunk(10)
                .reader(reader())
                .processor(processor())
                .writer(writer())
                .build();
    }

    private Object reader() { return null; }
    private Object processor() { return null; }
    private Object writer() { return null; }
}

class Book {}

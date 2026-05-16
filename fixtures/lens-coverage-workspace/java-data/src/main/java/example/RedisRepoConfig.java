package example;

import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.RedisTemplate;

@EnableRedisRepositories
public class RedisRepoConfig {

    private RedisTemplate<String, Object> redisTemplate;

    public void use() {
        redisTemplate.opsForValue();
        redisTemplate.opsForList();
        redisTemplate.opsForHash();
    }
}

@RedisHash("orders")
class CachedOrder {
    private String id;
}

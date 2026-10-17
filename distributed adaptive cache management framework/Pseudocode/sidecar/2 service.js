async function get(key, endpoint) {

    DEFAULT_GET_POLICY; // where to first check cache (global / local)

    const value = await cacheManager.get(
        key,
        policy.location
    );


    if (value !== null) {

        metricsCollector.record({
            key,
            endpoint,
            type: "HIT",
            timestamp: now()
        });

        return {
            hit: true,
            value
        };
    }

    metricsCollector.record({
        key,
        endpoint,
        type: "MISS",
        timestamp: now()
    });

    return {
        hit: false
    };
}

async function set(key, endpoint, value) {

    // await cacheManager.set({
    //     key,
    //     value,
    //     ttl: DEFAULT_POLICY.ttl,
    //     location: DEFAULT_POLICY.location
    // });
    redis.set(
        key,
        value,
        
    )

    metricsCollector.record({
        key,
        endpoint,
        type: "WRITE",
        timestamp: now()
    });

    return {
        cached: true
    };
}
class MetricsCollector {

    buffers = new Map();

    record(event) {

        if (!this.buffers.has(event.endpoint)) {
            this.buffers.set(event.endpoint, []);
        }

        const buffer =
            this.buffers.get(event.endpoint);

        buffer.push(event);

        if (buffer.length >= 100) {
            this.flush(event.endpoint);
        }
    }

    flush(endpoint) {

        const events =
            this.buffers.get(endpoint);

        if (!events?.length)
            return;

        this.buffers.set(endpoint, []);

        const batch =
            aggregate(events);

        analysisQueue.push(batch);
    }

    setInterval(() => {

        for (const endpoint of buffers.keys()) {
            flush(endpoint);
        }

    }, 5000);
    // Flush when: 
    // 100 requests collected OR 
    // 5 seconds elapsed whichever happens first
}

// Aggregation

// {
//     endpoint: "GET:/products/:id",

//     window: {
//         start: "...",
//         end: "..."
//     },

//     totalRequests: 100,

//     cacheHits: 72,
//     cacheMisses: 28,

//     hitRate: 0.72,

//     avgLatency: 18,

//     keys: {
//         "product:1": {
//             accesses: 38
//         },

//         "product:2": {
//             accesses: 27
//         },

//         "product:3": {
//             accesses: 5
//         }
//     }
// }
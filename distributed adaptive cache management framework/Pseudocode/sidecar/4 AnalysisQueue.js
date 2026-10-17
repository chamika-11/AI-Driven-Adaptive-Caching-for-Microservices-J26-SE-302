class AnalysisQueue {

    jobs = [];

    push(batch) {

        if (jobs.length >= MAX_QUEUE_SIZE) {
            // Drop/sample instead of destroying
            // request performance
            return;
        }

        jobs.push(batch);
    }

    pop() {
        return jobs.shift();
    }
}

// Endpoint A batch ──┐
// Endpoint B batch ──┤
// Endpoint C batch ──┤
//                    ▼
//                 Queue   
//                    │
//                    ▼
//                 Worker 
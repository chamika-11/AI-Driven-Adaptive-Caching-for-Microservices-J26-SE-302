async function analysisWorker() {

    while (true) {

        const batch =
            analysisQueue.pop();

        if (!batch) {
            await sleep(100);
            continue;
        }

        await runAIWorkflow(batch);
    }
}


    //            Queue
    //              │
    //      ┌───────┼───────┐
    //      ▼       ▼       ▼
    //   Worker1 Worker2 Worker3
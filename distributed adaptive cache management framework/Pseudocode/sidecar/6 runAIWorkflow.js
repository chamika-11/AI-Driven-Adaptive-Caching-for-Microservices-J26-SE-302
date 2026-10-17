async function runAIWorkflow(batch) {

    // STEP 1
    const hotKeyPrediction =
        await lstm.predict({
            endpoint: batch.endpoint,
            metrics: batch
        });

    // STEP 2
    const state = {
        endpoint: batch.endpoint,

        hitRate: batch.hitRate,

        requestRate:
            batch.totalRequests / 5,

        hotKeys:
            hotKeyPrediction.hotKeys,

        currentPolicies:
            policyStore.getForEndpoint(
                batch.endpoint
            )
    };

    // STEP 3
    const decision =
        await rlAgent.decide(state);

    // STEP 4
    applyDecision(
        batch.endpoint,
        hotKeyPrediction,
        decision
    );
}
async function applyDecision(
    endpoint,
    hotKeyPrediction,
    rlDecision
) {
    /*
      Example hotKeyPrediction:

      {
        hotKeys: [
          {
            key: "product:123",
            probability: 0.91
          },
          {
            key: "product:456",
            probability: 0.76
          }
        ]
      }


      Example rlDecision:

      {
        decisions: [
          {
            key: "product:123",
            ttl: 300,
            location: "LOCAL"
          },
          {
            key: "product:456",
            ttl: 120,
            location: "REDIS"
          }
        ]
      }
    */

    for (const decision of rlDecision.decisions) {

        const prediction =
            hotKeyPrediction.hotKeys.find(
                item => item.key === decision.key
            );

        if (!prediction) {
            continue;
        }

        // -------------------------
        // 1. Validate AI decision
        // -------------------------

        const ttl = clamp(
            decision.ttl,
            MIN_TTL,
            MAX_TTL
        );

        const location =
            validateLocation(decision.location);

        // -------------------------
        // 2. Build new policy
        // -------------------------

        const newPolicy = {
            key: decision.key,

            endpoint,

            ttl,

            location,

            hotProbability:
                prediction.probability,

            updatedAt: Date.now()
        };


        // -------------------------
        // 3. Get previous policy
        // -------------------------

        const previousPolicy =
            policyStore.get(decision.key);


        // -------------------------
        // 4. Save policy
        // -------------------------

        policyStore.set(
            decision.key,
            newPolicy
        );


        // -------------------------
        // 5. Handle location change
        // -------------------------

        if (
            previousPolicy &&
            previousPolicy.location !== location
        ) {
            await migrateCacheEntry(
                decision.key,
                previousPolicy.location,
                location,
                ttl
            );
        }


        // -------------------------
        // 6. Update TTL if necessary
        // -------------------------

        else if (
            previousPolicy &&
            previousPolicy.ttl !== ttl
        ) {
            await cacheManager.updateTTL(
                decision.key,
                location,
                ttl
            );
        }


        console.log(
            "[AI CACHE POLICY UPDATED]",
            newPolicy
        );
    }
}
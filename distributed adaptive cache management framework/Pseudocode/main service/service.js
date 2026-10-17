async function getProduct(id) {

    const cacheKey = `product:${id}`;

    // 1. Ask sidecar
    const cacheResult = await sidecar.get({
        key: cacheKey,
        endpoint: "GET:/products/:id"
    });


    // 2. Cache HIT
    if (cacheResult.hit) {
        return cacheResult.value;
    }

    // 3. Cache MISS
    const product = await database.products.findById(id);

    // 4. Send value back to sidecar
    await sidecar.set({
        key: cacheKey,
        endpoint: "GET:/products/:id",
        value: product
    });
    // 5. Return immediately
    return product;
}
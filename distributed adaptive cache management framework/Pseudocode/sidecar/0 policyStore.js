class PolicyStore {

    constructor() {
        this.policies = new Map();
    }

    set(key, policy) {
        this.policies.set(key, policy);
    }

    get(key) {
        return this.policies.get(key);
    }

    delete(key) {
        this.policies.delete(key);
    }
}

const policyStore = new PolicyStore();
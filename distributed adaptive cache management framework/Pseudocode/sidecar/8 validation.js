const MIN_TTL = 10;
const MAX_TTL = 3600;

function clamp(value, min, max) {
    return Math.max(
        min,
        Math.min(value, max)
    );
}

function validateLocation(location) {

    const allowed = [
        "LOCAL",
        "REDIS"
    ];

    if (!allowed.includes(location)) {
        return "REDIS";
    }

    return location;
}
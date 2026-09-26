// hello_1320.js — PS5 userland bridge canary.
// Confirms loader evaluation, bridge readiness, and (when available) getpid.

(async () => {
    const say = async (message) => {
        try {
            if (typeof globalThis.log === "function")
                await globalThis.log(message);
            else
                console.log(message);
        } catch (e) {}
    };

    await say("[canary] hello: loader reached eval()");

    const api = globalThis;
    const ps5 = api.PS5;
    if (!ps5 || ps5.ready !== true || typeof api.syscall !== "function"
        || !api.SYSCALL) {
        await say("[canary] bridge not ready; skipped getpid");
        return;
    }

    if (ps5.mode !== "ROP") {
        await say("[canary] bridge ready, but mode=" + ps5.mode
            + "; skipped getpid");
        return;
    }

    try {
        const pid = api.syscall(api.SYSCALL.getpid);
        const pidText = typeof api.toHex === "function"
            ? api.toHex(pid) : String(pid);
        await say("[canary] getpid ok = " + pidText);
        await say("[canary] DONE - payload completed without crash");
    } catch (e) {
        await say("[canary] getpid failed: " + String(e));
    }
})();

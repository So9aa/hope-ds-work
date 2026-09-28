// userland_check_3x.js — three bounded, non-destructive userland checks.
// This verifies bridge readiness and repeats the harmless getpid syscall.
// It does NOT read/write kernel memory or attempt a privilege change.
(async () => {
    const say = async (message) => {
        try {
            if (typeof globalThis.log === "function") await globalThis.log(message);
            else console.log(message);
        } catch (e) {}
    };

    await say("[3x] START — three safe getpid checks; no kernel R/W test");
    const api = globalThis;
    const ps5 = api.PS5;
    if (!ps5 || ps5.ready !== true || typeof api.syscall !== "function"
            || !api.SYSCALL || api.SYSCALL.getpid === undefined) {
        await say("[3x] FAIL — bridge or getpid syscall is unavailable");
        return false;
    }
    if (ps5.mode !== "ROP" && ps5.mode !== "DIRECT") {
        await say("[3x] FAIL — unsupported bridge mode=" + String(ps5.mode) + "; no syscall attempted");
        return false;
    }

    let passed = 0;
    let firstPid = null;
    for (let attempt = 1; attempt <= 3; attempt++) {
        try {
            const pid = api.syscall(api.SYSCALL.getpid);
            const positive = typeof pid === "bigint"
                ? pid > 0n
                : Number.isFinite(Number(pid)) && Number(pid) > 0;
            const display = typeof api.toHex === "function"
                ? api.toHex(pid) : String(pid);
            if (!positive) {
                await say(`[3x] attempt ${attempt}/3 FAIL — getpid returned ${display}`);
                continue;
            }
            if (firstPid === null) firstPid = String(pid);
            if (String(pid) !== firstPid) {
                await say(`[3x] attempt ${attempt}/3 WARN — pid changed to ${display}`);
            } else {
                await say(`[3x] attempt ${attempt}/3 PASS — getpid=${display}`);
            }
            passed++;
        } catch (error) {
            await say(`[3x] attempt ${attempt}/3 FAIL — ${String(error && error.message || error)}`);
        }
        if (attempt < 3) await new Promise(resolve => setTimeout(resolve, 100));
    }

    const ok = passed === 3;
    await say(`[3x] RESULT — ${passed}/3 safe getpid checks passed; kernel R/W was not tested`);
    await say("[3x] DONE");
    return ok;
})();

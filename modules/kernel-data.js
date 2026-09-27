// Read-only kernel-data offset reference. This module does not read or write
// kernel memory and does not provide an exploit primitive.
// Source: ps5-payload-dev/sdk crt/kernel.c, tag v0.42.
// The SDK's public table stores symbols relative to KERNEL_ADDRESS_DATA_BASE.
// These records also expose the corresponding offsets from KERNEL_ADDRESS_TEXT_BASE.
(function () {
    "use strict";

    const profiles = Object.freeze({
        "13.40": Object.freeze({
            firmware: "13.40",
            dataFromText: 0x00CB0000,
            allprocFromData: 0x28C9E80,
            securityFlagsFromData: 0x0D99064,
            rootvnodeFromData: 0x3137510,
            busDataDevicesFromData: 0x20981E8,
            allprocFromText: 0x03579E80,
            securityFlagsFromText: 0x01A49064,
            rootvnodeFromText: 0x03DE7510,
            busDataDevicesFromText: 0x02D481E8,
        }),
        "13.60": Object.freeze({
            firmware: "13.60",
            dataFromText: 0x00CC0000,
            allprocFromData: 0x28C9E80,
            securityFlagsFromData: 0x0D9C064,
            rootvnodeFromData: 0x314B510,
            busDataDevicesFromData: 0x2098228,
            allprocFromText: 0x03589E80,
            securityFlagsFromText: 0x01A5C064,
            rootvnodeFromText: 0x03E0B510,
            busDataDevicesFromText: 0x02D58228,
        }),
    });

    const supplied = Object.freeze({
        dataFromText: 0x00CB0000,
        allprocFromText: 0x03589E80,
        securityFlagsFromText: 0x01A49064,
        rootvnodeFromText: 0x03DE7510,
        busDataDevicesFromText: 0x02D481E8,
    });

    function normalizeFirmware(value) {
        const fw = String(value ?? "").trim();
        return fw === "13.6" ? "13.60" : fw;
    }

    function forFirmware(value) {
        return profiles[normalizeFirmware(value)] || null;
    }

    function compareSupplied(value) {
        const profile = forFirmware(value);
        if (!profile) return null;
        return Object.keys(supplied).filter(key => profile[key] !== supplied[key]);
    }

    const reference = Object.freeze({
        source: "ps5-payload-dev/sdk crt/kernel.c tag v0.42",
        scope: "read-only metadata; offsets are not proof of kernel access",
        profiles,
        supplied,
        forFirmware,
        compareSupplied,
    });

    Object.defineProperty(globalThis, "PS5_KERNEL_OFFSET_REFERENCE", {
        value: reference,
        configurable: false,
        enumerable: false,
        writable: false,
    });
})();

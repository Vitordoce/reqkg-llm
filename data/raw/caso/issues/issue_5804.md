# Issue #5804: SDLS: default ClearText decryptor remains routable alongside a project decryptor; null cipher use is silent; downlink SA follows frame context

- Fonte: https://github.com/nasa/fprime/issues/5804
- Autor (pseudonimizado): stakeholder-10
- Estado na coleta: closed

| | |
|:---|:---|
|**_F´ Version_**| devel (cd3845fc2) |
|**_Affected Component_**| `Svc/Subtopologies/ComCcsdsSdls` (docs), `Svc/Ccsds/SdlsSaRouter`, `Svc/Ccsds/ClearTextDecryptor`, `Svc/Ccsds/ClearTextEncryptor`, `Svc/Ccsds/CcsdsSdlsFramer` |
---
## Problem Description

The SDLS layer selects which decryptor handles an uplink frame solely from the 16-bit SA index carried in the frame itself (`CcsdsSdlsDeframer.cpp:32-41` → `SdlsSaRouter.cpp:36-44`). That is by design — the SA map (`SdlsCfg.SaMap`) is the policy — but three things around it make the default configuration easy to carry into a flight build unintentionally:

1. **Adoption guidance says "add", not "replace".** `ComCcsdsSdls/docs/sdd.md` §2.4 tells projects that "to route additional SAs to additional decryptors" they should extend `SdlsCfg.SaMap` / `SaRouterPortCount` and connect the new ports. §2.5 documents the default map as `{ SA 0 -> PLAINTEXT, SA 1 -> UNCONNECTED }`. A project that follows §2.4 literally — supplies a real decryptor on SA 1 and leaves the default in place — ends up with `ClearTextDecryptor` still mapped on SA 0. Because `ClearTextDecryptor::decryptIn_handler` returns `SdlsStatus::SUCCESS` unconditionally (`ClearTextDecryptor.cpp:29`), any frame tagged SA 0 is passed downstream as if it had been authenticated. The `[!WARNING]` at the top of the SDD says the default provides no security and must be overridden, but nothing says that leaving it *alongside* a real decryptor turns it into a bypass of that decryptor rather than a fallback.

2. **A null cipher handling traffic is silent.** Routing to `ClearTextDecryptor` / `ClearTextEncryptor` is a success path: no event, no `errorNotify`. `SdlsSaRouter` only emits `TrackingTableFull` and `UntrackedBufferReturned`. A misconfigured flight build gives no telemetry hint that frames are being accepted (or emitted) in the clear.

3. **Downlink SA precedence follows the frame context.** `CcsdsSdlsFramer.cpp:41-46` uses `context.get_saIndex()` when set and only falls back to the `SA_INDEX` parameter when it is `SaIndexUnset`. `ComCfg.fpp:60` documents `saIndex` as "set by SDLS deframers, read by SDLS framers". No in-tree component currently carries an uplink context through to the downlink framer (the reference downlink chain builds fresh contexts), so this is latent — but if a future component did, the uplink SA would silently select the downlink encryptor. The configured parameter should be authoritative.

Note: there is no cryptographic decryptor/encryptor in the F´ repository (only the `ClearText*` placeholders and the `CcsdsSdlsDecrypt`/`Encrypt` interfaces from #5527), and no in-tree topology imports `ComCcsdsSdls`. This is therefore a documentation and defensive-hardening item, not a defect in shipped behavior.

## Context / Environment

```
devel @ cd3845fc2
```

## How to Reproduce

Configuration walk-through rather than a runtime repro:

1. Follow `ComCcsdsSdls/docs/sdd.md` §2.4: override `SdlsSaRouter` config to add `{ SA 1 -> port 1 }`, set `SaRouterPortCount = 2`, connect a project decryptor to router port 1. Leave the default `decryptor` instance and SA 0 mapping as documented in §2.5.
2. Uplink a frame whose leading two bytes are `0x0000`.
3. `SdlsSaRouter` routes it to `PLAINTEXT` → `ClearTextDecryptor` → `SUCCESS` → `CcsdsSdlsDeframer` forwards it on `dataOut` with no event emitted.

## Expected Behavior

- **Docs (`ComCcsdsSdls/docs/sdd.md`):** §2.4 should instruct projects to *replace* the default decryptor/encryptor (`CONFIGURATION_OVERRIDES` on `ComCcsdsSdlsConfig`) and, when adding SAs, to remove SA 0 from `SdlsCfg.SaMap` or remap it to `UNCONNECTED`. State explicitly that any SA mapped to a `ClearText*` component is a no-authentication path for the whole link. Requirement `SVC-COMCCSDSSDLS-005` should carry the same caveat.
- **`ClearTextDecryptor` / `ClearTextEncryptor`:** emit a throttled `WARNING_HI` event (e.g. `NullCipherInUse`) when handling a frame, so a null cipher in a flight build is visible in telemetry. Alternatively `SdlsSaRouter` could emit a per-port routing warning, but the null-cipher components are the more direct place.
- **`CcsdsSdlsFramer`:** make the `SA_INDEX` parameter authoritative for downlink encryption; treat a context-supplied `saIndex` as informational (or validate it against the parameter) rather than letting it select the encryptor. Update the `ComCfg.fpp:60` comment accordingly.
- Unit tests for the new event(s) and for the framer precedence change.

---
Reported by @stakeholder-11 via the F´ security reporting process; reclassified as a documentation/hardening issue and reproduced here with credit.

## Comentários

### Comentário 1 (stakeholder-12)

I’d like to take this on. Proposed scope for a focused change:

- add a throttled warning event to `ClearTextDecryptor` and `ClearTextEncryptor` whenever the null cipher actually handles traffic;
- update `ComCcsdsSdls` guidance to make replacement/removal of the default plaintext SA mapping explicit when configuring a real SDLS implementation;
- make the configured `SA_INDEX` authoritative for downlink selection, with corresponding unit coverage and documentation updates.

I’ll hold the PR until the CCB confirms this direction, but I can prepare the implementation and tests in the meantime.

### Comentário 2 (stakeholder-02)

This was closed with the exception of item 3: `Downlink SA precedence follows the frame context.`

I contend item 3 is not desirable. I will close this issue - feel free to reopen a ticket for item 3 if we need more discussion there.

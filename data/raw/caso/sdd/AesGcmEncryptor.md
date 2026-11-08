# Svc::Ccsds::AesGcmEncryptor

The `Svc::Ccsds::AesGcmEncryptor` component encrypts and authenticates downlink data under AES-256-GCM, per CCSDS [Space Data Link Security Protocol (CCSDS 355.0-B-2)](https://ccsds.org/Pubs/355x0b2.pdf). It implements `Svc.Ccsds.CcsdsSdlsEncrypt` toward an encryption client (typically [`Svc::Ccsds::CcsdsSdlsFramer`](../../CcsdsSdlsFramer/docs/sdd.md) via [`Svc::Ccsds::SdlsSaRouter`](../../SdlsSaRouter/docs/sdd.md)) and `Svc.Ccsds.SdlsKeyInterfaceClient` toward a key supplier such as [`Svc::Ccsds::SdlsFileKeyManager`](../../SdlsFileKeyManager/docs/sdd.md). It is the security-providing alternative to [`Svc::Ccsds::ClearTextEncryptor`](../../ClearTextEncryptor/docs/sdd.md), and the downlink mirror of [`Svc::Ccsds::AesGcmDecryptor`](../../AesGcmDecryptor/docs/sdd.md).

## Introduction

Encrypting a frame proceeds as follows:

1. Receive an SA index, plaintext buffer, and frame context on `encryptIn`.
2. Request the AES-256 key for the frame's security association via `keyGet`; on failure or a wrong-sized key, report `KEY_ERROR`.
3. Draw a fresh IV, encrypt the plaintext into a per-instance output store, authenticating the SA index and virtual channel as AES-GCM additional authenticated data (AAD).
4. Emit `IV (12) | ciphertext | MAC (16)` on `encryptOut` with status `SUCCESS`.
5. Return the plaintext buffer via `bufferReturnOut` on every path — it is copied, not encrypted in place.

The AAD is built by `Svc::Ccsds::Utils::SdlsTmAuthMask`, whose layout matches the ground segment's independent implementation of the same contract. The TM primary header does not yet exist at encryption time, so the virtual channel comes from the frame context — the same field `Svc::Ccsds::TmFramer` reads when it builds that header downstream, so the AAD always authenticates the VC actually transmitted.

The output store is a single per-instance buffer; it must be returned on `encryptReturnIn` before the next frame, and a frame arriving while it is still in flight is dropped with `ENCRYPTION_FAILURE` and the `OutputBufferBusy` event rather than overwriting unsent ciphertext.

## Design

The component is passive with no commands, telemetry, or parameters, and allocates no memory after construction. It composes two interfaces:

| Kind | Name | Port Type | Description |
|---|---|---|---|
| guarded input | encryptIn | Svc.Ccsds.CcsdsSdlsEncryption | Receives the SA index and plaintext buffer to encrypt. |
| output | encryptOut | Svc.Ccsds.CcsdsSdlsData | Sends the operation status and encrypted data downstream. |
| sync input | encryptReturnIn | Svc.ComDataWithContext | Receives back ownership of buffers sent on `encryptOut`. |
| output | bufferReturnOut | Svc.ComDataWithContext | Returns the incoming plaintext buffer for deallocation. |
| output | keyGet | Svc.Ccsds.SdlsKey | Requests the AES-256 key for the frame's security association, passing the SA index with the request. |

Events: `OutputBufferBusy` (WARNING_HI).

The SA index is passed on every `keyGet` request, but whether it selects the key is up to the connected key source. Per `Svc.Ccsds.SdlsKeyInterface`, an implementation keyed per SA documents which indices it serves and returns `KEY_ERROR` for any other, while one that ignores the index says so. The in-tree `Svc.Ccsds.SdlsFileKeyManager` ignores it and returns its single file key for every SA — adequate where the deployment uses one key across its SAs by design, but note that SAs sharing a key also share its IV budget (see Security Considerations).

## Configuration

Compile time: none of its own. The output store is sized directly from `ComCfg.TmFrameFixedSize`, the project-overridable TM frame size every deployment already sets; the accepted output is bounded by the TM data field less the SA index that `Svc.Ccsds.CcsdsSdlsFramer` prepends.

Runtime: none. The constructor builds the `EVP_CIPHER_CTX` every frame reuses, which is what keeps `encryptIn` free of dynamic allocation, and the authenticated virtual channel arrives per frame on the frame context.

## Security Considerations

Each frame is encrypted under a freshly drawn 96-bit random IV. A repeated IV under one key forfeits both confidentiality and authenticity for GCM, so this is the property the design protects most carefully: the component returns `ENCRYPTION_FAILURE` rather than emit a frame if the CSPRNG cannot supply one.

Random IVs of this width carry a bound. NIST SP 800-38D §8.3 limits a key to 2^32 invocations when IVs are constructed randomly, which keeps the collision probability below 2^-32. Nothing in this component counts invocations or forces a re-key, and the in-tree `Svc.Ccsds.SdlsFileKeyManager` serves one static key for the life of the process, so respecting the bound is a deployment responsibility. Two consequences follow:

- **The budget is per key, not per SA.** Where several security associations are served by the same key material — which `SdlsFileKeyManager` does by construction — their frame counts add up against the same 2^32.
- **A long-lived mission can reach it.** At one downlink frame every 100 ms across a single SA, 2^32 frames is roughly 13 years of continuous transmission; a higher frame rate, or several SAs sharing a key, scales that down proportionally.

A mission that expects to approach the bound should either rotate keys through a key manager of its own, or move to the deterministic IV construction of §8.2.1 (a fixed field identifying the sender plus an invocation field that never repeats), which removes the birthday bound at the cost of requiring non-volatile invocation state.

## Unit Testing

Direct tests covering the frame layout and AAD, IV freshness, both key-error paths, the output-size bound, buffer ownership, and both busy-store cases (the drop, and back-to-back frames succeeding when the buffer returns from inside `encryptOut`, as `CcsdsSdlsFramer` does on a synchronous pipeline). The AAD and ciphertext are checked against an independently built reference rather than assumed self-consistent. Requirements are traced with `REQUIREMENT()` macros in the test main.

## See Also

- [`Svc/Ccsds/Interfaces/CcsdsSdlsEncrypt.fpp`](../../Interfaces/CcsdsSdlsEncrypt.fpp)
- [`Svc/Ccsds/Interfaces/SdlsKey.fpp`](../../Interfaces/SdlsKey.fpp)
- [`Svc/Ccsds/AesGcmDecryptor`](../../AesGcmDecryptor/docs/sdd.md)
- [`Svc/Ccsds/CcsdsSdlsFramer`](../../CcsdsSdlsFramer/docs/sdd.md)
- [`Svc/Ccsds/SdlsSaRouter`](../../SdlsSaRouter/docs/sdd.md)

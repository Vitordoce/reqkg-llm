# Svc::Ccsds::AesGcmDecryptor

The `Svc::Ccsds::AesGcmDecryptor` component decrypts and authenticates uplink data under AES-256-GCM, per CCSDS. It implements `Svc.Ccsds.CcsdsSdlsDecrypt` toward a decryption client (typically [`Svc::Ccsds::CcsdsSdlsDeframer`](../../CcsdsSdlsDeframer/docs/sdd.md) via [`Svc::Ccsds::SdlsSaRouter`](../../SdlsSaRouter/docs/sdd.md)) and `Svc.Ccsds.SdlsKeyInterfaceClient` toward a key supplier such as [`Svc::Ccsds::SdlsFileKeyManager`](../../SdlsFileKeyManager/docs/sdd.md). It is the security-providing alternative to [`Svc::Ccsds::ClearTextDecryptor`](../../ClearTextDecryptor/docs/sdd.md), and the uplink mirror of [`Svc::Ccsds::AesGcmEncryptor`](../../AesGcmEncryptor/docs/sdd.md).

## Introduction

Decrypting a frame proceeds as follows:

1. Receive an SA index, ciphertext buffer (`IV (12) | ciphertext | MAC (16)`), and frame context on `decryptIn`.
2. Reject a buffer too short to hold an IV and a MAC with `DECRYPTION_FAILURE` — before requesting a key, since the uplink is attacker-influenced.
3. Request the AES-256 key for the frame's security association via `keyGet`; on failure or a wrong-sized key, report `KEY_ERROR`.
4. Decrypt in place, authenticating the SA index and virtual channel as AES-GCM additional authenticated data (AAD).
5. On a failed MAC check, report `MAC_VERIFICATION_FAILURE`, distinct from `DECRYPTION_FAILURE`; the component remains able to decrypt subsequent frames.
6. On success, narrow the buffer to the plaintext and emit it on `decryptOut` with status `SUCCESS`.

Decryption is in place, so the emitted buffer is the one received, advanced past the IV and narrowed to the plaintext length; `Fw::Buffer` keeps its allocation context independently of the data pointer, so it remains deallocatable by the issuing `Svc.BufferManager`. Buffers returned on `decryptReturnIn` are passed upstream via `bufferReturnOut` unconditionally, since every buffer emitted is the one that arrived.

The AAD is built by `Svc::Ccsds::Utils::SdlsTcAuthMask`, whose layout matches the ground segment's independent implementation of the same contract. The virtual channel comes from the frame context: `Svc::Ccsds::TcDeframer` reads it from the TC primary header and sets it on the context before stripping that header, so it is still available by decryption time.

## Security Considerations

What this component provides: confidentiality, integrity, and authentication of the frame body, bound to the SA index and the virtual channel. A frame modified in flight, built under a different key, or presented on a different virtual channel or SA fails the MAC check.

What it does not provide, and which an operator must plan for:

- **No anti-replay.** The IV is chosen by the sender and is not checked against anything, and no sequence number is tracked per SA. A previously valid TC frame captured off the link and re-injected later passes the MAC check and reaches the command path unchanged. SDLS anti-replay (CCSDS 355.0-B-2 §4.1.3) relies on an Anti-Replay Sequence Number in the security header, which this implementation does not carry. Missions exposed to a recording adversary need replay protection above this layer — a command counter, a time-bounded authorization window, or an idempotent command set.
- **No key rotation.** The key is fetched per frame from the connected key source, so rotation is that component's responsibility. The in-tree `Svc.Ccsds.SdlsFileKeyManager` serves one static key for the life of the process.

## Design

The component is passive with no commands, telemetry, or parameters, and allocates no memory after construction. It composes two interfaces:

| Kind | Name | Port Type | Description |
|---|---|---|---|
| guarded input | decryptIn | Svc.Ccsds.CcsdsSdlsEncryption | Receives the SA index and ciphertext buffer to decrypt. |
| output | decryptOut | Svc.Ccsds.CcsdsSdlsData | Sends the operation status and decrypted data upstream. |
| sync input | decryptReturnIn | Svc.ComDataWithContext | Receives back ownership of buffers sent on `decryptOut`. |
| output | bufferReturnOut | Svc.ComDataWithContext | Returns the incoming buffer for deallocation. |
| output | keyGet | Svc.Ccsds.SdlsKey | Requests the AES-256 key bound to the frame's security association. |

The component emits no events: every outcome, including a failed authentication, is reported as an `SdlsStatus` on `decryptOut`.

## Configuration

Compile time: none.

Runtime: none. The constructor builds the `EVP_CIPHER_CTX` every frame reuses, which is what keeps `decryptIn` free of dynamic allocation, and the authenticated virtual channel arrives per frame on the frame context. The [`Svc/Ccsds/AesGcmEncryptor`](../../AesGcmEncryptor/docs/sdd.md) downlink path is built the same way.

A key source must be connected to `keyGet` and made ready before the first frame arrives; the component requests a key per frame and reports `KEY_ERROR` if none is available. The in-tree `Svc.Ccsds.SdlsFileKeyManager` needs `configure(path, keySize)` during topology setup.

## Unit Testing

Direct tests covering in-place decryption and its allocation context, the short-buffer shape-check rejection, both key-error paths, and the buffer return path. Authentication is exercised by tampering with the IV, ciphertext, and MAC in turn, and by presenting frames built for another VC and another SA, with a following good frame confirming the shared cipher context survives a rejection. The AAD and a known-answer frame are checked against an independently built reference rather than assumed self-consistent. Requirements are traced with `REQUIREMENT()` macros in the test main.

## See Also

- [`Svc/Ccsds/Interfaces/CcsdsSdlsDecrypt.fpp`](../../Interfaces/CcsdsSdlsDecrypt.fpp)
- [`Svc/Ccsds/Interfaces/SdlsKey.fpp`](../../Interfaces/SdlsKey.fpp)
- [`Svc/Ccsds/AesGcmEncryptor`](../../AesGcmEncryptor/docs/sdd.md)
- [`Svc/Ccsds/CcsdsSdlsDeframer`](../../CcsdsSdlsDeframer/docs/sdd.md)
- [`Svc/Ccsds/SdlsSaRouter`](../../SdlsSaRouter/docs/sdd.md)

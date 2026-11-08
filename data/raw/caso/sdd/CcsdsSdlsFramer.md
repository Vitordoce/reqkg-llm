# Svc::Ccsds::CcsdsSdlsFramer

The `Svc::Ccsds::CcsdsSdlsFramer` component frames buffers into CCSDS SDLS (Space Data Link Security) frames. It is both a framer (implementing the `Svc.Framer` interface within a framing pipeline) and an encryption client (implementing `Svc.Ccsds.CcsdsSdlsEncryptClient` toward an encryption helper such as `Svc.Ccsds.SdlsSaRouter` or an encryptor component). It is the downlink mirror of [`Svc::Ccsds::CcsdsSdlsDeframer`](../../CcsdsSdlsDeframer/docs/sdd.md).

## Introduction

Framing an SDLS frame proceeds as follows:

1. Determine the security association (SA) index: from the frame context when set, otherwise from the `SA_INDEX` parameter.
2. Record the SA index in the frame context and pass the data, SA index, and context to the encryption helper.
3. Check the status passed forward with the encrypted data; on failure raise an event and return the buffer.
4. Upon receiving successfully encrypted data back, allocate a frame buffer and prepend the 16-bit SA index.
5. Pass the SDLS frame downstream for further framing/transmission.

Buffer ownership follows the standard F Prime data-with-context return pattern: encrypted buffers are returned to the encryption helper via `encryptReturnOut` once copied into the frame, allocated frame buffers returned from downstream (`dataReturnIn`) are deallocated via `bufferDeallocate`, and original data buffers returned by the helper (`bufferReturnIn`) go back upstream via `dataReturnOut`. Com status (`comStatusIn`) passes through unmodified to `comStatusOut`; additionally, when a frame is dropped (encryption failure or buffer-allocation failure), the framer emits a ready-for-more com status on `comStatusOut` so a `ComQueue`-driven downlink does not stall.

## Design

The component is passive with no commands or telemetry. It composes two interfaces plus allocation ports:

| Kind | Name | Port Type | Description |
|---|---|---|---|
| sync input | dataIn | Svc.ComDataWithContext | Receives data to frame (from `Svc.Framer`). |
| output | dataOut | Svc.ComDataWithContext | Sends the SDLS frame downstream. |
| output | dataReturnOut | Svc.ComDataWithContext | Returns data buffer ownership upstream. |
| sync input | dataReturnIn | Svc.ComDataWithContext | Receives back ownership of frames sent on `dataOut`. |
| sync input | comStatusIn | Fw.SuccessCondition | Receives downstream ready status. |
| output | comStatusOut | Fw.SuccessCondition | Passes ready status upstream. |
| output | encryptOut | Svc.Ccsds.CcsdsSdlsEncryption | Sends the SA index and data to the encryption helper. |
| sync input | encryptIn | Svc.Ccsds.CcsdsSdlsData | Receives the operation status and encrypted data from the helper. |
| output | encryptReturnOut | Svc.ComDataWithContext | Returns ownership of encrypted buffers to the helper. |
| sync input | bufferReturnIn | Svc.ComDataWithContext | Receives back the data buffer sent on `encryptOut`. |
| output | bufferAllocate | Fw.BufferGet | Allocates the frame buffer for the SA prepend. |
| output | bufferDeallocate | Fw.BufferSend | Deallocates frame buffers. |

Events: `EncryptionFailed` (WARNING_HI, carries the `SdlsStatus`) and `BufferAllocationFailed` (WARNING_HI, carries the requested size as `FwSizeType`). Each event has an independent time-based throttle (`throttle 5 every { seconds = 60 }`): at most five emissions per 60-second period, measured with the component's time port from the first emission of the period. Once the quota is exhausted, further failures are suppressed until the period elapses; the next failure at or after that point is emitted and re-arms the quota, so a persistent failure keeps reporting at a bounded rate. Successful frames do not reset either quota. This component exposes no reset command.

Parameters: `SA_INDEX` (U16, default 1) — the SA index used when the incoming frame context does not specify one (context `saIndex` equal to its default value of 0xFFFF is treated as unset).

## Configuration

The `SA_INDEX` parameter selects the default security association for downlink frames. Its default of 1 matches the `SdlsCfg.SaMap` default in `Svc.Ccsds.SdlsSaRouter`, which routes SA 1 to the `PLAINTEXT` port, so the shipped `ComCcsdsSdls` subtopology downlinks through the default encryptor with no deployment configuration. Changing this parameter without a matching router entry yields `UNKNOWN_SA` and a dropped frame.

Note that `Svc.Ccsds.SpacePacketFramer` does not set `saIndex` on the frame context, so on the standard downlink path this parameter supplies the SA index for every frame.

## Unit Testing

Rule-based testing (STest) with rules covering both SA selection paths, both error paths, the encrypted-data framing path, the ownership return paths, and the comStatus pass-through; a 10000-step randomized scenario interleaves all rules. The error rules retain shadow counts across history clearing and verify buffer/status handling even when events are suppressed. Deterministic tests check independent quotas, interleaved successful frames, separate component instances, and re-arming of the quota once the throttle period has elapsed on the test time port. Requirements are traced with `REQUIREMENT()` macros in the test main.

## See Also

- [`Svc/Ccsds/Interfaces/CcsdsSdlsEncrypt.fpp`](../../Interfaces/CcsdsSdlsEncrypt.fpp)
- [`Svc/Ccsds/CcsdsSdlsDeframer`](../../CcsdsSdlsDeframer/docs/sdd.md)
- [`Svc/Ccsds/SdlsSaRouter`](../../SdlsSaRouter/docs/sdd.md)

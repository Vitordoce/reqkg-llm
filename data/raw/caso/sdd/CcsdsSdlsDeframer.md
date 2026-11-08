# Svc::Ccsds::CcsdsSdlsDeframer

The `Svc::Ccsds::CcsdsSdlsDeframer` component deframes buffers containing CCSDS SDLS (Space Data Link Security) frames. It is both a deframer (implementing the `Svc.Deframer` interface within a deframing pipeline) and a decryption client (implementing `Svc.Ccsds.CcsdsSdlsDecryptClient` toward a decryption helper such as `Svc.Ccsds.SdlsSaRouter` or a decryptor component).

## Introduction

Deframing an SDLS frame proceeds as follows:

1. Check that the frame is long enough to contain the 16-bit security association (SA) index.
2. Extract the SA index from the front of the frame and record it in the frame context.
3. Remove the SA index and pass the remaining data, SA index, and updated context to the decryption helper.
4. Check the status passed forward with the decrypted data; on failure raise an event, notify `errorNotify`, and return the buffer to the decryption subsystem.
5. Pass successfully decrypted data downstream for further processing.

Buffer ownership follows the standard F Prime data-with-context return pattern: frames that cannot be processed (or fail decryption) are returned via `dataReturnOut`, decrypted data ownership returns from downstream (`dataReturnIn`) are routed back to the decryption helper (`decryptReturnOut`), and original frame buffers returned by the helper (`bufferReturnIn`) go back upstream via `dataReturnOut`.

## Design

The component is passive with no commands, telemetry, or parameters. It composes two interfaces:

| Kind | Name | Port Type | Description |
|---|---|---|---|
| guarded input | dataIn | Svc.ComDataWithContext | Receives framed SDLS data (from `Svc.Deframer`). |
| output | dataOut | Svc.ComDataWithContext | Sends decrypted, deframed data downstream. |
| output | dataReturnOut | Svc.ComDataWithContext | Returns frame buffer ownership upstream. |
| sync input | dataReturnIn | Svc.ComDataWithContext | Receives back ownership of buffers sent on `dataOut`. |
| output | decryptOut | Svc.Ccsds.CcsdsSdlsEncryption | Sends the SA index and payload to the decryption helper. |
| sync input | decryptIn | Svc.Ccsds.CcsdsSdlsData | Receives the operation status and decrypted data from the helper. |
| output | decryptReturnOut | Svc.ComDataWithContext | Returns ownership of decrypted buffers to the helper. |
| sync input | bufferReturnIn | Svc.ComDataWithContext | Receives back the iv/data buffer sent on `decryptOut`. |
| output | errorNotify | Svc.Ccsds.ErrorNotify | Notifies the pipeline of frame errors. |

Events: `InsufficientLength` (WARNING_HI) and `DecryptionFailed` (WARNING_HI, carries the `SdlsStatus`).

## Configuration

None. The component requires no initialization-time configuration.

## Unit Testing

Rule-based testing (STest) with rules covering the nominal deframe path, both error paths, and the three data/ownership flow paths; a 10000-step randomized scenario interleaves all rules. Requirements are traced with `REQUIREMENT()` macros in the test main.

## See Also

- [`Svc/Ccsds/Interfaces/CcsdsSdlsDecrypt.fpp`](../../Interfaces/CcsdsSdlsDecrypt.fpp)
- [`Svc/Ccsds/SdlsSaRouter`](../../SdlsSaRouter/docs/sdd.md)
- [`Svc/Ccsds/ClearTextDecryptor`](../../ClearTextDecryptor/docs/sdd.md)

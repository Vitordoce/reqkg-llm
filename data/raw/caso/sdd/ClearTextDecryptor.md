# Svc::Ccsds::ClearTextDecryptor

> [!WARNING]
> **This component provides NO security.** It performs no authentication, no integrity
> checking, and no decryption. All data passes through unmodified. It is intended only
> for clear-mode operation (e.g. as the default decryptor in a standard subtopology) and
> for testing. Do not use it where confidentiality, integrity, or authenticity of the
> data link is required.

The `Svc::Ccsds::ClearTextDecryptor` component is a pass-through implementation of the `Svc.Ccsds.CcsdsSdlsDecrypt` interface. It is a pure pass-through in both dimensions: requests received on `decryptIn` are forwarded out `decryptOut` with the buffer and context unmodified (alongside an `SdlsStatus.SUCCESS` status), and buffer ownership returned on `decryptReturnIn` is passed upstream via `bufferReturnOut` for deallocation. No memory is allocated.

## Functionality

- Receives an SA index, iv/data buffer, and frame context on the guarded `decryptIn` port; the SA index is ignored.
- Forwards the buffer and context unmodified out `decryptOut` alongside an `SdlsStatus.SUCCESS` status.
- Passes ownership returns received on `decryptReturnIn` upstream via `bufferReturnOut` (the forwarded buffer is the incoming buffer, as no allocation occurs).

## Port Descriptions

| Kind          | Name            | Port Type                     | Description |
|---------------|-----------------|-------------------------------|-------------|
| guarded input | decryptIn       | Svc.Ccsds.CcsdsSdlsEncryption | Receives the SA index and iv/data buffer (from `CcsdsSdlsDecrypt` interface). |
| output        | decryptOut      | Svc.Ccsds.CcsdsSdlsData       | Sends the operation status and (unmodified) data downstream. |
| guarded input | decryptReturnIn | Svc.ComDataWithContext        | Receives back ownership of buffers sent on `decryptOut`. |
| output        | bufferReturnOut | Svc.ComDataWithContext        | Returns the incoming iv/data buffer for deallocation. |

## Events

| Name | Severity | Description |
|------|----------|-------------|
| NullCipherInUse | WARNING_HI (throttle 5) | Raised for every frame handled, carrying the SA index. Its presence in telemetry means a frame was accepted or emitted with no authentication and no decryption; a deployment requiring security must replace this component and must not leave any SA mapped to it. |

## See Also

- [`Svc/Ccsds/Interfaces/CcsdsSdlsDecrypt.fpp`](../../Interfaces/CcsdsSdlsDecrypt.fpp)
- [`Svc/Ccsds/SdlsSaRouter`](../../SdlsSaRouter/docs/sdd.md)

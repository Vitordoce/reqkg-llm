# Issue #5578: CfdpManager: support partial file transmission

- Fonte: https://github.com/nasa/fprime/issues/5578
- Autor (pseudonimizado): stakeholder-09
- Estado na coleta: open

## Summary

The `fileIn` (`Svc.SendFileRequest`) port carries `offset` and `length` arguments intended to support partial file downlink, but `CfdpManager` currently rejects any request with a non-zero offset or length. The DpCatalog -> CfdpManager downlink interface can specify these values, so partial file transmission should be supported.

## Current state

- The port carries the arguments: `Svc/FileDownlinkPorts/FileDownlinkPorts.fpp:23-28`
  ```
  port SendFileRequest(
                        sourceFileName: string size 100
                        destFileName: string size 100
                        offset: U32 @< start offset into the file
                        length: U32 @< amount of data in bytes; 0 to read until end of file
                      ) -> Svc.SendFileResponse
  ```
- Non-zero offset/length is rejected: `Svc/Ccsds/CfdpManager/CfdpManager.cpp:206-212`
  ```cpp
  // CFDP engine does not support partial file retransmit at this time
  // Offset and length must be 0 to send the entire file
  if (offset > 0 || length > 0) {
      response.set_status(Svc::SendFileStatus::STATUS_INVALID);
      this->log_WARNING_LO_UnsupportedSendFileArguments(offset, length);
      return response;
  }
  ```
- Rejection event: `Svc/Ccsds/CfdpManager/Events.fppi:18` (`UnsupportedSendFileArguments`)
- Threading gap: the queued `FileInRequest` struct (populated at `Svc/Ccsds/CfdpManager/CfdpManager.cpp:218-230`) only carries `sourceFileName`, `destFileName`, and `context`. It does not carry offset/length, so those fields must be added and threaded through to `Engine::txFile`.
- Minor: the `offset` doc comment in `FileDownlinkPorts.fpp:26` is a copy/paste of `length`'s and should be corrected.

## Acceptance criteria

- Add offset/length to `FileInRequest` and thread them through into the engine TX path
- Implement partial-file transmission (start at offset, send `length` bytes)
- Remove the offset/length rejection in `fileIn_handler`
- Add UT coverage for a partial transfer (non-zero offset and bounded length)
- Fix the `offset` argument doc comment in `FileDownlinkPorts.fpp`

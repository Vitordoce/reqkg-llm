# Svc::Ccsds::ApidManager

The `Svc::Ccsds::ApidManager` component manages CCSDS Application Process Identifier (APID) sequence counts for the F Prime communications stack. It provides per-APID sequence count tracking and validation, supporting the construction and checking of CCSDS Space Packet headers by other components (such as `SpacePacketFramer` and `SpacePacketDeframer`).

The `ApidManager` is typically used in conjunction with the [`SpacePacketFramer`](../../SpacePacketFramer/docs/sdd.md) (to provide incrementing sequence counts for each APID) and the [`SpacePacketDeframer`](../../SpacePacketDeframer/docs/sdd.md) (to validate received sequence counts and detect dropped or out-of-order packets).

## Functionality

- Maintains a `Fw::ArrayMap` of APIDs and their associated 14-bit sequence counts. The map is sized to the number of APIDs configured in the ComCfg.Apid enum.
- Provides a way to retrieve the current sequence count for a given APID through a port call.
- Provides a way to validate a received sequence count for a given APID through a port call.

## Port Descriptions

| Kind            | Name                  | Port Type                | Description                                                                 |
|-----------------|-----------------------|--------------------------|-----------------------------------------------------------------------------|
| guarded input   | validateApidSeqCountIn| Ccsds.ApidSequenceCount  | Validates a received sequence count for a given APID.                       |
| guarded input   | getApidSeqCountIn     | Ccsds.ApidSequenceCount  | Returns and increments the sequence count for a given APID.                 |

## Events

| Name                   | Severity      | Description                                                                 |
|------------------------|---------------|-----------------------------------------------------------------------------|
| UnexpectedSequenceCount| warning low   | Received an unexpected sequence count for an APID.                          |

## Usage

- The `getApidSeqCountIn` port is called by a component (e.g., `SpacePacketFramer`) to obtain and increment the sequence count for a given APID when constructing a new Space Packet.
- The `validateApidSeqCountIn` port is called by a component (e.g., `SpacePacketDeframer`) to check the sequence count of a received Space Packet. If the count does not match the expected value, an event is logged and the onboard count is synchronized.

## See Also

- [`Svc::Ccsds::SpacePacketFramer`](../../SpacePacketFramer/docs/sdd.md)
- [`Svc::Ccsds::SpacePacketDeframer`](../../SpacePacketDeframer/docs/sdd.md)
- [CCSDS Space Packet Protocol (CCSDS 133.0-B-2)](https://ccsds.org/Pubs/133x0b2e2.pdf)

# Discussion #4030: Make APID use in CCSDS telemetry/DPs match up more closely with ground systems.

- Fonte: https://github.com/nasa/fprime/discussions/4030
- Autor (pseudonimizado): stakeholder-08

This is a placeholder that needs a little more digging.

The current F Prime CCSDS packets have the following layout:

APID = class of telemetry (matches old F Prime descriptor type)
PAYLOAD = packet/channel/event/DP ID followed by time stamp and telemetry data

The data layout of the packet payload is not known by the APID but requires the ground system to look at the ID in the payload.

My impression is that most ground systems want a specification that uniquely maps an APID to a particular set of data in the packet. That allows decommutation that only needs the APID.

We should consider making the APID map to packet ID or DP ID. I think this would also involve deprecating TlmChan since it doesn't have fixed layouts.

More to come...

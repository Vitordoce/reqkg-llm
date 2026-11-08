# Discussion #5027: Improvemtents to CCSDS In F Prime

- Fonte: https://github.com/nasa/fprime/discussions/5027
- Autor (pseudonimizado): stakeholder-05

F Prime currently has initial support for CCSDS.  However, we would like to do better in how we represent data in CCSDS packets to fall in-line with more industry standards and better meet user needs.

## Representation of Time

CCSDS recommends representing time in a secondary header.  Possibly with a U16/U32 format.  We suggest making this configurable so that project that do not need the full Fw.Time representation don't have to use this.

## APID Usage

We propose having a configuration where the packet ID of the tlm packetizer maps to the APID.  This would save overhead on sending a redundant packet ID when the APID 11bits are under-utilized.

## Comentários

### Comentário 1 (stakeholder-02)

I am highly in favor expanding our support of the various CCSDS standards!

For the timestamp in the secondary header of Space Packet, big upvote from me. This seems like a very natural evolution of our data format.

For the APID usage of Packet IDs, I just want to call out a few things:
- 11 bit APID means there are only ~2048 to choose from (minus IDLE and other framework-utilized APIDs). And the APID domain is at the mission level. If we start thinking of multiple F´ deployments on a single bus, or even just F´ deployed as part of a broader spacecraft where the F´ deployment would be limited in terms of how many APIDs it's allocated... one could easily run out of APIDs. 
- I wouldn't say Packet ID is redundant with APID. TlmPacketizer currently utilizes a single APID, and can emit many different types of data within that APID. We're essentially multiplexing lots of data in a single APID by stamping out the Packet ID in the data. There's a bit of overhead to that yes, but it also has many benefits. Maybe the question we need to ask is what are we trying to optimize for?
- In a similar line of thought, one Packet ID == APID means a single space packet could only ever transmit a single Tlm Packet per Space Packet. No theoretical possibility of stuffing multiple Telemetry packets into a single Space Packet anymore. Is this desirable?
- Whatever direction we end up going, we will want to have a rationale for whether the downlinking of Events should have a format consistent with that of TlmPackets or not.

### Resposta 2 (stakeholder-17)

I want to underscore that APID should not be forcibly tied to the TlmPacketizer Packet IDs.  11 bits is not much, particularly on bigger missions.

I have been around some discussions with seasoned FSW developers griping about projects stuffing unrelated data into messages because there were availably bytes, but the project was out of APIDs.  This can get particularly weird when you default to one APID per command (yes, that is a thing, and its a separate APID space from telemetry) and your project exceeds 2000 commands.  Suddenly there are these weird multi-command messages with a switch to describe the active piece of the message.  In some missions, it has been common practice to define a C struct for each APID as the serialization strategy and the materializes as 3 structs packed together.  Weird.

Anyway, my general preference is to consider APID's to represent *Applications*.  That means I want things like file transfer to have an APID, general housekeeping to have an APID, a specific instrument or subsystem to be allocated its own APID.  The mental model maps approximately to IP ports, where it can make sense to have a few numbers allocated to an application but not normally a zillion to one application.

### Comentário 3 (stakeholder-18)

I also up vote adding the time in a secondary header with a deployment configurable length/format - I'd like to suggest allowing projects to include both seconds & sub/nanoseconds in the secondary header and specify the size of each. 

Regarding APIDs, I agree with the above concerns with the proposal regarding  `configuration where the packet ID of the tlm packetizer maps to the APID` (especially running out of IDs and restricting having multiple tlm packets per space packet) so am not in favor of it. For APID assignment, I'd like to advocate considering an APID to identify application (source) + data criticality (so that ground software can identify meaningful information about the packet by only parsing the CCSDS headers)

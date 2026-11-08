# Discussion #4390: Add file validator/dispatcher component

- Fonte: https://github.com/nasa/fprime/discussions/4390
- Autor (pseudonimizado): stakeholder-08

When sending files to a flight system, especially long latency deep=space missions, it is useful to validate files and do autonomous actions without ground-in-the-loop. This proposal is to add a component that does validation and dispatches files to components that need them.

Ths would entail:

1) Add a port to `Svc/FileUplink` that emits a file name when uplink is complete.
2) Implement a new component that has an input port from 1).
3) Implement "validate" and "execute" output ports that have a file name for downstream components.
4) The component will have a user-supplied table that maps filename extensions to the "validate" and "execute" ports.

This is a tinker-toy component that will implement part of the chain for auto-validating and auto-executing uplinked files.

## Comentários

### Comentário 1 (stakeholder-02)

For awareness: [CFDP](https://ccsds.org/Pubs/720x1g4.pdf) supports "User Message", which is basically arbitrary metadata sent alongside a file transaction. Sounds like this could be leveraged in many ways, for example "this is an auto-run sequence" etc
